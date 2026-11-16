"""Deterministic, source-bound creator actions. No inference, writes or winner calculation."""
from dataclasses import dataclass
import re
from typing import Any
from app.insights.comparison_models import ComparisonDecision
from app.insights.comparison_engine import validate_semantic_content
from app.insights.deterministic_scoring import normalize_metrics
from app.insights.recommendation_models import (
    RECOMMENDATION_POLICY, CreatorRecommendation, CreatorRecommendationBundle, RecommendationEvidence,
    WeaknessSignal, RecommendationPriority, RecommendationComparison, RecommendationFinding, CreativeExample,
)
from app.insights.recommendation_rules import RULES, RELEVANCE
from app.services.hash_service import hash_payload

CAUSAL_PROMISE = re.compile(r'\b(?:will|guarantee[sd]?)\b.{0,60}\b(?:increase|boost|improve|views|likes|retention|revenue)\b|\b(?:cause|caused|causes|proves)\b', re.I)

@dataclass
class RecommendationSubject:
    item: dict
    insight: Any
    identity: Any
    metrics: Any
    semantic_valid: bool = False


def metric_reference(subject, role='target'):
    identity=subject.identity
    values={**subject.metrics.counts, 'combined_engagement_percent':subject.metrics.rates_percent['combined_engagement'],
        'views_per_current_creator_size':subject.metrics.views_per_current_creator_size}
    return RecommendationEvidence(evidence_id='metric-'+hash_payload(dict(project_id=identity.project_id,
        content_id=identity.content_id,input_revision=identity.metric_input_revision)),project_id=identity.project_id,
        content_id=identity.content_id,slot=identity.slot,platform=identity.platform,role=role,source_type='metric_snapshot',
        metric_values=values,metric_provenance=subject.metrics.provenance,input_revision=identity.metric_input_revision)


def semantic_references(subject, feature):
    analysis=subject.insight.semantic_analysis
    sources={s['id']:s for s in analysis['evidence_sources']}
    return [RecommendationEvidence(evidence_id=r['evidence_id'],project_id=subject.identity.project_id,
        content_id=subject.identity.content_id,slot=subject.identity.slot,platform=subject.identity.platform,
        source_type=sources[r['evidence_id']]['source_type'],excerpt=r['excerpt'],start_time=r['start_time'],end_time=r['end_time'],
        input_revision=analysis['input_revision'],transcript_revision=subject.identity.transcript_revision,
        semantic_snapshot_id=analysis['snapshot_id']) for r in feature['evidence']]


def _comparison_context(decision, dimension=None):
    leader=decision.dimension_leaders.get(dimension) if dimension else None
    return RecommendationComparison(selected_objective_status=decision.eligibility.status,selected_outcome=decision.outcome.value,
        selected_winner_content_id=decision.winner_content_id,dimension=dimension,
        dimension_status=leader.eligibility.status if leader else None,dimension_outcome=leader.outcome.value if leader else None,
        dimension_values=leader.values if leader else {})


def _priority(severity, strength, relevance):
    score=severity+strength+relevance+1
    return RecommendationPriority(severity=severity,evidence_strength=strength,objective_relevance=relevance,
        action_directness=1,score=score,label='high' if score>=7 else 'medium' if score>=5 else 'low',
        explanation=f'Severity {severity} + source support {strength} + objective relevance {relevance} + directly testable action 1 = {score}; high >=7, medium >=5. This is a rule ranking, not a probability.')


def _finding(subject, category, observation, *, status='observed', evidence=None, missing=None, limitations=None):
    return RecommendationFinding(id=hash_payload(dict(target=subject.identity.content_id,category=category,observation=observation,
        revision=subject.identity.metric_input_revision,snapshot=subject.identity.semantic_snapshot_id)),
        target_content_id=subject.identity.content_id,target_slot=subject.identity.slot,category=category,status=status,
        observation=observation,evidence=evidence or [],missing_evidence=missing or [],limitations=limitations or [])


