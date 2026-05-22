import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import OperationalError, SQLAlchemyError
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
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        if settings.cleanup_enabled:
            self.scheduler.add_job(
                self.cleanup_expired_files,
                "interval",
                seconds=settings.cleanup_interval_seconds,
                id="cleanup_expired_files",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
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
            self.recover_stuck_jobs(db)

            pending_jobs = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.status == JobStatus.PENDING)
                .order_by(ProcessingJob.created_at)
                .limit(5)
                .all()
            )

            if not pending_jobs:
                logger.debug("No hay jobs pendientes")
                return

            logger.info(f"Jobs pendientes encontrados: {len(pending_jobs)}")

            for job in pending_jobs:
                logger.info(f"Procesando job {job.id}")

                try:
                    processing_service.process_job(db, job)
                    db.commit()
                    logger.info(f"Job {job.id} completado")

                except OperationalError as e:
                    db.rollback()
                    logger.warning(
                        f"DB temporalmente no disponible procesando job {job.id}. "
                        f"Se reintentará en el siguiente ciclo.",
                        exc_info=e,
                    )
                    return

                except SQLAlchemyError as e:
                    db.rollback()
                    logger.error(
                        f"Error SQLAlchemy procesando job {job.id}",
                        exc_info=e,
                    )

                except Exception as e:
                    db.rollback()
                    logger.error(
                        f"Error procesando job {job.id}: {e}",
                        exc_info=e,
                    )

        except OperationalError as e:
            db.rollback()
            logger.warning(
                "DB temporalmente no disponible al consultar jobs pendientes. "
                "El worker reintentará en el siguiente ciclo.",
                exc_info=e,
            )

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(
                "Error SQLAlchemy en process_pending_jobs",
                exc_info=e,
            )

        except Exception as e:
            db.rollback()
            logger.exception(
                f"Error inesperado en process_pending_jobs: {e}"
            )

        finally:
            db.close()

    def recover_stuck_jobs(self, db: Session):
        """
        Recupera jobs que quedaron atorados en PROCESSING por una caída,
        restart o pérdida temporal de conexión con la DB.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=15)

        stuck_jobs = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == JobStatus.PROCESSING)
            .filter(ProcessingJob.updated_at < cutoff)
            .all()
        )

        if not stuck_jobs:
            return

        for job in stuck_jobs:
            logger.warning(
                f"Recuperando job atorado {job.id}. "
                f"updated_at={job.updated_at}"
            )

            job.status = JobStatus.PENDING
            job.error_message = "Recovered from interrupted processing"

        db.commit()

        logger.warning(
            f"Jobs atorados recuperados: {len(stuck_jobs)}"
        )

    def cleanup_expired_files(self):
        db: Session = SessionLocal()

        try:
            result = cleanup_service.cleanup_expired_files(db)
            db.commit()
            logger.info(f"Cleanup ejecutado: {result}")

        except OperationalError as e:
            db.rollback()
            logger.warning(
                "DB temporalmente no disponible durante cleanup. "
                "Se reintentará en el siguiente ciclo.",
                exc_info=e,
            )

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(
                "Error SQLAlchemy ejecutando cleanup",
                exc_info=e,
            )

        except Exception as e:
            db.rollback()
            logger.error(
                f"Error ejecutando cleanup: {e}",
                exc_info=e,
            )

        finally:
            db.close()


worker_service = WorkerService()