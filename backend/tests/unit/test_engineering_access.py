from dataclasses import replace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.core.config import Settings
from app.core.identity import Principal
from app.core import engineering_access as gate
from tests.engineering_fixtures import FakeEngineeringRedis

KEY='offline-engineering-test-key-0123456789'

@pytest.fixture
def setup(monkeypatch):
    redis=FakeEngineeringRedis()
    monkeypatch.setattr(gate,'client',lambda _:redis)
    settings=Settings(_env_file=None,ENVIRONMENT='test',REDIS_URL='redis://localhost:6379',ENGINEERING_ACCESS_KEY=KEY)
    principal=Principal(str(uuid4()),str(uuid4()),1)
    return settings,principal,redis


def test_key_is_private_and_optional_without_weakening_other_configuration():
    settings=Settings(_env_file=None,ENGINEERING_ACCESS_KEY=KEY)
    assert KEY not in repr(settings)
    assert Settings(_env_file=None,ENGINEERING_ACCESS_KEY='').engineering_access_key is None

@pytest.mark.parametrize('key',['short','x'*257,'x'*31+' ','x'*31+'\n'])
def test_weak_or_invalid_configured_keys_are_rejected_without_echo(key):
    with pytest.raises(ValidationError) as error:Settings(_env_file=None,ENGINEERING_ACCESS_KEY=key)
    assert key not in str(error.value)

@pytest.mark.parametrize('seconds',[0,59,3601,-1])
def test_invalid_duration_rejected(seconds):
    with pytest.raises(ValidationError):Settings(_env_file=None,ENGINEERING_UNLOCK_SECONDS=seconds)


def test_missing_key_keeps_only_engineering_locked(setup):
    settings,p,redis=setup;settings.engineering_access_key=None
    assert gate.access_status(settings,p)['unlocked'] is False
    assert not redis.calls
    with pytest.raises(HTTPException) as error:gate.unlock(settings,p,KEY)
    assert error.value.status_code==503


def test_unlock_shared_across_requests_and_fixed_expiry(setup):
    settings,p,redis=setup
    assert not gate.access_status(settings,p)['unlocked']
    assert gate.unlock(settings,p,KEY)['expires_in']==1800
    redis.now+=1799
    assert gate.access_status(settings,p)['expires_in']==1
    gate.require_engineering(settings,p)
    redis.now+=1
    assert not gate.access_status(settings,p)['unlocked']
    with pytest.raises(HTTPException) as error:gate.require_engineering(settings,p)
    assert error.value.status_code==403
    assert len([c for c in redis.calls if c[0]=='set'])==1


def test_duration_override_changes_server_grant_and_reported_duration(setup):
    settings,p,redis=setup;settings.engineering_unlock_seconds=60
    assert gate.unlock(settings,p,KEY)['duration_seconds']==60
    redis.now+=60
    assert not gate.access_status(settings,p)['unlocked']


def test_manual_lock_is_shared_idempotent_and_session_specific(setup):
    settings,p,redis=setup;other=replace(p,session_id=str(uuid4()))
    gate.unlock(settings,p,KEY);gate.unlock(settings,other,KEY)
    gate.lock(settings,p);gate.lock(settings,p)
    assert not gate.access_status(settings,p)['unlocked']
    assert gate.access_status(settings,other)['unlocked']


def test_grants_cannot_cross_user_or_google_session(setup):
    settings,p,redis=setup;gate.unlock(settings,p,KEY)
    assert not gate.access_status(settings,replace(p,user_id=str(uuid4())))['unlocked']
    assert not gate.access_status(settings,replace(p,session_id=str(uuid4())))['unlocked']


def test_rotation_invalidates_existing_grant(setup):
    settings,p,redis=setup;gate.unlock(settings,p,KEY)
    changed=Settings(_env_file=None,REDIS_URL=settings.redis_url,ENGINEERING_ACCESS_KEY='rotated-offline-key-0123456789abcdef')
    assert not gate.access_status(changed,p)['unlocked']


def test_wrong_key_does_not_create_grant_or_leak_configuration(setup):
    settings,p,redis=setup
    with pytest.raises(HTTPException) as error:gate.unlock(settings,p,'incorrect')
    assert error.value.status_code==403 and KEY not in str(error.value)
    assert not gate.access_status(settings,p)['unlocked']


def test_user_attempt_limit_applies_across_multiple_sessions(setup):
    settings,p,redis=setup
    for _ in range(5):
        with pytest.raises(HTTPException) as error:gate.unlock(settings,replace(p,session_id=str(uuid4())),'wrong')
        assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:gate.unlock(settings,p,KEY)
    assert error.value.status_code==429 and error.value.headers['Retry-After']=='300'
    redis.now+=300
    assert gate.unlock(settings,p,KEY)['unlocked']


def test_global_attempt_limit_bounds_distinct_accounts(setup):
    settings,p,redis=setup
    for _ in range(30):
        with pytest.raises(HTTPException):gate.unlock(settings,replace(p,user_id=str(uuid4())),'wrong')
    with pytest.raises(HTTPException) as error:gate.unlock(settings,replace(p,user_id=str(uuid4())),KEY)
    assert error.value.status_code==429

@pytest.mark.parametrize('operation',['access_status','unlock','lock'])
def test_redis_outage_fails_closed(setup,operation):
    settings,p,redis=setup;redis.failed=True
    with pytest.raises(HTTPException) as error:getattr(gate,operation)(settings,p,*([KEY] if operation=='unlock' else []))
    assert error.value.status_code==503


def test_persistent_or_oversized_grant_ttl_cannot_bypass_expiry(setup,monkeypatch):
    settings,p,redis=setup
    for ttl in (-1,0,1801):
        monkeypatch.setattr(redis,'ttl',lambda _:ttl)
        assert not gate.access_status(settings,p)['unlocked']


@pytest.mark.parametrize('supplied',[chr(0xD800)*32,chr(0xE9)*32,None])
def test_untrusted_key_types_and_unicode_fail_without_echo_or_server_error(setup,supplied):
    settings,p,redis=setup
    with pytest.raises(HTTPException) as error:gate.unlock(settings,p,supplied)
    assert error.value.status_code==403 and KEY not in str(error.value)
