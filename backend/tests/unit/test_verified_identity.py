from types import SimpleNamespace
from time import time
from uuid import uuid4
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from app.core.identity import JwksVerifier
from app.core.config import Settings


def fixture():
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = __import__("json").loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="first", alg="ES256", use="sig")
    settings = SimpleNamespace(supabase_jwks_url="https://auth.example/auth/v1/.well-known/jwks.json", supabase_jwt_issuer="https://auth.example/auth/v1", supabase_jwt_audience="authenticated")
    claims = dict(sub=str(uuid4()), session_id=str(uuid4()), exp=int(time())+300, iat=int(time()), iss=settings.supabase_jwt_issuer, aud="authenticated", role="authenticated", app_metadata={"provider":"google","providers":["google"]}, amr=[{"method":"oauth"}])
    return key,jwk,settings,claims


@pytest.mark.parametrize("change,status", [({},None),({"exp":1},401),({"iss":"bad"},401),({"aud":"bad"},401),({"sub":"invalid"},401),({"role":"service_role"},401),({"iat":9999999999},401),({"app_metadata":{"provider":"email"}},403),({"amr":[{"method":"password"}]},403),({"app_metadata":{"provider":"google","providers":["google","github"]}},403)])
def test_verified_claims(change,status):
    key,jwk,settings,claims=fixture(); claims.update(change)
    verifier=JwksVerifier(fetch=lambda _: {"keys":[jwk]})
    token=jwt.encode(claims,key,algorithm="ES256",headers={"kid":"first"})
    if status:
        with pytest.raises(HTTPException) as error: verifier.verify(token,settings)
        assert error.value.status_code==status
    else: assert verifier.verify(token,settings).user_id==claims["sub"]


def test_signature_algorithm_key_and_outage():
    key,jwk,settings,claims=fixture()
    v=JwksVerifier(fetch=lambda _: {"keys":[jwk]})
    for token in ["bad",jwt.encode(claims,"synthetic-rejected-hmac-key-over-32-bytes",algorithm="HS256",headers={"kid":"first"}),jwt.encode(claims,ec.generate_private_key(ec.SECP256R1()),algorithm="ES256",headers={"kid":"first"}),jwt.encode(claims,key,algorithm="ES256",headers={"kid":"unknown"})]:
        with pytest.raises(HTTPException): v.verify(token,settings)
    with pytest.raises(HTTPException): JwksVerifier(fetch=lambda _: (_ for _ in ()).throw(TimeoutError())).verify(jwt.encode(claims,key,algorithm="ES256",headers={"kid":"first"}),settings)


def test_rotation_and_refresh_throttle():
    key,jwk,settings,claims=fixture(); tick=[10]; calls=[]; document={"keys":[jwk]}
    v=JwksVerifier(fetch=lambda _: calls.append(1) or document,clock=lambda:tick[0])
    token=lambda kid: jwt.encode(claims,key,algorithm="ES256",headers={"kid":kid})
    v.verify(token("first"),settings)
    for _ in range(3):
        with pytest.raises(HTTPException): v.verify(token("other"),settings)
    assert len(calls)==1
    document["keys"]=[dict(jwk,kid="other")];tick[0]+=6
    v.verify(token("other"),settings); assert len(calls)==2


def test_authentication_never_implicitly_enables():
    s=Settings(_env_file=None,SUPABASE_URL="https://auth.example")
    assert s.application_access_mode=="disabled"
    with pytest.raises(ValueError): Settings(_env_file=None,APPLICATION_ACCESS_MODE="authenticated")


def test_invalid_configuration_does_not_display_private_values():
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None,APPLICATION_ACCESS_MODE="authenticated",SUPABASE_URL="invalid",GEMINI_API_KEY="synthetic-private-value",DATABASE_URL="synthetic-private-database")
    assert "synthetic-private-value" not in str(error.value)
    assert "synthetic-private-database" not in str(error.value)
