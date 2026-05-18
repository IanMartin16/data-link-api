from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.job import ProcessingJob
from app.models.user import User
from app.models.plan_limits import PlanLimits
from app.enums.job_status import JobStatus


router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary")
async def get_analytics_summary(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return dashboard analytics summary for the authenticated user.
    """

    limits = db.query(PlanLimits).filter(PlanLimits.plan == user.plan).first()

    if not limits:
        raise HTTPException(status_code=500, detail="Plan limits are not configured.")

    completed_jobs = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.user_id == user.id,
            ProcessingJob.status == JobStatus.COMPLETED
        )
        .all()
    )

    total_jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.user_id == user.id)
        .count()
    )

    failed_jobs = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.user_id == user.id,
            ProcessingJob.status == JobStatus.FAILED
        )
        .count()
    )

    total_records = sum((job.total_records or 0) for job in completed_jobs)
    total_duplicates_removed = sum((job.duplicates_removed or 0) for job in completed_jobs)
    total_records_filtered = sum((job.records_filtered or 0) for job in completed_jobs)
    total_records_kept = sum((job.records_kept or 0) for job in completed_jobs)

    average_reduction = 0

    if total_records > 0:
        average_reduction = (
            (total_duplicates_removed + total_records_filtered) * 100.0
        ) / total_records

    last_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.user_id == user.id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    usage_percentage = 0

    if not limits.is_unlimited_files and limits.files_per_month > 0:
        usage_percentage = (
            user.files_processed_this_month / limits.files_per_month
        ) * 100

    return {
        "user": {
            "email": user.email,
            "plan": user.plan,
            "is_active": user.is_active
        },
        "usage": {
            "files_processed_this_month": user.files_processed_this_month,
            "files_processed_total": user.files_processed_total,
            "usage_percentage": round(usage_percentage, 1),
            "last_reset_date": user.last_reset_date.isoformat() if user.last_reset_date else None
        },
        "limits": {
            "files_per_month": limits.files_per_month if not limits.is_unlimited_files else "unlimited",
            "max_file_size_mb": limits.max_file_size_mb,
            "max_records_per_file": limits.max_records_per_file,
            "custom_filters_allowed": limits.custom_filters_allowed,
            "requests_per_hour": limits.requests_per_hour
        },
        "impact": {
            "total_jobs": total_jobs,
            "completed_jobs": len(completed_jobs),
            "failed_jobs": failed_jobs,
            "total_records_processed": total_records,
            "duplicates_removed": total_duplicates_removed,
            "records_filtered": total_records_filtered,
            "records_kept": total_records_kept,
            "average_reduction_percentage": round(average_reduction, 2)
        },
        "last_job": {
            "job_id": str(last_job.id),
            "status": last_job.status.value,
            "original_file_name": last_job.original_file_name,
            "created_at": last_job.created_at,
            "completed_at": last_job.completed_at
        } if last_job else None
    }