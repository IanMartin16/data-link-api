from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.user import User
from app.models.job import ProcessingJob
from app.models.plan_limits import PlanLimits
from app.enums.job_status import JobStatus
from app.enums.preset_operation import PresetOperation


router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None

    if len(api_key) <= 10:
        return "****"

    return f"{api_key[:6]}************{api_key[-4:]}"


def calculate_reduction(job: ProcessingJob) -> float:
    if not job.total_records or job.total_records <= 0:
        return 0

    reduced = (job.duplicates_removed or 0) + (job.records_filtered or 0)
    return round((reduced * 100.0) / job.total_records, 2)


@router.get("/dashboard")
async def get_dashboard(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return all data needed by Data_Link Console v0.1.

    Includes:
    - user
    - api key masked
    - usage
    - plan limits
    - analytics summary
    - recent jobs
    - billing status
    """

    limits = db.query(PlanLimits).filter(PlanLimits.plan == user.plan).first()

    if not limits:
        raise HTTPException(
            status_code=500,
            detail="Plan limits are not configured."
        )

    usage_percentage = 0

    if not limits.is_unlimited_files and limits.files_per_month > 0:
        usage_percentage = (
            user.files_processed_this_month / limits.files_per_month
        ) * 100

    all_user_jobs_query = db.query(ProcessingJob).filter(
        ProcessingJob.user_id == user.id
    )

    total_jobs = all_user_jobs_query.count()

    completed_jobs = all_user_jobs_query.filter(
        ProcessingJob.status == JobStatus.COMPLETED
    ).all()

    failed_jobs_count = all_user_jobs_query.filter(
        ProcessingJob.status == JobStatus.FAILED
    ).count()

    processing_jobs_count = all_user_jobs_query.filter(
        ProcessingJob.status == JobStatus.PROCESSING
    ).count()

    pending_jobs_count = all_user_jobs_query.filter(
        ProcessingJob.status == JobStatus.PENDING
    ).count()

    total_records_processed = sum(
        (job.total_records or 0) for job in completed_jobs
    )

    duplicates_removed = sum(
        (job.duplicates_removed or 0) for job in completed_jobs
    )

    records_filtered = sum(
        (job.records_filtered or 0) for job in completed_jobs
    )

    records_kept = sum(
        (job.records_kept or 0) for job in completed_jobs
    )

    average_reduction_percentage = 0

    if total_records_processed > 0:
        average_reduction_percentage = round(
            ((duplicates_removed + records_filtered) * 100.0) / total_records_processed,
            2
        )

    recent_jobs = (
        all_user_jobs_query
        .order_by(ProcessingJob.created_at.desc())
        .limit(5)
        .all()
    )

    recent_jobs_payload = []

    for job in recent_jobs:
        can_download = (
            job.status == JobStatus.COMPLETED
            and bool(job.output_file_url)
            and not job.files_deleted
        )

        recent_jobs_payload.append({
            "job_id": str(job.id),
            "status": job.status.value,
            "format": job.format.value,
            "preset": job.preset.display_name,
            "original_file_name": job.original_file_name,
            "file_size_mb": job.file_size_mb,
            "total_records": job.total_records,
            "duplicates_removed": job.duplicates_removed,
            "records_filtered": job.records_filtered,
            "records_kept": job.records_kept,
            "reduction_percentage": calculate_reduction(job),
            "can_download": can_download,
            "download_url": f"/api/v1/jobs/{job.id}/download" if can_download else None,
            "expires_at": job.expires_at.isoformat() if job.expires_at else None,
            "files_deleted": job.files_deleted,
            "files_deleted_at": job.files_deleted_at.isoformat() if job.files_deleted_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error_message if job.status == JobStatus.FAILED else None
        })

    can_upgrade = user.plan == "FREE"

    all_presets = [
        {
            "value": preset.value,
            "display_name": preset.display_name,
            "description": preset.description,
            "available": True
        }
        for preset in PresetOperation
    ]

    if user.plan == "FREE":
        free_allowed = [
            PresetOperation.REMOVE_DUPLICATES_BY_EMAIL.value,
            PresetOperation.REMOVE_DUPLICATES_BY_ID.value
        ]

        for preset in all_presets:
            preset["available"] = preset["value"] in free_allowed
            if not preset["available"]:
                preset["locked_message"] = "Upgrade to STARTER to unlock this preset."

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "plan": user.plan,
            "is_active": user.is_active
        },
        "api_key": {
            "masked": mask_api_key(user.api_key)
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
            "num_presets": limits.num_presets,
            "custom_filters_allowed": limits.custom_filters_allowed,
            "api_keys_count": limits.api_keys_count,
            "requests_per_hour": limits.requests_per_hour
        },
        "presets": all_presets,
        "analytics": {
            "total_jobs": total_jobs,
            "completed_jobs": len(completed_jobs),
            "failed_jobs": failed_jobs_count,
            "processing_jobs": processing_jobs_count,
            "pending_jobs": pending_jobs_count,
            "total_records_processed": total_records_processed,
            "duplicates_removed": duplicates_removed,
            "records_filtered": records_filtered,
            "records_kept": records_kept,
            "average_reduction_percentage": average_reduction_percentage
        },
        "recent_jobs": recent_jobs_payload,
        "billing": {
            "plan": user.plan,
            "billing_status": getattr(user, "billing_status", None),
            "stripe_customer_id": getattr(user, "stripe_customer_id", None),
            "can_upgrade": can_upgrade,
            "target_plan": "STARTER" if can_upgrade else None
        },
        "service": {
            "name": "Data_Link API",
            "status": "operational"
        }
    }