def _context_allows(rule, features):
    opening=features['opening_type']['value']
    if rule.context in {'problem','curiosity'}:return opening==rule.context
    if rule.context=='purpose':
        return opening in {'question','problem','introduction'} and features['audience_benefit']['value']=='clear' and features['topic_specificity']['value']=='clear'
    if rule.feature=='audience_specificity':return features['topic_specificity']['value'] in {'clear','partial'}
    return True


def _example(subject, features, category):
    if category not in {'opening_hook','topic_messaging','audience_relevance'} or features['topic_specificity']['value']!='clear':
        return None,[]
    refs=semantic_references(subject,features['topic_specificity'])
    for ref in refs:
        match=re.search(r'\b(?:Why|How|What|Which)\b[^?\n]{3,115}\?',ref.excerpt or '',re.I)
        if not match:continue
        question=match.group(0)
        # Do not promote a sourced prediction/causal claim into a suggested script.
        if CAUSAL_PROMISE.search(question) or re.search(r'guarante|retention|revenue|viral|moneti|\bviews\b|https?://',question,re.I):continue
        text=f'{question} Start this alternative with one brief answer, then the supporting explanation.'
        return CreativeExample(target_content_id=subject.identity.content_id,text=text,
            source_evidence_ids=[ref.evidence_id],limitation='Deterministic draft structure using this target’s cited question. Review factual wording and format fit; no test result is assumed.'),refs
    return None,[]


def _semantic_candidates(subject, decision):
    analysis=subject.insight.semantic_analysis
    features={f['feature']:f for f in analysis['features']['features']}
    candidates,findings=[],[]
    strength=2 if analysis.get('evidence_complete') else 1
    for rule in RULES:
        feature=features[rule.feature]
        if feature['status']!='assessed' or feature['value'] not in {'partial','absent'}:continue
        refs=semantic_references(subject,feature)
        if not refs:continue
        observation=f'Validated {rule.feature.replace("_"," ")} is {feature["value"]}; this is a semantic interpretation of the cited text.'
        findings.append(_finding(subject,rule.feature,observation,evidence=refs,
            limitations=['A rubric label is not a measured audience outcome.']))
        if not _context_allows(rule,features):
            findings.append(_finding(subject,rule.feature+'_context','No action generated: this intervention is not supported by the available format/purpose context.',status='not_assessable'))
            continue
        relevance=RELEVANCE[decision.selected_objective.value][rule.category]
        if relevance==0:continue
        severity=3 if feature['value']=='absent' else 1
        signal=WeaknessSignal(rule_id='semantic_'+rule.feature,feature=rule.feature,classification=feature['value'],observed_value=feature['value'],
            trigger='Assessed label is partial or absent, with source/type/revision validation and a matching context guard.',severity=severity,observation=observation)
        example,example_refs=_example(subject,features,rule.category)
        refs.extend(example_refs)
        candidates.append(CreatorRecommendation(id='',project_id=decision.project_id,target_content_id=subject.identity.content_id,
            target_slot=subject.identity.slot,target_platform=subject.identity.platform,selected_objective=decision.selected_objective,
            category=rule.category,intervention_group=rule.group,detected_weakness=observation,observed_signal=observation,
            evidence_status='valid' if strength==2 else 'partial',signals=[signal],evidence=refs,title=rule.title,
            recommended_change=rule.action,rationale=rule.rationale,experiment=rule.experiment,
            hypothesis='The alternative may change how viewers interpret or respond to the explanation. The direction and size are unknown until tested.',
            limitation='No causal performance effect, retention change or revenue outcome is established. A CTA or problem framework is optional and must fit the creator’s purpose.',
            priority=_priority(severity,strength,relevance),basis='individual_weakness',comparison=_comparison_context(decision,'creative_quality'),example=example))
    return candidates,findings


