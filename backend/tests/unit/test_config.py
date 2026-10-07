from app.core.config import Settings


def test_database_urls_are_loaded_from_environment(monkeypatch) -> None:
    development_url = "postgresql+psycopg://user:password@example.test/creatorlens"
    test_url = "postgresql+psycopg://user:password@example.test/creatorlens_test"

    monkeypatch.setenv("DATABASE_URL", development_url)
    monkeypatch.setenv("TEST_DATABASE_URL", test_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == development_url
    assert settings.test_database_url == test_url
    assert settings.sqlalchemy_database_url() == development_url
    assert settings.sqlalchemy_database_url(test=True) == test_url


def test_database_url_normalizes_neon_postgres_scheme(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.test/creatorlens?sslmode=require",
    )

    settings = Settings(_env_file=None)

    assert settings.sqlalchemy_database_url() == (
        "postgresql+psycopg://user:password@example.test/creatorlens"
        "?sslmode=require"
    )


def test_database_connection_timeout_has_bounded_default(monkeypatch) -> None:
    monkeypatch.delenv("DB_CONNECT_TIMEOUT_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.db_connect_timeout_seconds == 10


def test_redis_url_is_default_celery_transport(monkeypatch) -> None:
    redis_url = "rediss://default:password@example.test:6379"
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)

    settings = Settings(_env_file=None)

    assert settings.celery_broker_url == redis_url
    assert settings.celery_result_backend == redis_url


def test_celery_transport_overrides_are_supported(monkeypatch) -> None:
    monkeypatch.setenv(
        "REDIS_URL",
        "rediss://default:password@shared.example.test:6379",
    )
    monkeypatch.setenv(
        "CELERY_BROKER_URL",
        "rediss://default:password@broker.example.test:6379",
    )
    monkeypatch.setenv(
        "CELERY_RESULT_BACKEND",
        "rediss://default:password@results.example.test:6379",
    )

    settings = Settings(_env_file=None)

    assert settings.celery_broker_url.endswith("@broker.example.test:6379")
    assert settings.celery_result_backend.endswith("@results.example.test:6379")
