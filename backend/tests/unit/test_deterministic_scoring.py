"""Behavioral regressions for missing data, sample sufficiency and scoring contracts."""
import math
import pytest
from app.insights.deterministic_scoring import calculate_scoring, normalize_metrics, comparison_eligibility
from app.insights.scoring_models import CreatorScoring
from app.insights.insight_models import InsightScores

CREATIVE = dict(hook_clarity=2, problem_solution_clarity=3, caption_strength=4, cta_strength=5, audience_specificity=6)

def item(**changes):
    return dict(platform="youtube", views=10000, likes=100, comments=20, subscriber_count=1000,
        title="An example", transcript_evidence={"status":"partial", "revision":"r"}, **changes) if not changes else {
        **item(), **changes}

def score(**changes):
    return calculate_scoring(item(**changes), CREATIVE, hook_assessable=True)

@pytest.mark.parametrize('field,value', [(f,v) for f in ('views','likes','comments','subscriber_count') for v in (None,0,-1)])
def test_missing_zero_and_invalid_counts(field, value):
    result = score(**{field:value})
    assert result.metrics.counts[field] == (None if value is None or value < 0 else 0)
    if field == 'subscriber_count' and not value or field == 'subscriber_count' and value < 0:
        assert result.creator_efficiency.score is None
    if field in {'likes','comments'} and value is None:
        assert result.metrics.interactions is None
        assert result.public_performance.score is None
    if field in {'likes','comments'} and value == 0:
        assert result.metrics.counts[field] == 0

@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, '10', 1.5, 2**54])
def test_invalid_numeric_inputs_are_rejected(value):
    assert normalize_metrics(item(views=value)).counts['views'] is None


def test_small_sample_preserves_rates_without_winner_or_score():
    a, b = score(views=4,likes=4,comments=0), score(views=1000000,likes=4000,comments=0)
    assert a.metrics.rates_percent['likes'] == 100
    assert b.metrics.rates_percent['likes'] == .4
    assert a.metrics.engagement_status == 'insufficient_evidence'
    assert a.engagement.score is None and a.overall.score is None
    assert comparison_eligibility(a,b)['status'] == 'insufficient_evidence'


def test_complete_combined_rate_and_partial_counts_are_separate():
    a = score(comments=None)
    assert a.metrics.available_interactions == 100
    assert a.metrics.interactions is None
    assert a.metrics.rates_percent['likes'] == 1
    assert a.metrics.rates_percent['combined_engagement'] is None
    assert score(comments=0,likes=0).engagement.score == 0


def test_cross_platform_definition_guard():
    a = score()
    b = score(platform='facebook', reactions=100, shares=10, follower_count=1000)
    assert b.metrics.interaction_definition == ['reactions','comments','shares']
    assert comparison_eligibility(a,b)['status'] == 'insufficient_evidence'


def test_missing_creator_size_does_not_reduce_available_quality():
    a, b = score(subscriber_count=None), score()
    assert a.creator_efficiency.score is None
    assert a.overall.score is not None
    assert a.overall.coverage == pytest.approx(.60/.90)
    assert a.public_performance == b.public_performance
    assert comparison_eligibility(a,b)['status'] == 'insufficient_evidence'
    assert sum(p.weight for p in a.overall.components) == pytest.approx(1)


def test_quality_independent_of_confidence_and_evidence_status():
    a, b = score(), score(metric_source_confidence='high', transcript_evidence={'status':'valid'})
    assert a.overall == b.overall
    assert a.evidence != b.evidence
    assert not any(p.feature == 'engagement_confidence' for p in a.overall.components)


def test_extreme_ratios_capped_with_raw_metric_retained():
    a = score(views=10**9,subscriber_count=1)
    assert a.metrics.views_per_current_creator_size == 10**9
    assert a.creator_efficiency.score == 10


def test_observation_date_controls_age_not_system_clock():
    a = score(upload_date='2020-01-01',captured_at='2020-01-11T00:00:00Z')
    b = score(upload_date='2020-01-06',captured_at='2020-01-11T00:00:00Z')
    assert (a.metrics.age_days,b.metrics.age_days) == (10,5)
    assert a.overall.score == b.overall.score
    assert score(upload_date='2030-01-01',captured_at='2020-01-01').metrics.age_days is None


def test_creative_formula_and_missing_hook_eligibility():
    a = score()
    assert a.creative_structure.score == round(2*.3+3*.25+4*.2+5*.15+6*.1)
    b = calculate_scoring(item(), CREATIVE, hook_assessable=False)
    assert b.creative_structure.score is None and b.overall.score is None


def test_fixed_inputs_serialization_and_policy():
    a = score(subscriber_count=None)
    assert CreatorScoring.model_validate_json(a.model_dump_json()) == a
    assert a == score(subscriber_count=None)
    assert '"score":null' in a.model_dump_json()
    assert a.policy.version == 'creator-insight-2.0.0'
    assert comparison_eligibility(score(),score())['status'] == 'eligible'


def test_bounds_and_contributions_over_deterministic_grid():
    for views in (0,4,999,1000,34021,1527222,10**8):
        for likes in (0,4,485,18876):
            a = score(views=views,likes=likes,comments=0)
            for name in ('reach','engagement','public_performance','creator_efficiency','creative_structure','overall'):
                result = getattr(a,name)
                assert result.score is None or 0 <= result.score <= 10
                assert 0 <= result.coverage <= 1
            if views > 0 and likes <= views:
                assert 0 <= a.metrics.rates_percent['likes'] <= 100


def test_dopamine_metrics_are_descriptive_not_legacy_winners():
    a, b = score(views=34021,likes=485,comments=8,subscriber_count=None), score(views=1527222,likes=18876,comments=308,subscriber_count=None)
    assert a.metrics.rates_percent['combined_engagement'] == pytest.approx(493/34021*100)
    assert b.metrics.rates_percent['combined_engagement'] == pytest.approx(19184/1527222*100)
    assert a.reach.score < b.reach.score
    assert a.engagement.score > b.engagement.score
    assert a.authoritative_winner is None


def test_existing_insight_endpoint_attaches_versioned_contract(monkeypatch):
    from app.insights import insight_service as service
    monkeypatch.setattr(service, 'get_transcript_segments', lambda **kwargs: [])
    result = service._build_content_insight('synthetic',item(slot='content_1'))
    assert result.scores.policy_version == 'legacy-1.0.0'
    assert result.scoring.policy.version == 'creator-insight-2.0.0'
    assert result.scoring.overall.score is None
    assert isinstance(result.scores.overall_score,int)
