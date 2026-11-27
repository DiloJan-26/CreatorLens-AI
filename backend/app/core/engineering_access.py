"""Temporary read-only Engineering permission, scoped to verified Google sessions."""
import hashlib
import hmac
from fastapi import HTTPException
from app.core.request_limits import client
from app.core.config import setting_value

ATTEMPTS = """local a=redis.call('INCR',KEYS[1]); if a==1 then redis.call('EXPIRE',KEYS[1],300) end;
local b=redis.call('INCR',KEYS[2]); if b==1 then redis.call('EXPIRE',KEYS[2],300) end;
return {a,b,redis.call('TTL',KEYS[1]),redis.call('TTL',KEYS[2])}"""


def _secret(settings):
    value = getattr(settings, 'engineering_access_key', None)
    if value is None: return None
    text = value.get_secret_value()
    return text if text else None


def _identity(principal):
    return hashlib.sha256((principal.user_id+':'+principal.session_id).encode()).hexdigest()


def _grant_key(settings, principal):
    # Rotation changes the namespace, immediately invalidating previous grants.
    version = hmac.new(_secret(settings).encode(), b'creatorlens-engineering', hashlib.sha256).hexdigest()[:32]
    return 'creatorlens:{engineering}:grant:'+version+':'+_identity(principal)


def _connection(settings):
    if not getattr(settings, 'redis_url', None):
        raise HTTPException(503, 'Engineering access is temporarily unavailable.')
    return client(settings.redis_url)


def access_status(settings, principal):
    if not _secret(settings): return dict(configured=False, unlocked=False, expires_in=0, duration_seconds=setting_value(settings,'engineering_unlock_seconds'))
    try: remaining = int(_connection(settings).ttl(_grant_key(settings, principal)))
    except Exception:
        raise HTTPException(503, 'Engineering access is temporarily unavailable.') from None
    unlocked = 0 < remaining <= settings.engineering_unlock_seconds
    return dict(configured=True, unlocked=unlocked, expires_in=remaining if unlocked else 0, duration_seconds=settings.engineering_unlock_seconds)


def require_engineering(settings, principal):
    status = access_status(settings, principal)
    if not status['unlocked']:
        raise HTTPException(403, 'Engineering is locked. Enter the access key to continue.')


def unlock(settings, principal, supplied):
    expected = _secret(settings)
    if expected is None:
        raise HTTPException(503, 'Engineering access is not configured.')
    try:
        connection = _connection(settings)
        count, global_count, ttl, global_ttl = connection.eval(ATTEMPTS, 2,
            'creatorlens:{engineering}:attempts:'+hashlib.sha256(principal.user_id.encode()).hexdigest(),
            'creatorlens:{engineering}:attempts:global')
    except Exception:
        raise HTTPException(503, 'Engineering access is temporarily unavailable.') from None
    if int(count) > 5 or int(global_count) > 30:
        retry = global_ttl if int(global_count) > 30 else ttl
        raise HTTPException(429, 'Too many unlock attempts. Try again later.', headers={'Retry-After':str(max(1,int(retry)))})
    valid = isinstance(supplied, str) and 32 <= len(supplied) <= 256 and supplied.isascii()
    digest = hashlib.sha256((supplied if valid else '').encode()).digest()
    if not hmac.compare_digest(digest, hashlib.sha256(expected.encode()).digest()):
        raise HTTPException(403, 'The Engineering access key is incorrect.')
    try:
        if not connection.set(_grant_key(settings, principal), '1', ex=settings.engineering_unlock_seconds):
            raise RuntimeError('Grant unavailable')
    except Exception:
        raise HTTPException(503, 'Engineering access is temporarily unavailable.') from None
    return dict(configured=True, unlocked=True, expires_in=settings.engineering_unlock_seconds, duration_seconds=settings.engineering_unlock_seconds)


def lock(settings, principal):
    if not _secret(settings): return dict(configured=False, unlocked=False, expires_in=0, duration_seconds=setting_value(settings,'engineering_unlock_seconds'))
    try: _connection(settings).delete(_grant_key(settings, principal))
    except Exception:
        raise HTTPException(503, 'Engineering lock could not be confirmed. Try again.') from None
    return dict(configured=True, unlocked=False, expires_in=0, duration_seconds=settings.engineering_unlock_seconds)
