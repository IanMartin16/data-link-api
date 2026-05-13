import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.job import ProcessingJob
from app.enums.job_status import JobStatus
from app.services.processing_service import processing_service
from app.services.cleanup_service import cleanup_service
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class WorkerService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.started = False

    def start(self):
        if not settings.worker_enabled:
            logger.info("Worker deshabilitado")
            return

        if self.started:
            logger.info("Worker ya estaba iniciado")
            return

        self.scheduler.add_job(
            self.process_pending_jobs,
            "interval",
            seconds=settings.worker_interval_seconds,
            id="process_jobs",
            replace_existing=True
        )

        if settings.cleanup_enabled:
            self.scheduler.add_job(
                self.cleanup_expired_files,
                "interval",
                seconds=settings.cleanup_interval_seconds,
                id="cleanup_expired_files",
                replace_existing=True
            )

            logger.info(
                f"Cleanup worker iniciado "
                f"(cada {settings.cleanup_interval_seconds}s)"
            )
        else:
            logger.info("Cleanup worker deshabilitado")

        self.scheduler.start()
        self.started = True

        logger.info(
            f"Worker iniciado "
            f"(process cada {settings.worker_interval_seconds}s)"
        )

    def stop(self):
        if self.started and self.scheduler.running:
            self.scheduler.shutdown()
            self.started = False
            logger.info("Worker detenido")

    def process_pending_jobs(self):
        db: Session = SessionLocal()

        try:
            pending_jobs = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.status == JobStatus.PENDING)
                .order_by(ProcessingJob.created_at)
                .limit(5)
                .all()
            )

            for job in pending_jobs:
                logger.info(f"Procesando job {job.id}")

                try:
                    processing_service.process_job(db, job)
                    logger.info(f"Job {job.id} completado")
                except Exception as e:
                    logger.error(f"Error procesando job {job.id}: {e}")

        finally:
            db.close()

    def cleanup_expired_files(self):
        db: Session = SessionLocal()

        try:
            result = cleanup_service.cleanup_expired_files(db)
            logger.info(f"Cleanup ejecutado: {result}")

        except Exception as e:
            logger.error(f"Error ejecutando cleanup: {e}")

        finally:
            db.close()


worker_service = WorkerService()