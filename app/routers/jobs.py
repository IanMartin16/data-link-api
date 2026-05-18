from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional
from io import BytesIO

from app.database import get_db
from app.models.job import ProcessingJob
from app.models.user import User
from app.models.plan_limits import PlanLimits
from app.schemas.job import JobResponse, JobStatusResponse, JobStats, ProcessingRequest
from app.enums.file_format import FileFormat
from app.enums.preset_operation import PresetOperation
from app.enums.filter_operator import FilterOperator
from app.services.processing_service import processing_service
from app.enums.job_status import JobStatus
from app.services.storage_service import storage_service

from app.middleware.auth import (
    verify_api_key,
    check_plan_limits,
    validate_file_size,
    validate_preset_access,
    validate_custom_filter_access,
    validate_record_count,   # use this only if you wire record counting before job creation
)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

DIRECT_DOWNLOAD_LIMIT_MB = 5


@router.post("/process", response_model=JobResponse)
async def create_processing_job(
    file: UploadFile = File(...),
    format: FileFormat = Form(...),
    preset: PresetOperation = Form(...),
    filter_field: str = Form(None),
    filter_value: str = Form(None),
    filter_operator: FilterOperator = Form(None),
    auth: tuple = Depends(check_plan_limits),
    db: Session = Depends(get_db)
):
    """
    Create an asynchronous processing job.

    Requirements:
    - X-API-Key header
    - valid plan access
    - valid file size for current plan
    - valid preset access for current plan
    """

    user: User = auth[0]
    limits: PlanLimits = auth[1]

    # Validate file size
    file.file.seek(0, 2)
    file_size_bytes = file.file.tell()
    file.file.seek(0)

    validate_file_size(file_size_bytes, limits, user)

    # Validate preset access
    validate_preset_access(preset, user)

    # Validate custom filter access
    has_custom_filter = any([
        filter_field is not None,
        filter_value is not None,
        filter_operator is not None
    ])
    validate_custom_filter_access(has_custom_filter, limits, user)

    # Validate non-empty file
    if file_size_bytes == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    # Validate extension
    filename = (file.filename or "").lower()
    if format == FileFormat.CSV and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must have a .csv extension.")
    elif format == FileFormat.JSON and not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must have a .json extension.")

    # Optional future validation:
    # - record count check before creating the job
    # To enable this properly, you need a lightweight pre-read of the file.
    # validate_record_count(record_count, limits, user)

    request = ProcessingRequest(
        format=format,
        preset=preset,
        filter_field=filter_field,
        filter_value=filter_value,
        filter_operator=filter_operator
    )

    job = processing_service.create_job(db, file, request)

    retention_hours = 1 if user.plan == "FREE" else 24

    # Associate job with user
    job.user_id = user.id
    job.expires_at = datetime.utcnow() + timedelta(hours=retention_hours)
    db.commit()

    # Count usage after successful job creation
    user.increment_usage()
    db.commit()

    files_remaining = "unlimited"
    if not limits.is_unlimited_files:
        files_remaining = max(0, limits.files_per_month - user.files_processed_this_month)

    return JobResponse(
        job_id=job.id,
        status="PENDING",
        status_url=f"/api/v1/jobs/{job.id}",
        message=(
            f"Processing job created successfully. {files_remaining} files remaining this month."
            if files_remaining != "unlimited"
            else "Processing job created successfully."
        )
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return the current status of a processing job.
    Users can only access their own jobs.
    """

    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied. This job belongs to another user.")

    response = JobStatusResponse(
        job_id=job.id,
        status=job.status,
        format=job.format,
        preset=job.preset.display_name,
        original_file_name=job.original_file_name,
        file_size_mb=job.file_size_mb,
        created_at=job.created_at,
        completed_at=job.completed_at
    )

    if job.status.value == "COMPLETED":
        reduction = 0
        if job.total_records > 0:
            reduction = ((job.duplicates_removed + job.records_filtered) * 100.0) / job.total_records

        response.stats = JobStats(
            total_records=job.total_records,
            duplicates_removed=job.duplicates_removed,
            records_filtered=job.records_filtered,
            records_kept=job.records_kept,
            reduction_percentage=round(reduction, 2)
        )
        response.download_url = f"/api/v1/jobs/{job.id}/download"

    if job.status.value == "FAILED":
        response.error = job.error_message

    return response


@router.get("/jobs/{job_id}/download")
async def download_result(
    job_id: UUID,
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Download the processed output file.
    Users can only download their own jobs.

    Strategy:
    - small files: direct download
    - larger files: temporary storage redirect
    """

    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    if job.status.value != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job.status.value}."
        )

    if not job.output_file_url:
        raise HTTPException(status_code=404, detail="Processed output file is not available.")

    if job.file_size_mb <= DIRECT_DOWNLOAD_LIMIT_MB:
        file_data = storage_service.download_file(job.output_file_url)

        return StreamingResponse(
            BytesIO(file_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="processed_{job.id}.{job.format.value}"'
            }
        )

    presigned_url = storage_service.get_presigned_url(job.output_file_url)
    return RedirectResponse(url=presigned_url, status_code=302)


@router.get("/jobs/{job_id}/download-url")
async def get_download_url(
    job_id: UUID,
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return a temporary storage download URL for the processed output file.
    Recommended for large files and external integrations.
    """

    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    if job.status.value != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job is not completed yet.")

    if not job.output_file_url:
        raise HTTPException(status_code=404, detail="Processed output file is not available.")

    presigned_url = storage_service.get_presigned_url(job.output_file_url)

    return {
        "job_id": str(job.id),
        "download_url": presigned_url,
        "expires_in_hours": 24,
        "strategy": "direct_link"
    }


@router.get("/usage")
async def get_usage(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return current usage and plan limits for the authenticated user.
    """

    limits = db.query(PlanLimits).filter(PlanLimits.plan == user.plan).first()

    if not limits:
        raise HTTPException(status_code=500, detail="Plan limits are not configured.")

    usage_percentage = 0
    if not limits.is_unlimited_files:
        usage_percentage = (user.files_processed_this_month / limits.files_per_month) * 100

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
        }
    }


@router.get("/presets")
async def get_presets(user: User = Depends(verify_api_key)):
    """
    List available presets for the authenticated user's plan.

    FREE:
    - remove duplicates by email
    - remove duplicates by ID

    STARTER:
    - full preset access
    """

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
        "plan": user.plan,
        "presets": all_presets
    }

@router.get("/jobs")
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    List authenticated user's processing jobs.

    Used by Data_Link Console / Dashboard.
    """

    query = db.query(ProcessingJob).filter(ProcessingJob.user_id == user.id)

    if status:
        try:
            query = query.filter(ProcessingJob.status == JobStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    total = query.count()

    jobs = (
        query
        .order_by(ProcessingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []

    for job in jobs:
        reduction = 0

        if job.total_records and job.total_records > 0:
            reduction = (
                (job.duplicates_removed or 0) + (job.records_filtered or 0)
            ) * 100.0 / job.total_records

        can_download = (
            job.status.value == "COMPLETED"
            and bool(job.output_file_url)
            and not job.files_deleted
        )

        items.append({
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
            "reduction_percentage": round(reduction, 2),
            "download_url": f"/api/v1/jobs/{job.id}/download" if can_download else None,
            "can_download": can_download,
            "expires_at": job.expires_at,
            "files_deleted": job.files_deleted,
            "files_deleted_at": job.files_deleted_at,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error": job.error_message if job.status.value == "FAILED" else None
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }    