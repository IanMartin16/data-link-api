import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.job import ProcessingJob
from app.enums.job_status import JobStatus
from app.services.processing_service import processing_service
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class WorkerService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
    
    def start(self):
        if not settings.worker_enabled:
            logger.info("Worker deshabilitado")
            return
        
        self.scheduler.add_job(
            self.process_pending_jobs,
            'interval',
            seconds=settings.worker_interval_seconds,
            id='process_jobs'
        )
        self.scheduler.start()
        logger.info(f"Worker iniciado (cada {settings.worker_interval_seconds}s)")
    
    def stop(self):
        self.scheduler.shutdown()
        logger.info("Worker detenido")
    
    def process_pending_jobs(self):
        db: Session = SessionLocal()
        try:
            # Buscar jobs pendientes
            pending_jobs = db.query(ProcessingJob)\
                .filter(ProcessingJob.status == JobStatus.PENDING)\
                .order_by(ProcessingJob.created_at)\
                .limit(5)\
                .all()
            
            for job in pending_jobs:
                logger.info(f"Procesando job {job.id}")
                try:
                    processing_service.process_job(db, job)
                    logger.info(f"Job {job.id} completado")
                except Exception as e:
                    logger.error(f"Error procesando job {job.id}: {e}")
        finally:
            db.close()

worker_service = WorkerService()
