"""One pure decision engine. Reads validated snapshots; never queues or invokes inference."""
from dataclasses import dataclass
from typing import Any
from decimal import Decimal
from fractions import Fraction
import math
import json
from app.services.hash_service import hash_payload
from app.insights.semantic_evidence import parse_features
from app.insights.comparison_models import (
    ComparisonObjective, ComparisonDecision, ComparisonEligibility, ComparisonIdentity,
    ComparisonPolicy, DimensionLeader, DecisionOutcome,
)
from app.insights.deterministic_scoring import normalize_metrics
from app.insights.scoring_models import POLICY_VERSION, CreatorMetrics, CreatorScoring, ScoreBreakdown, ScoringPolicy
from app.insights.semantic_models import CREATIVE_POLICY, SCHEMA_VERSION, PROMPT_VERSION, CreativeFeatures

POLICY = ComparisonPolicy()
SEMANTIC_SCORING_POLICY = 'creator-insight-semantic-1.0.0'
SUPPORTED_PLATFORMS = {'youtube','instagram','facebook'}
OBJECTIVE_DIMENSIONS = {
    ComparisonObjective.BALANCED:'balanced', ComparisonObjective.REACH:'observed_reach',
    ComparisonObjective.ENGAGEMENT:'engagement', ComparisonObjective.CREATIVE_QUALITY:'creative_quality',
}

@dataclass
class Subject:
    item: dict
    insight: Any
    identity: ComparisonIdentity
    metrics: CreatorMetrics


def _subject(project_id: str, slot: str, item: dict | None, insight: Any) -> Subject:
    item = item or {}
    metrics = normalize_metrics(item)
    content_id = item.get('id') or item.get('content_item_id') or item.get('content_id')
    content_id = content_id.strip() if isinstance(content_id,str) else None
    analysis = getattr(insight, 'semantic_analysis', {}) or {}
    identity = ComparisonIdentity(slot=slot, content_id=str(content_id) if content_id else None,
        project_id=str(item.get('project_id') if 'project_id' in item else project_id), platform=metrics.platform,
        metric_provenance=metrics.provenance,
        metric_input_revision=hash_payload(metrics.model_dump(mode='json')),
        ownership_source='content_project_id' if 'project_id' in item else 'summary_project_membership',
        transcript_revision=(item.get('transcript_evidence') or {}).get('revision'),
        semantic_snapshot_id=analysis.get('snapshot_id'), semantic_input_revision=analysis.get('input_revision'),
        publication_date=metrics.publication_date, observed_at=metrics.observed_at, age_days=metrics.age_days)
    return Subject(item, insight, identity, metrics)


def _available(score: ScoreBreakdown | None) -> bool:
    return score is not None and score.score is not None and math.isfinite(score.score) and score.status in {'assessable','partial'}


def _mask(score):
    return tuple(sorted((p.feature, round(p.weight,12)) for p in score.components if p.score is not None and p.weight > 0))


def _base(subject: Subject) -> CreatorScoring | None:
    return getattr(subject.insight, 'scoring', None)


def _semantic(subject: Subject) -> CreatorScoring | None:
    return getattr(subject.insight, 'semantic_scoring', None)


