from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal
from app.services.worker_service import worker_service

logger = logging.getLogger(__name__)
settings = get_settings()


class HealthService:
    """
    Lightweight operational checks for Data_Link.

    This service must not:
    - execute processing jobs;
    - inspect pending jobs;
    - read uploaded files;
    - trigger cleanup;
    - perform heavy storage operations.
    """

    @staticmethod
    def check_database() -> tuple[str, str | None]:
        db = SessionLocal()

        try:
            db.execute(text("SELECT 1"))
            return "operational", None

        except SQLAlchemyError as exc:
            logger.warning(
                "Database health check failed: %s",
                type(exc).__name__,
                exc_info=exc,
            )
            return "degraded", type(exc).__name__

        except Exception as exc:
            logger.exception(
                "Unexpected database health check failure: %s",
                type(exc).__name__,
            )
            return "degraded", type(exc).__name__

        finally:
            db.close()

    @staticmethod
    def check_worker() -> tuple[str, str | None]:
        """
        Checks worker state without executing any scheduled job.

        A disabled worker is considered operational because it is an
        intentional configuration state.
        """
        if not settings.worker_enabled:
            return "operational", "disabled_by_configuration"

        try:
            if worker_service.started and worker_service.scheduler.running:
                return "operational", None

            return "degraded", "worker_not_running"

        except Exception as exc:
            logger.exception(
                "Worker health check failed: %s",
                type(exc).__name__,
            )
            return "degraded", type(exc).__name__

    @classmethod
    def dependency_checks(cls) -> dict:
        database_status, database_error = cls.check_database()
        worker_status, worker_error = cls.check_worker()

        overall_status = "operational"

        if (
            database_status != "operational"
            or worker_status != "operational"
        ):
            overall_status = "degraded"

        return {
            "status": overall_status,
            "checks": {
                "database": {
                    "status": database_status,
                    "error": database_error,
                },
                "worker": {
                    "status": worker_status,
                    "error": worker_error,
                },
            },
        }

    @classmethod
    def is_ready(cls) -> bool:
        result = cls.dependency_checks()
        return result["status"] == "operational"