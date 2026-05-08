from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.models.plan_limits import PlanLimits
from app.enums.preset_operation import PresetOperation


async def get_api_key_optional(
    x_api_key: Optional[str] = Header(None, description="Your API key")
) -> Optional[str]:
    """
    Obtiene API key opcional (para endpoints públicos)
    """
    return x_api_key


async def verify_api_key(
    x_api_key: str = Header(..., description="Your API key"),
    db: Session = Depends(get_db)
) -> User:
    """
    Verifica API key y retorna usuario
    
    Uso:
        @router.post("/endpoint")
        async def endpoint(user: User = Depends(verify_api_key)):
            # user está autenticado
    """
    
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )
    
    # Buscar usuario por API key
    user = db.query(User).filter(User.api_key == x_api_key).first()
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account suspended. Contact support@datalink.com"
        )
    
    return user


async def check_plan_limits(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
) -> tuple[User, PlanLimits]:
    """
    Verifica que el usuario no haya excedido sus límites mensuales
    
    Uso:
        @router.post("/process")
        async def process(auth: tuple = Depends(check_plan_limits)):
            user, limits = auth
    """
    
    # Obtener límites del plan
    limits = db.query(PlanLimits).filter(
        PlanLimits.plan == user.plan
    ).first()
    
    if not limits:
        raise HTTPException(
            status_code=500,
            detail="Plan configuration error. Contact support."
        )
    
    # Verificar límite mensual de archivos
    if not limits.is_unlimited_files:
        if user.files_processed_this_month >= limits.files_per_month:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Monthly file limit reached",
                    "files_processed": user.files_processed_this_month,
                    "plan_limit": limits.files_per_month,
                    "reset_date": user.last_reset_date.strftime("%Y-%m-%d"),
                    "current_plan": user.plan,
                    "upgrade_options": _get_upgrade_options(user.plan)
                }
            )
    
    return user, limits


def validate_file_size(file_size_bytes: int, limits: PlanLimits, user: User):
    """
    Valida que el archivo no exceda el límite del plan
    
    Uso:
        validate_file_size(file_size, limits, user)
    """
    
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    if file_size_mb > limits.max_file_size_mb:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "File size exceeds plan limit",
                "your_file_size_mb": round(file_size_mb, 2),
                "plan_limit_mb": limits.max_file_size_mb,
                "current_plan": user.plan,
                "upgrade_options": _get_upgrade_options(user.plan)
            }
        )


def validate_preset_access(preset: PresetOperation, user: User):
    """
    Valida que el usuario tenga acceso al preset
    
    FREE plan solo tiene acceso a 2 presets
    """
    
    if user.plan == "FREE":
        allowed_presets = [
            PresetOperation.REMOVE_DUPLICATES_BY_EMAIL,
            PresetOperation.REMOVE_DUPLICATES_BY_ID
        ]
        
        if preset not in allowed_presets:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Preset not available in FREE plan",
                    "requested_preset": preset.display_name,
                    "available_presets": [p.display_name for p in allowed_presets],
                    "upgrade_options": _get_upgrade_options(user.plan)
                }
            )


def validate_custom_filter_access(has_custom_filter: bool, limits: PlanLimits, user: User):
    """
    Valida que el usuario pueda usar filtros custom
    
    FREE plan no tiene acceso a filtros custom
    """
    
    if has_custom_filter and not limits.custom_filters_allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Custom filters not available in FREE plan",
                "current_plan": user.plan,
                "upgrade_options": _get_upgrade_options(user.plan)
            }
        )


def _get_upgrade_options(current_plan: str) -> dict:
    """
    Retorna opciones de upgrade según el plan actual
    """
    
    upgrade_paths = {
        "FREE": {
            "recommended_plan": "STARTER",
            "price": "$29/month",
            "benefits": [
                "100 files/month (vs 10)",
                "100 MB files (vs 10 MB)",
                "All 5 presets",
                "Custom filters"
            ]
        },
        "STARTER": {
            "recommended_plan": "PRO",
            "price": "$99/month",
            "benefits": [
                "500 files/month (vs 100)",
                "500 MB files (vs 100 MB)",
                "3 API keys",
                "Priority support",
                "99.5% SLA"
            ]
        },
        "PRO": {
            "recommended_plan": "BUSINESS",
            "price": "$299/month",
            "benefits": [
                "Unlimited files",
                "2 GB files (vs 500 MB)",
                "10 API keys",
                "4h support",
                "99.9% SLA"
            ]
        },
        "BUSINESS": None  # Ya está en el plan más alto
    }
    
    return upgrade_paths.get(current_plan)
