"""Atomic Redis fixed-window limiter. SQL entitlements never depend on Redis."""
from functools import lru_cache
from hashlib import sha256
from fastapi import HTTPException
from redis import Redis

SCRIPT = """local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return {n,redis.call('TTL',KEYS[1])}"""


@lru_cache(maxsize=2)
def client(url):
    return Redis.from_url(url,socket_connect_timeout=2,socket_timeout=2,decode_responses=True)


def enforce_rate(settings, user_id, category="general", *, connection=None):
    limit = settings.authenticated_requests_per_minute if category=="general" else settings.analysis_requests_per_minute if category=="analysis" else settings.paid_requests_per_minute
    if limit <= 0:
        raise HTTPException(403, "This operation has no approved request limit and is disabled.")
    key="creatorlens:limits:"+category+":"+sha256(user_id.encode()).hexdigest()
    try:
        count, ttl = (connection or client(settings.redis_url)).eval(SCRIPT,1,key,60)
    except Exception:
        raise HTTPException(503,"Usage admission is temporarily unavailable.",headers={"Retry-After":"60"}) from None
    if int(count)>limit:
        raise HTTPException(429,"Request limit reached. Try again later.",headers={"Retry-After":str(max(1,int(ttl)))})
