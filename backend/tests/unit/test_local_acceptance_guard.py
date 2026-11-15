"""The manual launcher must never accept the real remote environment targets."""
import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).parents[2]/"scripts/local_auth_acceptance.py"
spec=importlib.util.spec_from_file_location("local_auth_acceptance",p)
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


@pytest.mark.parametrize("database,redis",[("postgresql://fixture:fixture@remote.neon.tech/creatorlens_acceptance","redis://localhost:6379/15"),("postgresql://localhost/production","redis://localhost:6379/15"),("postgresql://localhost/creatorlens_acceptance","redis://remote.example/15"),("postgresql://localhost/creatorlens_acceptance","redis://localhost:6379/0")])
def test_remote_or_nondisposable_target_is_denied(database,redis):
    with pytest.raises(ValueError):launcher.validate_targets(database,redis)


def test_explicit_disposable_targets_are_accepted_without_connecting():
    launcher.validate_targets("postgresql+psycopg://localhost/creatorlens_acceptance","redis://127.0.0.1:6379/15")


def test_check_mode_strips_provider_environment_without_connecting(tmp_path):
    import os,subprocess,sys
    env=dict(os.environ,ACCEPTANCE_DATABASE_URL="postgresql+psycopg://fixture:fixture@localhost/creatorlens_acceptance",ACCEPTANCE_REDIS_URL="redis://127.0.0.1:6379/15",SUPABASE_URL="https://auth.example",SUPABASE_JWT_ISSUER="https://auth.example/auth/v1",SUPABASE_JWKS_URL="https://auth.example/auth/v1/.well-known/jwks.json",SUPABASE_JWT_AUDIENCE="authenticated",GEMINI_API_KEY="synthetic-must-strip",QDRANT_URL="https://synthetic-must-not-contact.example",PAID_OPERATIONS_ENABLED="true")
    result=subprocess.run([sys.executable,str(p),"check"],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert "No connections made" in result.stdout and "paid/extraction disabled" in result.stdout
    assert "synthetic-must-strip" not in result.stdout+result.stderr
