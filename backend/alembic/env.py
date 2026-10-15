from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    target = context.get_x_argument(as_dictionary=True).get("database", "default")
    if target not in {"default", "test"}:
        raise RuntimeError("Alembic database target must be 'default' or 'test'.")

    url = get_settings().sqlalchemy_database_url(test=target == "test")
    variable = "TEST_DATABASE_URL" if target == "test" else "DATABASE_URL"
    if url is None:
        raise RuntimeError(f"{variable} is not configured.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    except OperationalError as exc:
        target = context.get_x_argument(as_dictionary=True).get(
            "database", "default"
        )
        variable = "TEST_DATABASE_URL" if target == "test" else "DATABASE_URL"
        raise RuntimeError(
            f"Could not connect using {variable} within "
            f"{settings.db_connect_timeout_seconds} seconds. Verify the Neon "
            "branch connection string, branch availability, DNS, and outbound "
            "access to PostgreSQL port 5432."
        ) from exc


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