def _metric_opportunity(subjects, decision):
    """Consume the canonical engagement loser; never choose a target from legacy scores."""
    if decision.selected_objective.value!='engagement':return None
    leader=decision.dimension_leaders['engagement']
    if leader.eligibility.status!='eligible' or leader.outcome.value not in {'content_1','content_2'}:return None
    by_slot={s.identity.slot:s for s in subjects.values()}
    winner=by_slot.get(leader.winner_slot)
    target=by_slot.get('content_2' if leader.winner_slot=='content_1' else 'content_1')
    if not winner or not target or leader.winner_content_id!=winner.identity.content_id:return None
    if any(leader.values.get(s.identity.slot)!=s.metrics.rates_percent['combined_engagement'] for s in (winner,target)):return None
    value=target.metrics.rates_percent['combined_engagement']
    observation=f'Observed combined engagement is {value:.4f}% versus {winner.metrics.rates_percent["combined_engagement"]:.4f}% under the eligible canonical comparison. This is not evidence of a creative defect.'
    signal=WeaknessSignal(rule_id='eligible_engagement_opportunity',feature='combined_engagement_percent',classification='lower_observed_rate',observed_value=value,
        trigger='Selected Engagement objective; canonical eligible non-tie outcome; complete interaction definition and >=1000 views per content.',severity=1,observation=observation)
    return CreatorRecommendation(id='',project_id=decision.project_id,target_content_id=target.identity.content_id,target_slot=target.identity.slot,
        target_platform=target.identity.platform,selected_objective=decision.selected_objective,category='engagement_opportunity',intervention_group='viewer_response',
        detected_weakness='Comparative interaction opportunity; no creative mechanism established.',observed_signal=observation,evidence_status='partial',signals=[signal],
        evidence=[metric_reference(target),metric_reference(winner,'comparison_context')],title='Run a controlled interaction experiment',
        recommended_change='On two otherwise comparable posts, vary only the wording of one on-topic viewer question; treat this as an experiment, not a correction of a proven defect.',
        rationale='The eligible observed rate gap supports testing response wording, but public counts do not explain the gap.',
        experiment='Keep topic, format and observation window as similar as practicable. Compare two question wordings using the same platform interaction definition after each reaches at least 1,000 views.',
        hypothesis='The alternative may produce a different observed public interaction rate; its direction and magnitude are unknown.',
        limitation='This is a proposed manual experiment, not a built-in A/B testing feature. Publication context, repeated views and audiences may differ; comments do not establish positive sentiment.',
        priority=_priority(1,1,2),basis='comparative_opportunity',comparison=_comparison_context(decision,'engagement'))


def _validate_recommendation_evidence(recommendation, subjects, decision):
    """Fail closed on target swaps, stale references or unsupported action promises."""
    r=recommendation
    subject=subjects.get(r.target_content_id)
    if not subject or r.project_id!=decision.project_id or r.selected_objective!=decision.selected_objective or r.policy_version!=RECOMMENDATION_POLICY:
        raise ValueError('Recommendation context mismatch.')
    if r.target_slot!=subject.identity.slot or r.target_platform!=subject.identity.platform:
        raise ValueError('Recommendation target identity mismatch.')
    if r.comparison != _comparison_context(decision,r.comparison.dimension):
        raise ValueError('Comparison context does not match the canonical decision.')
    own=False
    for ref in r.evidence:
        owner=subjects.get(ref.content_id)
        if not owner or ref.project_id!=decision.project_id or ref.slot!=owner.identity.slot or ref.platform!=owner.identity.platform:
            raise ValueError('Evidence ownership mismatch.')
        is_target=ref.content_id==r.target_content_id
        if is_target and ref.role!='target' or not is_target and (ref.role!='comparison_context' or r.basis!='comparative_opportunity' or r.comparison.dimension_status!='eligible'):
            raise ValueError('Cross-content evidence lacks explicit comparative context.')
        own=own or is_target
        if ref.source_type=='metric_snapshot':
            if ref!=metric_reference(owner,ref.role):raise ValueError('Metric evidence is stale or fabricated.')
        else:
            if not owner.semantic_valid:raise ValueError('Semantic evidence is not current.')
            analysis=owner.insight.semantic_analysis
            source=next((s for s in analysis['evidence_sources'] if s['id']==ref.evidence_id),None)
            if not source or ref.source_type!=source['source_type'] or not ref.excerpt or ref.excerpt not in source['text']:
                raise ValueError('Unsupported semantic excerpt.')
            if ref.start_time!=source['start_time'] or ref.end_time!=source['end_time'] or ref.input_revision!=analysis['input_revision'] or ref.transcript_revision!=owner.identity.transcript_revision or ref.semantic_snapshot_id!=analysis['snapshot_id']:
                raise ValueError('Stale semantic evidence or fabricated timing.')
    if not own:raise ValueError('Action requires target evidence.')
    if r.example:
        own_ids={e.evidence_id for e in r.evidence if e.role=='target'}
        if r.example.target_content_id!=r.target_content_id or not set(r.example.source_evidence_ids).issubset(own_ids):
            raise ValueError('Creative example uses another content.')
    proposed=' '.join([r.detected_weakness,r.observed_signal,*[signal.observation for signal in r.signals],r.title,r.recommended_change,r.rationale,r.experiment,r.hypothesis,r.example.text if r.example else ''])
    if CAUSAL_PROMISE.search(proposed):raise ValueError('Unsupported causal or guaranteed outcome claim.')
    return r


