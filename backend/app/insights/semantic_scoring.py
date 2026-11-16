"""Fixed semantic-label weights; Gemini never supplies numerical scores."""
from app.insights.scoring_models import CreatorScoring, ScoreBreakdown, ScoreComponent
from app.insights.semantic_models import CreativeFeatures, CREATIVE_POLICY
from app.insights.deterministic_scoring import _combine, _feature

WEIGHTS = {'verbal_hook_clarity':.25, 'topic_specificity':.15, 'curiosity_gap':.10,
    'audience_benefit':.15, 'problem_solution_clarity':.15, 'audience_specificity':.10,
    'spoken_cta':.05, 'description_cta':.05}
POINTS = {'clear':10., 'partial':5., 'absent':0., 'unassessable':None}


def semantic_creative_score(features: CreativeFeatures) -> ScoreBreakdown:
    by_name = {f.feature:f for f in features.features}
    parts = [ScoreComponent(feature=name, score=POINTS[by_name[name].value], rule='clear=10, partial=5, absent=0; unassessable=null; model-derived label, not measured audience outcome',
        source=','.join(r.evidence_id for r in by_name[name].evidence)) for name in WEIGHTS]
    result = _combine(parts, WEIGHTS, minimum=1, rationale='Fixed semantic label mapping; eligible weights renormalized. Minimum coverage .70 and assessed hook clarity/topic specificity required.')
    required = all(by_name[name].status == 'assessed' for name in ('verbal_hook_clarity','topic_specificity'))
    if result.coverage < .70 or not required:
        result.score = None
        result.status = 'not_assessable'
        for part in result.components:
            part.weight = 0
            part.contribution = None
    result.policy_version = CREATIVE_POLICY
    result.limitations = ['Model interpretations are not independently measured retention, virality, causality or revenue.',
        'Transcript evidence assesses verbal content only; no visual or acoustic production analysis.']
    return result


def apply_semantic_scoring(base: CreatorScoring, features: CreativeFeatures, snapshot_id: str) -> CreatorScoring:
    result = base.model_copy(deep=True)
    result.creative_structure = semantic_creative_score(features)
    c, p, f = result.creative_structure, result.public_performance, result.creator_efficiency
    result.overall = _combine([
        _feature('public_performance',p.score,p.score,'Unchanged metric policy','confirmed public metrics'),
        _feature('creator_efficiency',f.score,f.score,'Unchanged metric policy','current creator-size context'),
        _feature('creative_structure',c.score,c.score,CREATIVE_POLICY,'validated semantic feature snapshot')],
        result.policy.overall_weights, minimum=2, rationale='Existing metric weights .35/.30/.25; requires performance AND semantic creative evidence; no confidence bonus.')
    if p.score is None or c.score is None:
        result.overall.score = None
        result.overall.status = 'not_assessable'
        for component in result.overall.components:
            component.weight = 0
            component.contribution = None
    result.policy.version = 'creator-insight-semantic-1.0.0'
    result.creative_policy_version = CREATIVE_POLICY
    result.semantic_snapshot_id = snapshot_id
    result.overall.policy_version = result.policy.version
    result.comparison_signature = [result.metrics.platform, '+'.join(result.metrics.interaction_definition),
        CREATIVE_POLICY, *[x.feature for x in result.overall.components if x.score is not None]]
    return result
