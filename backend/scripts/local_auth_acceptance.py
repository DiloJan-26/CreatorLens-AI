"""User-run local OAuth acceptance launcher. No live credentials are printed.
Requires an existing disposable loopback PostgreSQL and Redis DB15. Never
starts workers or enables provider calls. Default --check makes no connections.
"""
import argparse,ast,os,sys,tempfile
from contextlib import chdir
from pathlib import Path
from urllib.parse import urlsplit

BACKEND=Path(__file__).resolve().parents[1]


def validate_targets(database,redis):
    from sqlalchemy.engine import make_url
    try:
        target=make_url(database)
        broker=urlsplit(redis)
        if target.drivername not in {"postgresql","postgresql+psycopg"} or target.host not in {"localhost","127.0.0.1","::1"} or target.database!="creatorlens_acceptance":
            raise ValueError()
        if broker.scheme not in {"redis","rediss"} or broker.hostname not in {"localhost","127.0.0.1","::1"} or broker.path!="/15" or broker.query or broker.fragment:
            raise ValueError()
    except Exception:
        raise ValueError("Only disposable loopback PostgreSQL creatorlens_acceptance and loopback Redis DB15 are permitted.") from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["check","migrate","serve"],default="check",nargs="?")
    args=parser.parse_args()
    database=os.environ.get("ACCEPTANCE_DATABASE_URL","")
    redis=os.environ.get("ACCEPTANCE_REDIS_URL","")
    validate_targets(database,redis)
    from dotenv import dotenv_values
    private=dotenv_values(BACKEND/".env",interpolate=False)
    names=("SUPABASE_URL","SUPABASE_JWT_ISSUER","SUPABASE_JWKS_URL","SUPABASE_JWT_AUDIENCE")
    public_auth={name:os.environ.get(name) or private.get(name) for name in names}
    if not all(public_auth.values()):raise ValueError("Existing trusted Supabase verification configuration is required.")
    tree=ast.parse((BACKEND/"app/core/config.py").read_text(encoding="utf-8-sig"))
    aliases={kw.value.value for n in ast.walk(tree) if isinstance(n,ast.Call) for kw in n.keywords if kw.arg=="alias" and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str)}
    for name in list(os.environ):
        if name in aliases or name.startswith(("GOOGLE_","OPENAI_","LANGCHAIN_","LANGSMITH_","OTEL_")):os.environ.pop(name,None)
    os.environ.update(public_auth)
    os.environ.update(ENVIRONMENT="test",APPLICATION_ACCESS_MODE="authenticated",DEMO_ACCESS_MODE="disabled",DATABASE_URL=database,TEST_DATABASE_URL=database,REDIS_URL=redis,PAID_OPERATIONS_ENABLED="false",EXTRACTION_ENABLED="false",AUTHENTICATED_REQUESTS_PER_MINUTE="60",ANALYSIS_REQUESTS_PER_MINUTE="0",PAID_REQUESTS_PER_MINUTE="0",LLM_MODEL="gemini-3.5-flash-lite",LANGSMITH_TRACING="false",CORS_ORIGINS="http://localhost:3000")
    sys.path.insert(0,str(BACKEND))
    with tempfile.TemporaryDirectory(prefix="creatorlens-local-auth-") as temp, chdir(temp):
        # Prevent BaseSettings from reloading the real backend .env; restore cwd before cleanup.
        from app.core.config import get_settings
        get_settings.cache_clear();settings=get_settings()
        assert not settings.paid_operations_enabled and not settings.extraction_enabled
        assert not any((settings.gemini_api_key,settings.supadata_api_key,settings.apify_api_token,settings.deepgram_api_key,settings.qdrant_url))
        from app.core import paths
        paths.STORAGE_DIR=Path(temp)/"storage";paths.SQLITE_DB_PATH=paths.STORAGE_DIR/"creatorlens.db"
        if args.mode=="check":
            print("Validated: disposable loopback targets, trusted auth configuration, provider credentials removed, paid/extraction disabled. No connections made.")
        elif args.mode=="migrate":
            from alembic import command
            from alembic.config import Config
            config=Config(str(BACKEND/"alembic.ini"));config.set_main_option("script_location",str(BACKEND/"alembic"))
            command.upgrade(config,"head")
        else:
            import uvicorn
            uvicorn.run("app.main:app",host="127.0.0.1",port=8000,log_level="warning")


if __name__=="__main__":
    try:main()
    except Exception:
        print("Local acceptance launcher refused configuration or startup. Verify disposable targets and trusted auth settings privately; no credentials are printed.",file=sys.stderr)
        raise SystemExit(2) from None
