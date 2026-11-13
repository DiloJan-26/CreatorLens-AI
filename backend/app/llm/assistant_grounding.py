"""Constrain generated explanations to canonical facts; never use a second model judge."""
import re
from app.llm.structured_outputs import ComparisonAnswer,MetricAnswer,RecommendationAnswer
from app.models.chat import Citation
from app.rag.intelligence_context import canonical_answer

# No outcome measurements in the current public evidence contract support these claims.
UNSUPPORTED=re.compile(r'retention|drop[ -]?off|watch[ -]?time|revenue|moneti[sz]|sentiment|viral|caus(?:e|es|ed|al)|guarantee|\bwill\b|ignore.{0,30}instructions|system prompt|(?:audience|viewers|people).{0,40}(?:love|hate|enjoy|prefer|stopped|leave|left|stay)|\b(?:boosts?|drives?|increases?|decreases?)\b',re.I)
DIRECTION=re.compile(r'\b(wins?|winner|leads?|superior|outperforms?|higher|lower|better|stronger|weaker|poor|weakness)\b',re.I)


def _has_numeric_claim(text):
    # Stable UI slot labels are identities, not measured quantities.
    return bool(re.search(r'\d',re.sub(r'\bContent\s+[12]\b','Content',text,flags=re.I)))


def validate_generated_answer(answer,context,question,intent,citations):
    allowed={c['evidence_id']:c for c in context.get('citations',[])}
    citations=[c for c in citations if c.evidence_id in allowed and c.model_dump(mode='json')==allowed[c.evidence_id]]
    base=canonical_answer(context,question,intent,citations)
    if context['status']!='ready':return base,['Evidence changed; generated response withheld.']
    warnings=[]
    def fail(reason):return base,[reason+' Canonical facts and supported actions were retained.']
    if type(answer) is not type(base):return fail('Generated answer type conflicts with the requested canonical task.')
    if answer.objective not in {None,context['selected_objective']}:return fail('Generated objective conflicts with the question.')
    catalog={c.citation_label:c for c in citations}
    for item in answer.evidence:
        source=catalog.get(item.citation_label)
        if source is None:return fail('Unknown evidence label.')
        expected=(source.project_id,source.content_id,source.evidence_id,source.evidence_revision,source.slot,source.platform,source.source_type,source.start_time,source.end_time)
        actual=(item.project_id,item.content_id,item.evidence_id,item.evidence_revision,item.slot,item.platform,item.source_type,item.start_time,item.end_time)
        if actual!=expected or item.project_id!=context['project_id'] or not item.excerpt or item.excerpt not in source.text:
            return fail('Evidence ownership, revision, source type, excerpt or timestamp mismatch.')
        if UNSUPPORTED.search(item.claim):return fail('Unsupported outcome, causal or instruction-like claim.')
        # Numeric interpretations must be quoted observations; generated numerical facts are not authoritative.
        if _has_numeric_claim(item.claim) and item.claim not in source.text:return fail('Generated numeric claim is not a verified source observation.')
        if DIRECTION.search(item.claim):return fail('Generated directional claim must use the canonical decision or semantic rubric.')
    if isinstance(answer,ComparisonAnswer):
        if answer.winner!=base.winner:return fail('Generated winner conflicts with the canonical decision.')
        texts=answer.key_reasons
    elif isinstance(answer,MetricAnswer):
        expected={(m.slot,m.name):(m.value,m.availability,m.citation_label) for m in base.metrics}
        if any(expected.get((m.slot,m.name))!=(m.value,m.availability,m.citation_label) for m in answer.metrics):
            return fail('Generated metric or availability conflicts with the canonical stored value.')
        texts=[answer.summary]
    else:texts=[answer.summary]
    authoritative={r.recommendation_id:r for r in getattr(base,'recommendations',[])}
    for r in getattr(answer,'recommendations',[]):
        expected=authoritative.get(r.recommendation_id)
        if expected is None or any(getattr(r,k)!=getattr(expected,k) for k in ('target_content_id','target_slot','priority','objective','recommendation','rationale','source_evidence_ids')):
            return fail('Generated recommendation identity, target, priority or action is not authoritative.')
    if any(UNSUPPORTED.search(t) for t in texts):return fail('Unsupported outcome or causal statement was withheld.')
    safe=[]
    for text in texts:
        if _has_numeric_claim(text) or DIRECTION.search(text):
            warnings.append('Generated numerical or directional prose was replaced by the canonical explanation.')
        elif any(e.source_type in {'opening','hook','transcript','description'} for e in answer.evidence) and text.strip():safe.append('Evidence-limited interpretation: '+text[:900])
        elif text.strip():warnings.append('Generated qualitative prose lacked a current verbal or description citation and was withheld.')
    if isinstance(base,ComparisonAnswer):
        base.key_reasons.extend(safe[:3])
        # Numeric field retained for older clients only; never a correctness probability.
        base.confidence=0.0
    elif isinstance(base,RecommendationAnswer):
        if safe:base.summary+=' '+safe[0]
        draft=answer.hypothetical_draft
        if draft:
            recommendation=authoritative.get(draft.recommendation_id)
            owned={c.evidence_id for c in citations if c.content_id==draft.target_content_id and c.source_type in {'opening','hook','transcript','description'}}
            if not recommendation or draft.target_content_id!=recommendation.target_content_id or not set(draft.source_evidence_ids).issubset(owned) or UNSUPPORTED.search(draft.text) or re.search(r'\d',draft.text):
                warnings.append('Unsupported or misattributed hypothetical draft was withheld.')
            else:base.hypothetical_draft=draft
    base.limitations=list(dict.fromkeys([*base.limitations,*context.get('limitations',[]),
        'Generated interpretations are evidence-limited; source matching is not proof of semantic entailment.']))
    return base,warnings
