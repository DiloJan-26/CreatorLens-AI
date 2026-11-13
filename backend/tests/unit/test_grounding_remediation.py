"""Bounded factual paraphrases, sentiment safety and canonical priority regressions."""
from copy import deepcopy
import json
import pytest
from app.evaluations.intelligence_fixtures import fixtures, assistant_context
from app.evaluations.intelligence_checks import execute_case
from app.evaluations.intelligence_runner import load_intelligence_dataset, check_expected
from app.llm.structured_output_service import parse_structured_output
from app.llm.structured_outputs import ComparisonAnswer
from app.rag.intelligence_context import evidence_items
from app.rag.query_router import classify_question
from tests.unit.test_creator_recommendations import semantic, run, contexts
from app.insights.recommendation_engine import validate_recommendation


def context():
    return assistant_context(fixtures()['educational'], {'probe': True})


def parsed_claim(text, data=None, evidence_claim=False):
    ctx, citations, question = data or context()
    decision = ctx['summary']['goal_comparison']
    payload = ComparisonAnswer(
        winner=decision['outcome'] if decision['outcome'] != 'incomparable' else 'insufficient_evidence',
        confidence=0, objective=ctx['selected_objective'], key_reasons=[text],
        evidence=evidence_items(citations),
    )
    if evidence_claim:
        source = next(e for e in payload.evidence if e.source_type == 'metadata' and e.slot == 'content_2')
        source.claim = text
    return parse_structured_output(payload.model_dump_json(), 'comparison', citations=citations,
        canonical_context=ctx, question=question, intent=classify_question(question))


def retained(result, text):
    return any(reason == 'Evidence-limited interpretation: '+text for reason in result.answer.key_reasons)


@pytest.mark.parametrize('claim', [
    'Content 2 has more views.',
    'Content 2 leads in observed reach.',
    'Content 2 has higher confirmed public views.',
    'Content 2 has more views than Content 1.',
    'More views were recorded for Content 2.',
    'The observed reach leader is Content 2.',
    'Content 1 has fewer views.',
    'Content 2 received 18,876 likes.',
])
def test_grounding_remediation_accepts_bounded_supported_metric_paraphrases(claim):
    result = parsed_claim(claim)
    assert retained(result, claim) and not result.used_fallback
    assert result.answer.winner == 'content_2' and result.answer.confidence == 0


@pytest.mark.parametrize('claim', [
    'Content 1 has more views.',
    'Content 1 leads in observed reach.',
    'Content 2 has fewer views.',
    'Content 2 has more views than Content 2.',
    'Content 2 received 18,877 likes.',
    'Content 1 received 18,876 likes.',
    'Content 2 has more views by 123.',
    'Content 2 has higher revenue.',
    'Content 2 has higher retention.',
    'Content 2 has more views and viewers adored it.',
])
def test_grounding_remediation_withholds_reversed_fabricated_or_unbounded_assertions(claim):
    result = parsed_claim(claim)
    assert not retained(result, claim)
    assert result.used_fallback and result.answer.winner == 'content_2'


@pytest.mark.parametrize('damage', ['missing', 'tie', 'incomparable', 'revision', 'owner', 'no_citation'])
def test_grounding_remediation_requires_current_eligible_metric_comparison(damage):
    data = context(); ctx, citations, question = data
    dimension = ctx['summary']['goal_comparison']['objective_decisions']['reach']
    if damage == 'missing': dimension['values']['content_2'] = None
    if damage == 'tie': dimension['outcome'] = 'tie'; dimension['winner_slot'] = None
    if damage == 'incomparable': dimension['eligibility']['status'] = 'incomparable'
    if damage == 'revision': ctx['summary']['goal_comparison']['content_2']['metric_input_revision'] = 'new'
    if damage == 'owner': ctx['summary']['content_2']['content_id'] = 'foreign'
    if damage == 'no_citation': citations[:] = [c for c in citations if not (c.source_type == 'metadata' and c.slot == 'content_2')]
    claim = 'Content 2 has more views.'
    assert not retained(parsed_claim(claim, data), claim)


def test_grounding_remediation_direction_uses_requested_dimension_not_other_leader():
    data = context()
    claim = 'Content 1 has higher observed engagement rate.'
    result = parsed_claim(claim, data)
    assert retained(result, claim)
    assert not retained(parsed_claim('Content 2 has higher observed engagement rate.', data), 'Content 2 has higher observed engagement rate.')
    # Independent engagement leader cannot change the selected Reach outcome.
    assert result.answer.winner == 'content_2' and result.answer.objective == 'reach'


@pytest.mark.parametrize('claim', [
    'The audience adored the video.',
    'Viewers loved this content.',
    'The comments were overwhelmingly positive.',
    'Viewers hated this content.',
    'The audience was bored.',
    'Viewers liked this video.',
    'Fans were captivated by this content.',
    'This video was loved by viewers.',
    'The available metrics do not establish sentiment, but viewers loved this content.',
    'The opening caused viewer drop-off.',
    'The video will increase revenue.',
])
def test_grounding_remediation_rejects_unsupported_emotion_and_outcome_claims(claim):
    result = parsed_claim(claim)
    assert result.used_fallback and not retained(result, claim)


