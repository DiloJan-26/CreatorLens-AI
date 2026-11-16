"""Credential-independent synthetic recruiter demo. Never imported by runtime routes."""
import json
from app.evaluations.intelligence_fixtures import fixtures, assistant_context, comparison_inputs
from app.rag.intelligence_context import canonical_answer
from app.rag.query_router import classify_question
from app.llm.cost_estimation import estimate_model_cost
from app.llm.token_usage import parse_token_usage
from datetime import date


def build_demo_report():
    fixture = fixtures()['educational']
    decisions = {}
    for objective in ('balanced', 'reach', 'engagement', 'creative_quality'):
        _, _, decision = comparison_inputs(fixture, {'objective': objective, 'dopamine': True})
        decisions[objective] = decision.model_dump(mode='json')
    context, citations, question = assistant_context(fixture, {'question': 'Which video has more views?'})
    metric = canonical_answer(context, question, classify_question(question), citations)
    semantic_a, semantic_b, semantic_decision = comparison_inputs(fixture, {'semantic': True, 'objective': 'creative_quality'})
    usage = parse_token_usage({'usage_metadata': {'input_tokens': 6803, 'output_tokens': 946,
        'input_token_details': {'cache_read': 0}, 'output_token_details': {'reasoning': 0}}})
    return dict(mode='synthetic_offline_not_live_inference', limitations=[
        'Example metrics use the supplied numerical regression fixture, not freshly extracted videos.',
        'Semantic labels are fixture-authored mocked responses, not human-reviewed labels or actual Gemini generation.',
        'No production data, embeddings, Qdrant, Redis or provider access is required.'],
        metric_only_decisions=decisions, deterministic_answer=metric.model_dump(mode='json'),
        mocked_semantic_decision=semantic_decision.model_dump(mode='json'),
        recommendations=context['summary']['creator_recommendations'],
        token_estimate=estimate_model_cost(usage, provider='gemini', model='gemini-3.5-flash-lite', service_tier='standard', at=date(2026,11,14)))


if __name__ == '__main__':
    import sys
    def offline_guard(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'sqlite3.connect'}:
            raise RuntimeError('Offline demonstration forbids network and database access.')
    sys.addaudithook(offline_guard)
    import argparse
    parser = argparse.ArgumentParser(description='Synthetic offline CreatorLens demonstration; no providers.')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    report = build_demo_report()
    if not args.full:
        report['metric_only_decisions'] = {key: {name: value[name] for name in ('selected_objective', 'outcome', 'raw_objective_values', 'explanation')} for key, value in report['metric_only_decisions'].items()}
        report['mocked_semantic_decision'] = {key: report['mocked_semantic_decision'][key] for key in ('outcome', 'explanation', 'creative_policy_version')}
    print(json.dumps(report, indent=2))
