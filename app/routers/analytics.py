from fastapi import APIRouter, Depends
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/usage")
async def get_usage_stats(user = Depends(verify_api_key)):
    """
    Retorna stats de uso del usuario
    """
    
    return {
        "plan": user.plan,
        "files_processed_this_month": user.files_processed_this_month,
        "files_processed_total": user.files_processed_total,
        "last_reset_date": user.last_reset_date,
        "limits": {
            "files_per_month": get_plan_limit(user.plan, "files_per_month"),
            "max_file_size_mb": get_plan_limit(user.plan, "max_file_size_mb"),
            "requests_per_hour": get_plan_limit(user.plan, "requests_per_hour")
        },
        "usage_percentage": (
            user.files_processed_this_month / 
            get_plan_limit(user.plan, "files_per_month")
        ) * 100 if get_plan_limit(user.plan, "files_per_month") != -1 else 0
    }