@pytest.mark.parametrize('claim', [
    'The available metrics do not establish sentiment.',
    'Audience sentiment remains unknown.',
    'Test two opening statements and compare the observed interaction rate.',
    'Content 1 introduces the study topic in its spoken explanation.',
])
def test_grounding_remediation_preserves_uncertainty_and_qualitative_experiments(claim):
    result = parsed_claim(claim)
    assert retained(result, claim) and not result.used_fallback


def test_grounding_remediation_source_quotation_is_not_a_sentiment_assertion():
    ctx, citations, question = context()
    source = next(c for c in citations if c.source_type == 'transcript')
    source.text = 'Viewers loved this content.'
    ctx['citations'] = [c.model_dump(mode='json') for c in citations]
    claim = 'The transcript says "Viewers loved this content."'
    assert retained(parsed_claim(claim, (ctx,citations,question)), claim)
    fabricated = 'The transcript says "The audience adored the video."'
    assert not retained(parsed_claim(fabricated, (ctx,citations,question)), fabricated)


def test_grounding_remediation_supported_metric_evidence_claim():
    result = parsed_claim('Content 2 received 18,876 likes.', evidence_claim=True)
    assert not result.used_fallback
    assert parsed_claim('Content 2 received 18,877 likes.', evidence_claim=True).used_fallback


@pytest.mark.parametrize('damage', ['id','label','score','strength','severity','relevance','directness','explanation',
    'priority_policy','target','policy','trigger','evidence','missing_current'])
def test_grounding_remediation_untrusted_recommendation_must_match_full_current_output(damage):
    a, b = semantic('content_1', {'verbal_hook_clarity':'partial'}), semantic('content_2')
    bundle, decision = run(a,b)
    r = bundle.recommendations[0].model_copy(deep=True)
    assert r.priority.label == 'medium'
    if damage == 'id': r.id = 'invented'
    elif damage == 'label': r.priority.label = 'high'
    elif damage == 'score': r.priority.score = 8
    elif damage == 'strength': r.priority.evidence_strength = 0
    elif damage == 'severity': r.priority.severity = 3
    elif damage == 'relevance': r.priority.objective_relevance = 0
    elif damage == 'directness': r.priority.action_directness = 0
    elif damage == 'explanation': r.priority.explanation = 'Invented rationale'
    elif damage == 'priority_policy': r.priority.policy_version = 'forged'
    elif damage == 'target': r.target_content_id = b[0]['id']
    elif damage == 'policy': r.policy_version = 'forged'
    elif damage == 'trigger': r.signals[0].trigger = 'Invented rule'
    elif damage == 'evidence': r.evidence[0].input_revision = 'stale'
    else:
        a = semantic('content_1')  # The previously supported weakness no longer exists.
        _, decision = run(a,b)
    with pytest.raises(ValueError): validate_recommendation(r, contexts(a,b,decision), decision)


def test_grounding_remediation_canonical_recommendation_survives_unavailable_verdict():
    from app.insights.comparison_engine import build_goal_comparison
    from app.insights.recommendation_engine import build_creator_recommendations, RecommendationSubject
    from app.insights.deterministic_scoring import normalize_metrics
    from tests.unit.test_creator_recommendations import PROJECT
    a = semantic('content_1', {'verbal_hook_clarity':'partial'})
    decision = build_goal_comparison(PROJECT, a[0], None, a[1], None, 'balanced')
    bundle = build_creator_recommendations(PROJECT, decision, [a, (None,None)])
    r = bundle.recommendations[0]
    assert decision.outcome.value == 'insufficient_evidence'
    subjects = {a[0]['id']:RecommendationSubject(a[0],a[1],decision.content_1,normalize_metrics(a[0]),True)}
    assert validate_recommendation(r, subjects, decision) == r


def test_grounding_remediation_untouched_merged_recommendation_remains_valid():
    a,b = semantic('content_1', {'verbal_hook_clarity':'partial','audience_benefit':'partial'}),semantic('content_2')
    bundle,decision = run(a,b)
    r = bundle.recommendations[0]
    assert len(r.signals) == 2
    assert validate_recommendation(r, contexts(a,b,decision), decision) == r


@pytest.mark.parametrize('case_id', ['recommendation_wrong_priority_probe',
    'grounding_probe_valid_directional_paraphrase','grounding_probe_unsupported_indirect_sentiment'])
def test_grounding_remediation_original_evaluation_expectations_unchanged(case_id):
    case = next(c for c in load_intelligence_dataset('creatorlens_intelligence_v2') if c.case_id == case_id)
    actual, measurements = execute_case(case, fixtures()[case.fixture_id])
    assert not check_expected(actual, case.expected)


def test_grounding_remediation_directional_claim_cannot_be_attributed_to_transcript():
    ctx,citations,question = context()
    decision = ctx['summary']['goal_comparison']
    evidence = evidence_items(citations)
    next(e for e in evidence if e.source_type == 'transcript').claim = 'Content 2 has more views.'
    payload = ComparisonAnswer(winner='content_2', confidence=0, objective='reach', evidence=evidence)
    result = parse_structured_output(payload.model_dump_json(), 'comparison', citations=citations,
        canonical_context=ctx, question=question, intent=classify_question(question))
    assert result.used_fallback
