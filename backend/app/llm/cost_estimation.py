from decimal import Decimal

from app.llm.token_usage import TokenUsage


MILLION = Decimal("1000000")


def estimate_cost_usd(
    usage: TokenUsage,
    *,
    input_cost_per_million_usd: float | None,
    output_cost_per_million_usd: float | None,
) -> Decimal | None:
    """Estimate model cost only when both usage and configured rates exist."""

    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    if (
        input_cost_per_million_usd is None
        or output_cost_per_million_usd is None
    ):
        return None

    input_cost = (
        Decimal(usage.input_tokens)
        * Decimal(str(input_cost_per_million_usd))
        / MILLION
    )
    output_cost = (
        Decimal(usage.output_tokens)
        * Decimal(str(output_cost_per_million_usd))
        / MILLION
    )
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


# Runtime estimation uses an exact, reviewed registry, never the global legacy rates.
import json
from pathlib import Path
from datetime import date


def estimate_model_cost(usage, *, provider, model, service_tier=None, at=None, caching_mode='unknown', deterministic=False):
    result=dict(status='pricing_unavailable',estimated_cost_usd=None,priced_subtotal_usd=None,
        actual_billed_cost_usd=None,mode='paid_tier_equivalent_not_invoice',reason=None,
        provider=provider,model=model,service_tier=service_tier,caching_mode=caching_mode,policy_version=None,components={})
    if deterministic:
        return {**result,'status':'known_zero','estimated_cost_usd':'0','priced_subtotal_usd':'0','mode':'no_provider_call','reason':'No model invocation.'}
    registry=json.loads((Path(__file__).with_name('pricing_registry.json')).read_text(encoding='utf-8'))
    result['policy_version']=registry['version']
    day=(at or date.today()).isoformat()
    result['pricing_observed_on']=day
    rate=next((r for r in registry['entries'] if r['provider']==provider and r['model']==model and r['service_tier']==service_tier
        and r['effective_from']<=day and (r['effective_until'] is None or day<r['effective_until'])),None)
    if rate is None: result['reason']='No verified rate for exact model, tier and observation period.'; return result
    result.update(source_url=rate['source_url'],verified_on=rate['verified_on'],rates=rate)
    if usage is None or not usage.available: result.update(status='usage_unavailable',reason='Provider usage unavailable.'); return result
    counts=(usage.input_tokens,usage.output_tokens,usage.cached_input_tokens,usage.thinking_tokens,usage.tool_use_prompt_tokens)
    if any(v is not None and (type(v) is not int or v<0) for v in counts):
        result.update(status='usage_invalid',reason='Usage counts must be nonnegative integers.'); return result
    if usage.warnings: result.update(status='usage_invalid',reason='; '.join(usage.warnings)); return result
    components={}
    if usage.input_tokens is not None and usage.cached_input_tokens is not None and 0<=usage.cached_input_tokens<=usage.input_tokens:
        components['input_cost_usd']=str(Decimal(usage.input_tokens-usage.cached_input_tokens)*Decimal(rate['input_per_million'])/MILLION)
        components['cached_input_cost_usd']=str(Decimal(usage.cached_input_tokens)*Decimal(rate['cached_input_per_million'])/MILLION)
    if usage.output_tokens is not None and usage.completeness=='complete':
        components['output_cost_usd']=str(Decimal(usage.output_tokens)*Decimal(rate['output_per_million'])/MILLION)
    subtotal=sum((Decimal(v) for v in components.values()),Decimal(0)) if components else None
    complete=len(components)==3 and usage.completeness=='complete' and not usage.tool_use_prompt_tokens and not (usage.cached_input_tokens and caching_mode!='implicit')
    result.update(components=components,priced_subtotal_usd=str(subtotal) if subtotal is not None else None,
        estimated_cost_usd=str(subtotal) if complete else None,status='estimated' if complete else 'partial',
        reason='Token inference estimate only; actual billed cost unavailable.' if complete else 'Incomplete usage, cache mode/storage or tool charges; subtotal is partial.')
    return result