def validate_recommendation(recommendation, subjects, decision):
    """Validate untrusted output against current deterministic recommendation assembly.

    Replays only the bounded recommendation rules over supplied snapshots, without
    inference, repository reads, scoring or comparison recalculation. Internal
    assembly uses the evidence validator directly to avoid recursive validation.
    """
    _validate_recommendation_evidence(recommendation, subjects, decision)
    canonical = build_creator_recommendations(
        decision.project_id, decision, [(s.item, s.insight) for s in subjects.values()]
    )
    current = next((r for r in canonical.recommendations if r.id == recommendation.id), None)
    if current is None:
        raise ValueError('Recommendation is not present in the current canonical output.')
    if recommendation.model_dump(mode='json') != current.model_dump(mode='json'):
        raise ValueError('Recommendation fields or full priority breakdown differ from the canonical output.')
    return recommendation


def _merge_and_limit(candidates, subjects, decision):
    groups={}
    for r in sorted(candidates,key=lambda x:(-x.priority.score,x.target_content_id,x.signals[0].rule_id)):
        key=(r.target_content_id,r.intervention_group)
        if key not in groups:
            groups[key]=r.model_copy(deep=True)
        else:
            kept=groups[key]
            kept.signals.extend(r.signals)
            kept.evidence.extend(r.evidence)
            if r.basis=='comparative_opportunity':
                kept.basis=r.basis;kept.comparison=r.comparison
                kept.limitation+=' '+r.limitation
    eligible=[]
    for r in groups.values():
        r.signals=sorted({s.rule_id:s for s in r.signals}.values(),key=lambda s:s.rule_id)
        r.evidence=sorted({e.model_dump_json():e for e in r.evidence}.values(),key=lambda e:(e.role,e.content_id,e.evidence_id,e.excerpt or ''))
        r.id=hash_payload(dict(policy=RECOMMENDATION_POLICY,project=decision.project_id,target=r.target_content_id,
            objective=decision.selected_objective.value,group=r.intervention_group,rules=[s.rule_id for s in r.signals],evidence=[e.model_dump(mode='json') for e in r.evidence]))
        try:eligible.append(_validate_recommendation_evidence(r,subjects,decision))
        except ValueError:continue
    ordered=sorted(eligible,key=lambda r:(-r.priority.score,r.target_content_id,r.intervention_group,r.id))
    displayed=[];per_target={}
    for r in ordered:
        if len(displayed)<5 and per_target.get(r.target_content_id,0)<3:
            displayed.append(r);per_target[r.target_content_id]=per_target.get(r.target_content_id,0)+1
    return displayed,max(0,len(candidates)-len(groups)),len(eligible)-len(displayed)


