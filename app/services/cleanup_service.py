from datetime import datetime
from sqlalchemy.orm import Session

from app.models.job import ProcessingJob
from app.enums.job_status import JobStatus
from app.services.storage_service import storage_service


class CleanupService:
    def cleanup_expired_files(self, db: Session) -> dict:
        now = datetime.utcnow()

        jobs = db.query(ProcessingJob).filter(
            ProcessingJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
            ProcessingJob.files_deleted == False,
            ProcessingJob.expires_at.isnot(None),
            ProcessingJob.expires_at <= now
        ).all()

        deleted_inputs = 0
        deleted_outputs = 0
        errors = 0

        for job in jobs:
            try:
                if job.input_file_url:
                    if storage_service.delete_file(job.input_file_url):
                        deleted_inputs += 1

                if job.output_file_url:
                    if storage_service.delete_file(job.output_file_url):
                        deleted_outputs += 1

                job.mark_files_deleted()

            except Exception as e:
                errors += 1
                print(f"❌ Cleanup error for job {job.id}: {e}")

        db.commit()

        return {
            "jobs_checked": len(jobs),
            "deleted_inputs": deleted_inputs,
            "deleted_outputs": deleted_outputs,
            "errors": errors
        }


cleanup_service = CleanupService()