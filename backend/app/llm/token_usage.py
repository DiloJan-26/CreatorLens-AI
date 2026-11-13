"""Normalize documented Gemini and LangChain usage without inventing categories."""
from dataclasses import dataclass, field, asdict
from typing import Any, Mapping
import math


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None  # billable output, includes thinking exactly once
    total_tokens: int | None = None
    cached_input_tokens: int | None = field(default=None, compare=False)
    noncached_input_tokens: int | None = field(default=None, compare=False)
    candidate_tokens: int | None = field(default=None, compare=False)
    thinking_tokens: int | None = field(default=None, compare=False)
    tool_use_prompt_tokens: int | None = field(default=None, compare=False)
    provider_total_tokens: int | None = field(default=None, compare=False)
    metadata_source: str | None = field(default=None, compare=False)
    service_tier: str | None = field(default=None, compare=False)
    model_id: str | None = field(default=None, compare=False)
    completeness: str = field(default='unavailable', compare=False)
    warnings: tuple[str, ...] = field(default=(), compare=False)

    @property
    def available(self):
        return any(v is not None for v in (self.input_tokens,self.output_tokens,self.total_tokens))

    def safe_dict(self):
        return asdict(self)


def _as_mapping(value):
    if isinstance(value, Mapping): return value
    dump=getattr(value,'model_dump',None)
    if callable(dump): return dump()
    # Known SDK attribute shapes only; never retain arbitrary response attributes.
    keys=('prompt_token_count','cached_content_token_count','candidates_token_count','thoughts_token_count',
        'tool_use_prompt_token_count','total_token_count','service_tier')
    return {k:getattr(value,k) for k in keys if hasattr(value,k)}


def _nonnegative_int(value):
    if isinstance(value,bool): return None
    if isinstance(value,int): return value if value>=0 else None
    if isinstance(value,float): return int(value) if math.isfinite(value) and value>=0 and value.is_integer() else None
    if isinstance(value,str) and value.strip().isascii() and value.strip().isdigit(): return int(value.strip())
    return None


def _usage_sources(response):
    root=_as_mapping(response); sources=[]
    for key in ('usage_metadata','usageMetadata'):
        value=_as_mapping(getattr(response,key,None)) or _as_mapping(root.get(key))
        if value: sources.append(value)
    for key in ('response_metadata','additional_kwargs'):
        meta=_as_mapping(getattr(response,key,None)) or _as_mapping(root.get(key))
        for nested in ('usage_metadata','usageMetadata','token_usage','usage'):
            value=_as_mapping(meta.get(nested))
            if value: sources.append(value)
        if meta: sources.append(meta)
    if root: sources.append(root)
    return sources


def parse_token_usage(response):
    sources=_usage_sources(response); warnings=[]
    native=next((s for s in sources if any(k in s for k in ('promptTokenCount','prompt_token_count','candidatesTokenCount','candidates_token_count'))),None)
    data=native or next((s for s in sources if any(k in s for k in ('input_tokens','prompt_tokens','input_token_count','output_tokens','completion_tokens','total_tokens'))),{})
    def count(*keys):
        for key in keys:
            if key in data:
                if data[key] is None: return None
                value=_nonnegative_int(data[key])
                if value is None: warnings.append('Invalid usage field: '+key)
                return value
        return None
    prompt=count('promptTokenCount','prompt_token_count','input_tokens','input_token_count','prompt_tokens')
    total=count('totalTokenCount','total_token_count','total_tokens')
    reported_total=total
    cached=count('cachedContentTokenCount','cached_content_token_count')
    thinking=count('thoughtsTokenCount','thoughts_token_count')
    tools=count('toolUsePromptTokenCount','tool_use_prompt_token_count')
    if native is not None:
        candidate=count('candidatesTokenCount','candidates_token_count','candidate_token_count')
        output=candidate+thinking if candidate is not None and thinking is not None else None
        if output is None and prompt is not None and candidate is not None and total is not None:
            # Conservation establishes billable output only when no unexplained tool tokens remain.
            remainder=total-prompt-(tools or 0)
            if remainder==candidate if thinking is None else remainder==candidate+thinking: output=remainder
        # Candidate tokens remain separately visible; unknown thinking/tool usage must not become billable output.
    else:
        output=count('output_tokens','output_token_count','completion_tokens')
        details=_as_mapping(data.get('output_token_details'))
        if 'reasoning' in details:
            thinking=_nonnegative_int(details['reasoning'])
            if thinking is None: warnings.append('Invalid usage field: reasoning')
        input_details=_as_mapping(data.get('input_token_details'))
        if 'cache_read' in input_details:
            cached=_nonnegative_int(input_details['cache_read'])
            if cached is None: warnings.append('Invalid usage field: cache_read')
        candidate=output-thinking if output is not None and thinking is not None and output>=thinking else None
    if cached is not None and (prompt is None or cached>prompt): warnings.append('Cached input exceeds or lacks prompt total.'); cached=None
    if thinking is not None and output is not None and thinking>output: warnings.append('Thinking exceeds billable output.')
    if prompt is not None and output is not None:
        calculated=prompt+output+(tools or 0)
        if total is None: total=calculated
        elif total!=calculated: warnings.append('Provider total does not reconcile with normalized categories.')
    complete=prompt is not None and output is not None and not warnings
    if native is not None and thinking is None and (reported_total is None or prompt is None or candidate is None or reported_total!=prompt+candidate+(tools or 0)): complete=False
    source='gemini_native' if native is not None else 'langchain_combined' if data else None
    model=None
    for s in sources:
        value=s.get('model_name') or s.get('model_version') or s.get('modelVersion')
        if isinstance(value,str) and value.strip(): model=value.strip()[:128]; break
    tier=data.get('serviceTier',data.get('service_tier'))
    if tier is None:
        tier=next((s.get('serviceTier',s.get('service_tier')) for s in sources if s.get('serviceTier',s.get('service_tier')) is not None),None)
    return TokenUsage(prompt,output,total,cached,prompt-cached if prompt is not None and cached is not None else None,
        candidate,thinking,tools,reported_total,source,str(tier).lower()[:32] if tier is not None else None,model,
        'complete' if complete else 'partial' if any(v is not None for v in (prompt,output,total)) else 'unavailable',tuple(warnings))
