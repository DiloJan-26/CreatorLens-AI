"""Offline exact-model pricing, configuration and snapshot-isolation contracts."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import json

import pytest

from app.core.config import Settings
from app.core.model_policy import DEFAULT_GEMINI_MODEL, SUPPORTED_GEMINI_MODELS, model_configuration_error
from app.llm.cost_estimation import estimate_model_cost
from app.llm.pricing_policy import load_pricing_registry, pricing_date
from app.llm.token_usage import TokenUsage, parse_token_usage
from app.db.repositories.cost_repository import CostRepository
from app.llm.operation_analytics import operation_analytics
from tests.unit.test_operation_observability import usage, record
from tests.unit.test_content_item_repository import _create_project
from tests.unit.test_semantic_intelligence import content, runtime  # shared isolated synthetic fixtures


def price(model=DEFAULT_GEMINI_MODEL, at=date(2026, 11, 14), value=None, **kwargs):
    return estimate_model_cost(value or usage(), provider='gemini', model=model,
        service_tier=kwargs.pop('service_tier', 'standard'), at=at, **kwargs)


@pytest.mark.parametrize('model,day,expected', [
    (DEFAULT_GEMINI_MODEL, date(2026, 11, 14), '.0044059'),
    ('gemini-3.6-flash', date(2026, 12, 31), '.00864975'),
    ('gemini-3.8-flash', date(2026, 12, 31), '.00864975'),
    ('gemini-3.6-flash', date(2027, 1, 1), '.0172995'),
    ('gemini-3.8-flash', date(2027, 1, 1), '.0172995'),
])
def test_multi_model_exact_rates_and_effective_boundaries(model, day, expected):
    result = price(model, day)
    assert result['status'] == 'estimated'
    assert Decimal(result['estimated_cost_usd']) == Decimal(expected)
    assert result['actual_billed_cost_usd'] is None
    assert result['rates']['verified_on'] == '2026-11-14'


@pytest.mark.parametrize('model', ['gemini-3.6-flash', 'gemini-3.8-flash'])
def test_multi_model_intro_start_is_only_verified_bound(model):
    assert price(model, date(2026, 11, 13))['status'] == 'pricing_unavailable'


@pytest.mark.parametrize('kwargs', [
    {'model': 'unknown'}, {'model': 'gemini-3.5-flash'}, {'model': 'gemini-3.8-flash-latest'},
    {'service_tier': None}, {'service_tier': 'free'}, {'service_tier': 'batch'},
    {'service_tier': 'flex'}, {'service_tier': 'priority'}, {'api_backend': 'vertex_ai'},
    {'at': date(2026, 11, 12)}, {'at': datetime(2026, 11, 14)},
])
def test_multi_model_never_guesses_unsupported_prices(kwargs):
    result = price(**kwargs)
    assert result['estimated_cost_usd'] is None
    assert result['status'] == 'pricing_unavailable'


def test_multi_model_utc_inference_day_not_local_recording_day():
    moment = datetime(2027, 1, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert pricing_date(moment) == date(2026, 12, 31)
    assert Decimal(price('gemini-3.6-flash', moment)['estimated_cost_usd']) == Decimal('.00864975')


def test_multi_model_overlap_and_invalid_rates_fail_closed(tmp_path, monkeypatch):
    from app.llm import pricing_policy
    registry = load_pricing_registry()
    registry['entries'].append(deepcopy(registry['entries'][-1]))
    path = tmp_path / 'invalid-pricing.json'
    path.write_text(json.dumps(registry), encoding='utf-8')
    with pytest.raises(ValueError, match='Overlapping'):
        load_pricing_registry(path)
    monkeypatch.setattr(pricing_policy, 'REGISTRY_PATH', path)
    assert price()['status'] == 'pricing_unavailable'
    registry['entries'].pop()
    registry['entries'][0]['input_per_million'] = '-1'
    path.write_text(json.dumps(registry), encoding='utf-8')
    assert price()['status'] == 'pricing_unavailable'


def test_multi_model_prior_registry_and_policy_retained():
    from app.llm.pricing_policy import REGISTRY_PATH
    archived = json.loads(REGISTRY_PATH.with_name('pricing_registry_2026-11-13.json').read_text())
    assert archived['version'] == 'gemini-token-rates-2026-11-13'
    assert archived['entries'][0]['effective_until'] is None
    old = price(at=date(2026, 11, 13))
    new = price()
    assert old['policy_version'] == archived['version']
    assert old['estimated_cost_usd'] == new['estimated_cost_usd']
    assert old['policy_version'] != new['policy_version']


@pytest.mark.parametrize('model', ['gemini-3.6-flash', 'gemini-3.8-flash'])
def test_multi_model_cache_and_thinking_counted_once(model):
    native = parse_token_usage({'usageMetadata': dict(promptTokenCount=100,
        cachedContentTokenCount=20, candidatesTokenCount=30, thoughtsTokenCount=10, totalTokenCount=140)})
    assert native.output_tokens == 40
    assert Decimal(price(model, value=native, caching_mode='implicit')['estimated_cost_usd']) == Decimal('.0002115')
    partial = price(model, value=native, caching_mode='explicit')
    assert partial['status'] == 'partial' and partial['estimated_cost_usd'] is None
    assert Decimal(partial['priced_subtotal_usd']) == Decimal('.0002115')
    assert price(model, value=TokenUsage())['status'] == 'usage_unavailable'


@pytest.mark.parametrize('model', sorted(SUPPORTED_GEMINI_MODELS))
def test_multi_model_api_worker_share_exact_configuration(model, monkeypatch):
    from app.services import llm_service
    settings = Settings(_env_file=None, ENVIRONMENT='production', LLM_MODEL=model,
        GEMINI_API_KEY='offline-test-value')
    assert model_configuration_error(settings) is None
    # Production model policy remains checked above; mocked client runs in explicitly local demo mode.
    settings = settings.model_copy(update={'environment': 'test', 'demo_access_mode': 'local', 'demo_allow_provider_calls': True})
    monkeypatch.setattr(llm_service, 'get_settings', lambda: settings)
    options = []
    monkeypatch.setattr(llm_service, '_get_gemini_llm', lambda **kwargs: options.append(kwargs))
    llm_service.get_llm()
    assert options[0]['model'] == model
    assert options[0]['max_retries'] == 0 and options[0]['timeout'] == 30


@pytest.mark.parametrize('model', ['', 'gemini-3.5-flash', 'gemini-3.6-flash-latest', ' gemini-3.8-flash'])
def test_multi_model_invalid_configuration_rejected(model):
    assert model_configuration_error(Settings(_env_file=None, LLM_MODEL=model))


def test_multi_model_missing_production_setting_does_not_silently_fallback(monkeypatch):
    monkeypatch.delenv('LLM_MODEL', raising=False)
    settings = Settings(_env_file=None, ENVIRONMENT='production')
    assert settings.llm_model == DEFAULT_GEMINI_MODEL
    assert 'explicitly configured' in model_configuration_error(settings)
    assert model_configuration_error(Settings(_env_file=None, ENVIRONMENT='test')) is None
    assert model_configuration_error(Settings(_env_file=None, LLM_FALLBACK_MODEL='gemini-3.8-flash'))


@pytest.mark.parametrize('options', [{'max_output_tokens': 0}, {'max_output_tokens': 8193},
    {'max_retries': 1}, {'timeout': 0}, {'timeout': 66}])
def test_multi_model_inference_bounds_fail_before_client_creation(monkeypatch, options):
    from app.services import llm_service
    monkeypatch.setattr(llm_service, 'get_settings', lambda: Settings(_env_file=None, GEMINI_API_KEY='offline-test-value', DEMO_ACCESS_MODE='local', DEMO_ALLOW_PROVIDER_CALLS=True))
    monkeypatch.setattr(llm_service, '_get_gemini_llm', lambda **_: pytest.fail('Client must not be created'))
    with pytest.raises(llm_service.LLMConfigurationError):
        llm_service.get_llm(**options)


def test_multi_model_semantic_cache_identity_changes_without_destroying_history(runtime, monkeypatch):
    from app.services import semantic_service as service
    keys = []
    for model in sorted(SUPPORTED_GEMINI_MODELS):
        monkeypatch.setattr(service, 'get_settings', lambda m=model: Settings(_env_file=None, LLM_MODEL=m))
        keys.append(service.semantic_identity('project-a', 'content_1')[0])
    assert len(set(keys)) == 3
    monkeypatch.setattr(service, 'get_settings', lambda: Settings(_env_file=None, LLM_MODEL=DEFAULT_GEMINI_MODEL))
    assert service.semantic_identity('project-a', 'content_1')[0] == keys[0]


def test_multi_model_semantic_observed_identity_mismatch_cannot_be_ready(runtime, monkeypatch):
    from app.services import semantic_service as service
    pending = service.queue_semantic_analysis('project-a', 'content_1')
    async def mismatched(*_):
        return {'content': '{}', 'response_metadata': {'model_name': 'gemini-3.8-flash'},
            'usage_metadata': {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}}
    monkeypatch.setattr(service, '_invoke', mismatched)
    result = service.process_semantic_snapshot(pending['snapshot_id'])
    assert result == {'status': 'failed', 'error_code': 'SEMANTIC_MODEL_MISMATCH'}


def test_multi_model_precise_cached_price_survives_storage_aggregation_and_idempotency(db_session):
    project = _create_project(db_session)
    run = record(db_session, project, cost=None)
    cached = parse_token_usage({'usage_metadata': {'input_tokens': 1, 'output_tokens': 0,
        'input_token_details': {'cache_read': 1}}})
    before = price('gemini-3.6-flash', date(2026, 12, 31), cached, caching_mode='implicit')
    after = price('gemini-3.6-flash', date(2027, 1, 1), cached, caching_mode='implicit')
    repo = CostRepository(db_session)
    first = repo.record(llm_run_id=run.id, project_id=project, llm_provider='gemini',
        llm_model='gemini-3.6-flash', usage=cached, estimated_cost_usd=before['estimated_cost_usd'],
        estimate_details=before, event_key='stable-invocation')
    duplicate = repo.record(llm_run_id=run.id, project_id=project, llm_provider='gemini',
        llm_model='gemini-3.6-flash', usage=cached, estimated_cost_usd=after['estimated_cost_usd'],
        estimate_details=after, event_key='stable-invocation')
    assert duplicate.id == first.id and duplicate.estimate_details == before
    stored = next(row for row in repo.list_for_run(run.id) if row['id'] == first.id)
    assert stored['estimated_cost_usd'] == Decimal('.000000075')
    assert repo.summary(project_id=project)['priced_subtotal_usd'] == Decimal('.000000075')
    assert Decimal(operation_analytics(db_session, project)['daily'][0]['priced_subtotal_usd']) == Decimal('.000000075')


@pytest.mark.parametrize('moment,expected', [
    (datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc), '.00864975'),
    (datetime(2027, 1, 1, tzinfo=timezone.utc), '.0172995'),
    (None, None),
])
def test_multi_model_runtime_cost_uses_actual_invocation_timestamp(db_session, monkeypatch, moment, expected):
    from contextlib import contextmanager
    from app.services import llm_observability_service as service
    from app.core import config
    project = _create_project(db_session)
    run = record(db_session, project, cost=None)
    @contextmanager
    def session(**_):
        yield db_session
    monkeypatch.setattr(service, 'database_session', session)
    monkeypatch.setattr(service, 'is_database_configured', lambda: True)
    monkeypatch.setattr(config, 'get_settings', lambda: Settings(_env_file=None, LLM_ESTIMATE_SERVICE_TIER='standard'))
    assert service.record_cost_event(llm_run_id=run.id, project_id=project,
        llm_provider='gemini', llm_model='gemini-3.6-flash', usage=usage(),
        provider_invocation_count=1, inference_at=moment)
    row = CostRepository(db_session).list_for_run(run.id)[-1]
    assert row['estimate_details']['model_identity_status'] == 'unreported'
    assert row['estimate_details']['requested_model'] == 'gemini-3.6-flash'
    if expected is None:
        assert row['estimated_cost_usd'] is None
        assert row['estimate_details']['status'] == 'pricing_unavailable'
    else:
        assert row['estimated_cost_usd'] == Decimal(expected)
        assert row['estimate_details']['inference_started_at'] == moment.isoformat()


def test_multi_model_existing_sdk_is_pinned_to_developer_api(monkeypatch):
    from app.services import llm_service
    options = []
    monkeypatch.setattr(llm_service, 'ChatGoogleGenerativeAI', lambda **kwargs: options.append(kwargs))
    llm_service._get_gemini_llm.__wrapped__(model=DEFAULT_GEMINI_MODEL, temperature=0,
        max_output_tokens=80, google_api_key='offline-test-value', streaming=False)
    assert options[0]['vertexai'] is False


def test_multi_model_missing_registry_fails_closed(tmp_path, monkeypatch):
    from app.llm import pricing_policy
    monkeypatch.setattr(pricing_policy, 'REGISTRY_PATH', tmp_path / 'absent.json')
    assert price()['status'] == 'pricing_unavailable'