def build_creator_recommendations(project_id: str, decision: ComparisonDecision, contents: list[tuple[dict | None, Any]]) -> CreatorRecommendationBundle:
    bundle=CreatorRecommendationBundle(project_id=project_id,selected_objective=decision.selected_objective,
        decision_policy_version=decision.decision_policy_version,status='unavailable')
    if decision.project_id!=project_id or decision.decision_policy_version!='goal-comparison-1.0.0':
        bundle.limitations=['A supported canonical comparison contract is required.'];return bundle
    identities={x.slot:x for x in (decision.content_1,decision.content_2)}
    ids=[x.content_id for x in identities.values() if x.content_id]
    if len(ids)!=len(set(ids)):
        bundle.limitations=['Distinct stable content identities are required.'];return bundle
    subjects={};findings=[];candidates=[]
    for item,insight in contents:
        if not item:continue
        identity=identities.get(item.get('slot'))
        metrics=normalize_metrics(item)
        raw_id=item.get('id') or item.get('content_item_id') or item.get('content_id')
        if not identity or not identity.content_id or raw_id!=identity.content_id or identity.project_id!=project_id or item.get('project_id',project_id)!=project_id or identity.platform!=metrics.platform or identity.metric_input_revision!=hash_payload(metrics.model_dump(mode='json')):
            bundle.limitations.append('A content input was omitted because its identity or metric revision does not match the canonical decision.');continue
        subject=RecommendationSubject(item,insight,identity,metrics)
        subjects[identity.content_id]=subject
        problem=validate_semantic_content(project_id,item,insight)
        analysis=getattr(insight,'semantic_analysis',{}) or {}
        if problem is None and (identity.semantic_snapshot_id!=analysis.get('snapshot_id') or identity.semantic_input_revision!=analysis.get('input_revision') or identity.transcript_revision!=(item.get('transcript_evidence') or {}).get('revision')):
            problem=('insufficient_evidence','Semantic evidence changed after the canonical decision was assembled.')
        subject.semantic_valid=problem is None
        if problem:
            findings.append(_finding(subject,'semantic_evidence',problem[1],status='not_assessable',missing=['Current individually validated semantic features']))
        else:
            detected,notes=_semantic_candidates(subject,decision);candidates.extend(detected);findings.extend(notes)
        if metrics.missing_inputs:
            findings.append(_finding(subject,'metric_evidence','Some platform-defined public metrics are unavailable; missing values are not poor performance.',status='not_assessable',missing=metrics.missing_inputs))
    for subject in subjects.values():
        identity=subject.identity
        for dimension,category in [('observed_reach','reach_observation'),('engagement','engagement_observation'),('creator_efficiency','efficiency_observation')]:
            leader=decision.dimension_leaders[dimension]
            value=leader.values.get(identity.slot)
            note=f'{leader.metric}: {value if value is not None else "unavailable"} {leader.units}. Canonical dimension outcome: {leader.outcome.value}. This does not identify a creative cause.'
            refs=[metric_reference(subject)] if value is not None else []
            refs.extend(metric_reference(peer,'comparison_context') for peer in subjects.values() if peer.identity.content_id!=identity.content_id and leader.values.get(peer.identity.slot) is not None)
            findings.append(_finding(subject,category,note,status='observed' if leader.eligibility.status=='eligible' else 'incomparable' if leader.eligibility.status=='incomparable' else 'not_assessable',
                evidence=refs,missing=leader.eligibility.missing_evidence,limitations=leader.limitations))
    comparative=_metric_opportunity(subjects,decision)
    if comparative:candidates.append(comparative)
    recommendations,merged,omitted=_merge_and_limit(candidates,subjects,decision)
    bundle.recommendations=recommendations;bundle.detected_candidates=len(candidates);bundle.merged_candidates=merged;bundle.omitted_by_display_limit=omitted
    bundle.findings=sorted({f.id:f for f in findings}.values(),key=lambda f:(f.target_content_id or '',f.category,f.id))[:24]
    bundle.status='ready' if recommendations else 'no_supported_actions' if subjects else 'unavailable'
    bundle.limitations.extend(['Recommendations are proposed experiments, not measured causal effects or performance guarantees.',
        'Selected objective outcome: '+decision.outcome.value+'. Independent findings do not substitute another objective winner.',
        'No semantic inference or evidence refresh is triggered by this response.'])
    return bundle