def _semantic_problem(subject, *, require_score=True):
    """Semantic read service validates current fingerprint/text; also bind identity and policy here."""
    score = _semantic(subject)
    analysis = getattr(subject.insight, 'semantic_analysis', {}) or {}
    if analysis.get('status') != 'ready' or score is None:
        return 'insufficient_evidence', 'Ready semantic snapshot required.'
    if score.policy.version != SEMANTIC_SCORING_POLICY or score.creative_policy_version != CREATIVE_POLICY or score.creative_structure.policy_version != CREATIVE_POLICY:
        return 'incomparable', 'Unsupported semantic scoring policy.'
    if score.metric_policy_version != POLICY_VERSION:
        return 'incomparable', 'Unsupported referenced metric policy.'
    if not analysis.get('snapshot_id') or analysis['snapshot_id'] != score.semantic_snapshot_id:
        return 'insufficient_evidence', 'Semantic snapshot identity is missing or stale.'
    if not subject.identity.transcript_revision or score.evidence.transcript_revision != subject.identity.transcript_revision:
        return 'insufficient_evidence', 'Semantic transcript revision is missing or stale.'
    if any(not analysis.get(key) for key in ('creative_policy','schema_version','prompt_version','model_id')):
        return 'insufficient_evidence', 'Semantic version/model metadata is missing.'
    if analysis.get('creative_policy') != CREATIVE_POLICY or analysis.get('schema_version') != SCHEMA_VERSION or analysis.get('prompt_version') != PROMPT_VERSION or not analysis.get('model_id'):
        return 'incomparable', 'Semantic analysis versions/model are unsupported or incomplete.'
    try:
        features = CreativeFeatures.model_validate(analysis.get('features'))
    except ValueError:
        return 'insufficient_evidence', 'Validated semantic features are missing.'
    if (features.content_id != subject.identity.content_id or features.project_id != subject.identity.project_id
            or features.slot != subject.identity.slot or features.input_revision != analysis.get('input_revision')):
        return 'insufficient_evidence', 'Semantic feature ownership/input revision mismatch.'
    try:
        sources = analysis.get('evidence_sources', [])
        for source in sources:
            if (source.get('content_id') != subject.identity.content_id or source.get('project_id') != subject.identity.project_id
                    or source.get('slot') != subject.identity.slot or source.get('platform') != subject.identity.platform):
                return 'insufficient_evidence', 'Semantic evidence source ownership is invalid.'
        parse_features(json.dumps(analysis['features']), dict(project_id=subject.identity.project_id,
            content_id=subject.identity.content_id,slot=subject.identity.slot,input_revision=analysis['input_revision'],
            sources=sources,complete=analysis.get('evidence_complete',False)))
    except (ValueError, TypeError, KeyError, AttributeError):
        return 'insufficient_evidence', 'Semantic citation/type/text/timing or coverage validation failed.'
    if require_score and (not _available(score.creative_structure) or score.creative_structure.coverage < .70 or not {"verbal_hook_clarity","topic_specificity"}.issubset({p.feature for p in score.creative_structure.components if p.score is not None and p.weight > 0})):
        return 'insufficient_evidence', 'Semantic creative score lacks required feature coverage.'
    return None


