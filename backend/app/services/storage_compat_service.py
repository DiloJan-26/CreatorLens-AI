"""Selects PostgreSQL when configured and preserves SQLite as a V1 fallback.

The fallback is configuration-based only. PostgreSQL runtime failures are allowed
to surface instead of silently writing a second, divergent SQLite data store.
"""

import logging

from app.db.session import is_database_configured


logger = logging.getLogger(__name__)

if is_database_configured():
    from app.db.repositories.storage_repository import *  # noqa: F403
    logger.info("PostgreSQL persistence backend selected.")
else:
    from app.services.storage_service import *  # noqa: F403
    logger.warning(
        "DATABASE_URL is not configured; using the temporary V1 SQLite fallback."
    )
