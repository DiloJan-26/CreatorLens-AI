import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger

from app.core.config import get_settings
from app.core.logging import configure_secret_safe_worker_logging


logger = logging.getLogger(__name__)
settings = get_settings()


def _secure_redis_url(url: str | None, *, fallback: str) -> str:
    if not url:
        return fallback

    parsed = urlsplit(url)
    if parsed.scheme != "rediss":
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("ssl_cert_reqs", "required")
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


broker_url = _secure_redis_url(
    settings.celery_broker_url,
    fallback="memory://",
)
result_backend = _secure_redis_url(
    settings.celery_result_backend,
    fallback="cache+memory://",
)

if settings.celery_broker_url is None:
    logger.warning(
        "REDIS_URL is not configured; Celery is using an in-process test broker."
    )


celery_app = Celery(
    "creatorlens",
    broker=broker_url,
    backend=result_backend,
    include=[
        "app.workers.ingestion_tasks",
        "app.workers.indexing_tasks",
    ],
)

celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="creatorlens",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=settings.celery_broker_connection_timeout_seconds,
    broker_pool_limit=2,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 1,
    },
    broker_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout_seconds,
        "socket_connect_timeout": settings.celery_broker_connection_timeout_seconds,
        "socket_timeout": settings.celery_broker_connection_timeout_seconds,
    },
    result_expires=settings.celery_result_expires_seconds,
)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _configure_worker_logging(logger: logging.Logger, **_: object) -> None:
    configure_secret_safe_worker_logging(logger)

