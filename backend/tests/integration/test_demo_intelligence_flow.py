"""Synthetic cross-component demonstration, not a live extraction/model benchmark."""
from decimal import Decimal
from app.evaluations.demo_report import build_demo_report


def test_offline_demo_canonical_decisions_recommendation_identity_and_cost():
    data = build_demo_report()
    decisions = data['metric_only_decisions']
    assert decisions['reach']['winner_slot'] == 'content_2'
    assert decisions['engagement']['winner_slot'] == 'content_1'
    assert decisions['balanced']['outcome'] == 'insufficient_evidence'
    assert decisions['creative_quality']['outcome'] == 'insufficient_evidence'
    assert data['deterministic_answer']['winner'] == 'content_2'
    assert data['mocked_semantic_decision']['eligibility']['status'] == 'eligible'
    for item in data['recommendations']['recommendations']:
        assert item['target_content_id'] == 'eval-' + item['target_slot']
        assert all(e['content_id'] == item['target_content_id'] or e['role'] == 'comparison_context' for e in item['evidence'])
    assert Decimal(data['token_estimate']['estimated_cost_usd']) == Decimal('.0044059')
    assert data['token_estimate']['actual_billed_cost_usd'] is None
    assert data == build_demo_report()
