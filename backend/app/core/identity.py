"""Supabase asymmetric JWT verification. No token-derived URLs or algorithms."""
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from uuid import UUID
import httpx
import jwt
from fastapi import HTTPException


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str
    issued_at: int
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class JwksVerifier:
    def __init__(self, fetch=None, clock=monotonic):
        self.fetch = fetch or self._fetch
        self.clock = clock
        self.lock = RLock()
        self.keys = {}
        self.expires = 0
        self.last_refresh = -100.0
        self.url = None

    @staticmethod
    def _fetch(url):
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            response = client.get(url)
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ValueError("Oversized JWKS")
            return response.json()

    def verify(self, token, settings):
        try:
            if not isinstance(token, str) or len(token) > 16384:
                raise ValueError("Invalid token")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "ES256" or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise ValueError("Invalid key identifier")
            if any(key in header for key in ("jku", "x5u", "crit")):
                raise ValueError("Unsupported JWT headers")
            with self.lock:
                now = self.clock()
                if self.url != settings.supabase_jwks_url:
                    self.keys, self.expires, self.last_refresh = {}, 0, -100.0
                    self.url = settings.supabase_jwks_url
                if now >= self.expires or kid not in self.keys:
                    if now - self.last_refresh >= 5:
                        self.last_refresh = now
                        document = self.fetch(self.url)
                        keys = document.get("keys", [])
                        if not isinstance(keys, list) or len(keys) > 20:
                            raise ValueError("Invalid JWKS")
                        eligible = [key for key in keys if key.get("kty") == "EC" and key.get("crv") == "P-256" and key.get("use", "sig") == "sig" and key.get("alg", "ES256") == "ES256"]
                        self.keys = {key["kid"]: jwt.PyJWK.from_dict(key, algorithm="ES256").key for key in eligible}
                        self.expires = now + 300
                    if now >= self.expires:
                        raise ValueError("JWKS expired")
                key = self.keys.get(kid)
                if key is None:
                    raise ValueError("Unknown signing key")
            claims = jwt.decode(token, key, algorithms=["ES256"], audience=settings.supabase_jwt_audience,
                issuer=settings.supabase_jwt_issuer, options={"require": ["exp", "iat", "sub", "iss", "aud", "session_id", "role"]})
            subject, session = str(UUID(claims["sub"])), str(UUID(claims["session_id"]))
            if claims["role"] != "authenticated" or claims.get("is_anonymous", False):
                raise ValueError("Ineligible identity")
            # Provider metadata is signed server app_metadata, never user_metadata.
            # OAuth AMR is also required: merely linking Google to a password session is insufficient.
            methods = claims.get("amr", [])
            metadata=claims.get("app_metadata", {})
            if metadata.get("provider") != "google" or metadata.get("providers") != ["google"] or not any(m.get("method") == "oauth" for m in methods):
                raise HTTPException(403, "Google sign-in is required.")
            profile = claims.get("user_metadata", {})
            def text(value):
                return value[:512] if isinstance(value, str) else None
            return Principal(subject, session, int(claims["iat"]), text(claims.get("email")), text(profile.get("full_name")), text(profile.get("avatar_url")))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "A valid Supabase access token is required.", headers={"WWW-Authenticate": "Bearer"}) from None


verifier = JwksVerifier()
