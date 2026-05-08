# app/routers/jobs.py
"""
Router para jobs de procesamiento de datos

NUEVO en V1: Autenticación con API Key y validación de límites por plan
"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
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
from app.services.storage_service import storage_service
from app.config import get_settings

# ✅ NUEVO: Middleware de autenticación
from app.middleware.auth import (
    verify_api_key,
    check_plan_limits,
    validate_file_size,
    validate_preset_access,
    validate_custom_filter_access
)

router = APIRouter(prefix="/api/v1", tags=["jobs"])
settings = get_settings()


@router.post("/process", response_model=JobResponse)
async def create_processing_job(
    file: UploadFile = File(...),
    format: FileFormat = Form(...),
    preset: PresetOperation = Form(...),
    filter_field: str = Form(None),
    filter_value: str = Form(None),
    filter_operator: FilterOperator = Form(None),
    auth: tuple = Depends(check_plan_limits),  # ✅ NUEVO: Autenticación y validación
    db: Session = Depends(get_db)
):
    """
    Crea un job de procesamiento asíncrono.
    
    ✅ V1 FEATURES:
    - Requiere autenticación via X-API-Key header
    - Valida límites del plan automáticamente
    - Incrementa contador de uso
    - Retorna archivos restantes
    """
    
    # ✅ NUEVO: Desempacar autenticación
    user: User = auth[0]
    limits: PlanLimits = auth[1]
    
    # ✅ NUEVO: 1. Validar tamaño del archivo
    file.file.seek(0, 2)
    file_size_bytes = file.file.tell()
    file.file.seek(0)
    
    validate_file_size(file_size_bytes, limits, user)
    
    # ✅ NUEVO: 2. Validar acceso al preset
    validate_preset_access(preset, user)
    
    # ✅ NUEVO: 3. Validar filtros custom
    has_custom_filter = filter_field is not None
    validate_custom_filter_access(has_custom_filter, limits, user)
    
    # 4. Validar que el archivo no esté vacío
    if file_size_bytes == 0:
        raise HTTPException(400, detail="File is empty")
    
    # 5. Validar extensión del archivo
    filename = file.filename.lower()
    if format == FileFormat.CSV and not filename.endswith('.csv'):
        raise HTTPException(400, detail="File must have .csv extension")
    elif format == FileFormat.JSON and not filename.endswith('.json'):
        raise HTTPException(400, detail="File must have .json extension")
    
    # 6. Crear request
    request = ProcessingRequest(
        format=format,
        preset=preset,
        filter_field=filter_field,
        filter_value=filter_value,
        filter_operator=filter_operator
    )
    
    # 7. Crear job (tu código existente)
    job = processing_service.create_job(db, file, request)
    
    # ✅ NUEVO: 8. Asociar job con usuario
    job.user_id = user.id
    db.commit()
    
    # ✅ NUEVO: 9. Incrementar contador de uso
    user.increment_usage()
    db.commit()
    
    # ✅ NUEVO: 10. Calcular archivos restantes
    files_remaining = "unlimited"
    if not limits.is_unlimited_files:
        files_remaining = limits.files_per_month - user.files_processed_this_month
    
    return JobResponse(
        job_id=job.id,
        status="PENDING",
        status_url=f"/api/v1/jobs/{job.id}",
        message=f"Job created successfully. {files_remaining} files remaining this month." 
            if files_remaining != "unlimited" else "Job created successfully."
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    user: User = Depends(verify_api_key),  # ✅ NUEVO: Autenticación
    db: Session = Depends(get_db)
):
    """
    Consulta el estado de un job de procesamiento.
    
    ✅ V1: Solo puedes ver tus propios jobs
    """
    
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    
    # ✅ NUEVO: Verificar ownership
    if job.user_id and job.user_id != user.id:
        raise HTTPException(403, detail="Access denied. This job belongs to another user.")
    
    # Tu código existente para response
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
    user: User = Depends(verify_api_key),  # ✅ NUEVO: Autenticación
    db: Session = Depends(get_db)
):
    """
    Descarga el archivo procesado.
    
    ✅ V1: Solo puedes descargar tus propios jobs
    """
    
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    
    # ✅ NUEVO: Verificar ownership
    if job.user_id and job.user_id != user.id:
        raise HTTPException(403, detail="Access denied")
    
    if job.status.value != "COMPLETED":
        raise HTTPException(
            400, 
            detail=f"Job not completed. Current status: {job.status.value}"
        )
    
    if not job.output_file_url:
        raise HTTPException(404, detail="Output file not available")
    
    # Para archivos pequeños: descarga directa
    # Para archivos grandes: redirect a presigned URL
    DIRECT_DOWNLOAD_LIMIT_MB = 5
    
    if job.file_size_mb <= DIRECT_DOWNLOAD_LIMIT_MB:
        file_data = storage_service.download_file(job.output_file_url)
        
        return StreamingResponse(
            BytesIO(file_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="processed_{job.id}.{job.format.value}"'
            }
        )
    else:
        # Redirect a URL pre-firmada
        presigned_url = storage_service.get_presigned_url(job.output_file_url)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=presigned_url, status_code=302)


# ============================================
# ✅ NUEVOS ENDPOINTS V1
# ============================================

@router.get("/usage")
async def get_usage(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Retorna el uso actual del usuario y sus límites
    
    Headers:
        X-API-Key: Your API key
    
    Returns:
        - Usuario (email, plan, activo)
        - Uso (archivos procesados, porcentaje)
        - Límites del plan
    """
    
    limits = db.query(PlanLimits).filter(PlanLimits.plan == user.plan).first()
    
    if not limits:
        raise HTTPException(500, "Plan limits not configured")
    
    # Calcular porcentaje de uso
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
            "last_reset_date": user.last_reset_date.isoformat()
        },
        "limits": {
            "files_per_month": limits.files_per_month if not limits.is_unlimited_files else "unlimited",
            "max_file_size_mb": limits.max_file_size_mb,
            "max_records_per_file": limits.max_records_per_file,
            "custom_filters_allowed": limits.custom_filters_allowed,
            "requests_per_hour": limits.requests_per_hour,
            "sla_uptime": limits.sla_uptime
        }
    }


@router.get("/presets")
async def get_presets(user: User = Depends(verify_api_key)):
    """
    Lista los presets disponibles según el plan del usuario
    
    FREE plan: Solo 2 presets (email, ID)
    STARTER/PRO/BUSINESS: Todos los presets
    
    Headers:
        X-API-Key: Your API key
    
    Returns:
        - Plan actual
        - Lista de presets (con flag 'available')
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
    
    # Marcar cuáles están disponibles para FREE
    if user.plan == "FREE":
        free_allowed = [
            PresetOperation.REMOVE_DUPLICATES_BY_EMAIL.value,
            PresetOperation.REMOVE_DUPLICATES_BY_ID.value
        ]
        
        for preset in all_presets:
            preset["available"] = preset["value"] in free_allowed
            if not preset["available"]:
                preset["locked_message"] = "Upgrade to STARTER ($29/month) to unlock this preset"
    
    return {
        "plan": user.plan,
        "presets": all_presets
    }