def validate_comparison_eligibility(project_id: str, left: Subject, right: Subject, dimension: str) -> ComparisonEligibility:
    missing, incompatible = [], []
    for subject in (left,right):
        identity = subject.identity
        if not identity.content_id:
            missing.append(f'{identity.slot}: content identity unavailable.')
        if not subject.item:
            continue
        if subject.item.get('slot') != identity.slot or identity.project_id != project_id:
            incompatible.append(f'{identity.slot}: content does not belong to the requested project/slot.')
        if subject.insight is not None and (subject.insight.slot != identity.slot or subject.insight.platform != identity.platform):
            incompatible.append(f'{identity.slot}: insight identity conflicts with content source.')
        if identity.platform not in SUPPORTED_PLATFORMS:
            incompatible.append(f'{identity.slot}: platform identity is unsupported.')
    if left.identity.content_id and left.identity.content_id == right.identity.content_id:
        incompatible.append('Content identities must be distinct.')
    if left.item.get('url') and left.item.get('url') == right.item.get('url') and left.identity.platform == right.identity.platform:
        incompatible.append('Both slots reference the same public content URL.')
    if incompatible or missing:
        return ComparisonEligibility(status='incomparable' if incompatible else 'insufficient_evidence', reasons=incompatible or missing, missing_evidence=missing)
    # Creative execution uses a shared textual rubric; metric objectives require same-platform units.
    if dimension != 'creative_quality' and left.identity.platform != right.identity.platform:
        incompatible.append('Cross-platform metric definitions/audiences are not equivalent; descriptive observations only.')
    for subject in (left,right):
        slot = subject.identity.slot
        if dimension == 'observed_reach':
            if subject.metrics.counts['views'] is None:
                missing.append(f'{slot}: confirmed views unavailable or invalid.')
        elif dimension in {'engagement','public_performance'}:
            if subject.metrics.engagement_status != 'eligible' or (subject.metrics.counts['views'] or 0) < POLICY.minimum_engagement_views:
                missing.append(f'{slot}: engagement needs >=1000 views and complete, consistent platform interactions.')
        if dimension in {'creator_efficiency','public_performance'}:
            score = _base(subject)
            if score is None:
                missing.append(f'{slot}: versioned metric scoring unavailable.')
            elif score.metric_policy_version != POLICY_VERSION or score.policy.version != POLICY_VERSION:
                incompatible.append(f'{slot}: incompatible metric scoring policy.')
            elif getattr(score, dimension).policy_version != POLICY_VERSION:
                incompatible.append(f'{slot}: component scoring policy mismatch.')
            elif score.metrics != subject.metrics:
                missing.append(f'{slot}: score inputs do not match current metrics.')
            elif not _available(getattr(score,dimension)):
                missing.append(f'{slot}: {dimension} is not assessable.')
        if dimension in {'creative_quality','balanced'}:
            problem = _semantic_problem(subject)
            if problem:
                (incompatible if problem[0] == 'incomparable' else missing).append(f'{slot}: {problem[1]}')
            if dimension == 'balanced':
                semantic = _semantic(subject)
                if semantic is None or not _available(semantic.overall) or not _available(semantic.public_performance):
                    missing.append(f'{slot}: eligible semantic overall and public-performance scores required.')
                elif semantic.metrics != subject.metrics or subject.metrics.engagement_status != 'eligible' or (subject.metrics.counts['views'] or 0) < POLICY.minimum_engagement_views:
                    missing.append(f'{slot}: balanced score metrics are stale or ineligible.')
                elif not {'public_performance','creative_structure'}.issubset({p.feature for p in semantic.overall.components if p.score is not None and p.weight > 0}):
                    missing.append(f'{slot}: balanced component eligibility metadata is incomplete.')
                elif semantic.policy.overall_weights != ScoringPolicy().overall_weights or semantic.policy.performance_weights != ScoringPolicy().performance_weights:
                    incompatible.append(f'{slot}: weights do not match the referenced scoring policy.')
                elif semantic.overall.policy_version != SEMANTIC_SCORING_POLICY:
                    incompatible.append(f'{slot}: overall scoring policy mismatch.')
    if dimension in {'engagement','public_performance','balanced'} and left.metrics.interaction_definition != right.metrics.interaction_definition:
        incompatible.append('Interaction definitions differ.')
    if dimension in {'creative_quality','balanced'} and _semantic(left) is not None and _semantic(right) is not None:
        a,b = _semantic(left),_semantic(right)
        if _mask(a.creative_structure) != _mask(b.creative_structure):
            incompatible.append('Semantic creative feature masks/effective weights differ.')
        la,ra = left.insight.semantic_analysis,right.insight.semantic_analysis
        if la.get('model_id') != ra.get('model_id') or la.get('prompt_version') != ra.get('prompt_version'):
            incompatible.append('Semantic model/prompt versions differ.')
        if dimension == 'balanced' and (_mask(a.overall) != _mask(b.overall) or a.policy.overall_weights != b.policy.overall_weights or a.policy.performance_weights != b.policy.performance_weights):
            incompatible.append('Balanced eligible component masks/effective weights differ.')
    return ComparisonEligibility(status='incomparable' if incompatible else 'insufficient_evidence' if missing else 'eligible',
        reasons=incompatible + missing, missing_evidence=missing)


def _values(subject, dimension):
    if dimension == 'observed_reach':return subject.metrics.counts['views']
    if dimension == 'engagement':return subject.metrics.rates_percent['combined_engagement']
    scores = _semantic(subject) if dimension in {'creative_quality','balanced'} else _base(subject)
    name = 'creative_structure' if dimension == 'creative_quality' else 'overall' if dimension == 'balanced' else dimension
    return getattr(scores,name).score if scores else None


def _breakdown(subject, dimension):
    scores = _semantic(subject) if dimension in {'creative_quality','balanced'} else _base(subject)
    if scores is None or dimension in {'observed_reach','engagement'}:return []
    field = 'creative_structure' if dimension == 'creative_quality' else 'overall' if dimension == 'balanced' else dimension
    return [p.model_dump(mode='json') for p in getattr(scores,field).components]


def _difference(left,right,dimension,values):
    if None in values:return None
    if dimension == 'observed_reach':return values[0]-values[1]
    if dimension == 'engagement':
        a,b=left.metrics,right.metrics
        if not a.counts['views'] or not b.counts['views'] or a.interactions is None or b.interactions is None:return None
        return Fraction(100*a.interactions,a.counts['views'])-Fraction(100*b.interactions,b.counts['views'])
    return Decimal(str(values[0]))-Decimal(str(values[1]))


def _leader(project_id,left,right,dimension):
    eligibility = validate_comparison_eligibility(project_id,left,right,dimension)
    values = [_values(left,dimension),_values(right,dimension)]
    diff = _difference(left,right,dimension,values)
    tolerance = POLICY.reach_tie_views if dimension == 'observed_reach' else POLICY.engagement_tie_percentage_points if dimension == 'engagement' else POLICY.score_tie_points
    boundary = Fraction(str(tolerance)) if dimension == 'engagement' else Decimal(str(tolerance))
    descriptive = None
    # Descriptive raw leaders are supplementary and require valid distinct ownership.
    identity_valid = all(s.identity.content_id and s.identity.project_id == project_id and s.item.get('slot') == s.identity.slot and s.identity.platform in SUPPORTED_PLATFORMS for s in (left,right)) and left.identity.content_id != right.identity.content_id
    identity_valid = identity_valid and not any('identity' in r or 'belong' in r or 'same public content' in r for r in eligibility.reasons)
    if identity_valid and diff is not None and diff != 0 and (dimension == 'observed_reach' or dimension == 'engagement' and eligibility.status == 'eligible'):
        descriptive = 'content_1' if diff > 0 else 'content_2'
    outcome = DecisionOutcome.INCOMPARABLE if eligibility.status == 'incomparable' else DecisionOutcome.INSUFFICIENT
    winner = None
    if eligibility.status == 'eligible':
        outcome = DecisionOutcome.TIE if abs(diff) <= boundary else DecisionOutcome.CONTENT_1 if diff > 0 else DecisionOutcome.CONTENT_2
        if outcome in {DecisionOutcome.CONTENT_1,DecisionOutcome.CONTENT_2}:winner=outcome.value
    units = 'views' if dimension == 'observed_reach' else 'percent' if dimension == 'engagement' else 'points_out_of_10'
    limitations = list(dict.fromkeys(left.metrics.limitations + right.metrics.limitations))
    if dimension in {'creative_quality','balanced'}:
        for subject in (left,right):
            limitations.extend((getattr(subject.insight, 'semantic_analysis', {}) or {}).get('limitations', []))
    for subject in (left,right):
        limitations.extend((subject.item.get('transcript_evidence') or {}).get('issues') or []) if dimension in {'creative_quality','balanced'} else None
    if left.metrics.publication_date != right.metrics.publication_date:
        limitations.append('Publication dates differ or are incomplete; lifetime counts are not growth velocity.')
    if not left.metrics.observed_at or not right.metrics.observed_at or left.metrics.observed_at != right.metrics.observed_at:
        limitations.append('Observation timestamps differ or are unavailable; simultaneous measurement is not established.')
    if dimension != 'observed_reach':limitations.append('Tie tolerance is an uncalibrated policy threshold, not statistical significance.')
    if dimension == 'engagement':limitations.append('Interactions do not establish retention or positive audience sentiment.')
    if dimension == 'creator_efficiency':limitations.append('Current-audience normalization is not historical conversion or proof of virality.')
    if dimension in {'creative_quality','balanced'}:limitations.append('Semantic rubric scores are heuristic textual interpretations, not measured retention, virality or revenue.')
    metric = {'observed_reach':'confirmed_lifetime_views','engagement':'complete_combined_engagement_rate',
        'creator_efficiency':'audience_normalized_reach_score','public_performance':'public_performance_score',
        'creative_quality':'semantic_creative_score','balanced':'semantic_overall_score'}[dimension]
    label = 'descriptive' if dimension in {'observed_reach','engagement'} else 'heuristic'
    criterion = f'{metric}: Content 1={values[0]}, Content 2={values[1]} {units}.'
    if outcome == DecisionOutcome.TIE:
        explanation = f'{dimension}: tie under the {label} policy (absolute difference <= {tolerance}). {criterion}'
    elif winner:
        explanation = f'{dimension}: {winner} leads under the {label} policy. {criterion}'
    else:
        explanation = f'{dimension}: {outcome.value}. ' + ' '.join(eligibility.reasons) + f' {criterion}'
    explanation += ' ' + ('Lifetime views are not unique viewers or growth velocity.' if dimension == 'observed_reach' else 'This does not establish retention, sentiment, revenue or causal performance.')
    differences = []
    if dimension in {'creative_quality','balanced'} and _semantic(left) and _semantic(right):
        a={p.feature:p for p in _semantic(left).creative_structure.components}
        b={p.feature:p for p in _semantic(right).creative_structure.components}
        for feature in sorted(set(a)&set(b)):
            if a[feature].score != b[feature].score:
                differences.append(dict(feature=feature,content_1=a[feature].model_dump(mode='json'),content_2=b[feature].model_dump(mode='json')))
    ids={s.identity.slot:s.identity.content_id for s in (left,right)}
    refs = {}
    if dimension in {'creative_quality','balanced'}:
        for subject in (left,right):
            if _semantic_problem(subject) is None:
                refs[subject.identity.slot] = [dict(feature=f['feature'], **ref) for f in subject.insight.semantic_analysis['features']['features'] for ref in f['evidence']]
    return DimensionLeader(dimension=dimension, metric=metric, interpretation=label, eligibility=eligibility,
        outcome=outcome,winner_slot=winner,winner_content_id=ids[winner] if winner else None,
        descriptive_leader_slot=descriptive, values=dict(zip(('content_1','content_2'),values)),
        difference_content_1_minus_content_2=float(diff) if dimension != 'observed_reach' and diff is not None else diff,
        units=units,difference_units='views' if dimension == 'observed_reach' else 'percentage_points' if dimension == 'engagement' else 'score_points',tie_tolerance=tolerance,contributions={s.identity.slot:_breakdown(s,dimension) for s in (left,right)},
        feature_differences=differences, evidence_references=refs, explanation=explanation,limitations=list(dict.fromkeys(limitations)))


def build_goal_comparison(project_id: str, content_1: dict | None, content_2: dict | None, insight_1: Any, insight_2: Any, objective: ComparisonObjective | str = ComparisonObjective.BALANCED) -> ComparisonDecision:
    objective = ComparisonObjective(objective)
    left,right=_subject(project_id,'content_1',content_1,insight_1),_subject(project_id,'content_2',content_2,insight_2)
    leaders={name:_leader(project_id,left,right,name) for name in
        ('observed_reach','engagement','creator_efficiency','creative_quality','public_performance','balanced')}
    objectives={obj:leaders[dimension] for obj,dimension in OBJECTIVE_DIMENSIONS.items()}
    selected=objectives[objective]
    return ComparisonDecision(project_id=project_id,selected_objective=objective,metric_policy_version=POLICY_VERSION,
        creative_policy_version=CREATIVE_POLICY if objective in {ComparisonObjective.BALANCED,ComparisonObjective.CREATIVE_QUALITY} else None,
        content_1=left.identity,content_2=right.identity,eligibility=selected.eligibility,outcome=selected.outcome,
        winner_slot=selected.winner_slot,winner_content_id=selected.winner_content_id,
        objective_units=selected.units, difference_content_1_minus_content_2=selected.difference_content_1_minus_content_2, difference_units=selected.difference_units,
        raw_objective_values=selected.values,eligible_scoring_inputs={s.identity.slot: ((['views'] if objective == ComparisonObjective.REACH else ['views',*s.metrics.interaction_definition]) if selected.eligibility.status == 'eligible' and objective in {ComparisonObjective.REACH,ComparisonObjective.ENGAGEMENT} else [p['feature'] for p in selected.contributions.get(s.identity.slot,[]) if p['score'] is not None and p['weight'] > 0]) for s in (left,right)},
        key_contributions=selected.contributions,explanation=selected.explanation,missing_evidence=selected.eligibility.missing_evidence,
        limitations=selected.limitations,objective_decisions=objectives,dimension_leaders=leaders)


def validate_semantic_content(project_id: str, item: dict, insight: Any):
    """Validate individual semantic evidence without requiring a comparable aggregate score."""
    slot = item.get('slot')
    if slot not in {'content_1','content_2'}:
        return 'insufficient_evidence', 'Content slot is invalid.'
    subject = _subject(project_id, slot, item, insight)
    if not subject.identity.content_id or subject.identity.project_id != project_id or insight is None:
        return 'insufficient_evidence', 'Content identity or insight is unavailable.'
    if insight.slot != slot or insight.platform != subject.identity.platform:
        return 'incomparable', 'Semantic insight identity conflicts with content.'
    evidence = item.get('transcript_evidence') or {}
    if evidence.get('status') not in {'valid','partial'} or (evidence.get('provenance') or {}).get('caption_kind') == 'translated':
        return 'insufficient_evidence', 'Usable validated transcript evidence required; translated captions are not eligible.'
    return _semantic_problem(subject, require_score=False)
