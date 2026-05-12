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
    Return an optional API key for public endpoints.
    """
    return x_api_key


async def verify_api_key(
    x_api_key: str = Header(..., description="Your API key"),
    db: Session = Depends(get_db)
) -> User:
    """
    Validate API key and return the authenticated user.

    Usage:
        @router.post("/endpoint")
        async def endpoint(user: User = Depends(verify_api_key)):
            ...
    """

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )

    user = db.query(User).filter(User.api_key == x_api_key).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive. Contact support."
        )

    return user


async def check_plan_limits(
    user: User = Depends(verify_api_key),
    db: Session = Depends(get_db)
) -> tuple[User, PlanLimits]:
    """
    Validate that the authenticated user is within plan limits.

    Usage:
        @router.post("/process")
        async def process(auth: tuple = Depends(check_plan_limits)):
            user, limits = auth
    """

    limits = db.query(PlanLimits).filter(
        PlanLimits.plan == user.plan
    ).first()

    if not limits:
        raise HTTPException(
            status_code=500,
            detail="Plan configuration error. Contact support."
        )

    if not limits.is_unlimited_files:
        if user.files_processed_this_month >= limits.files_per_month:
            reset_date = (
                user.last_reset_date.strftime("%Y-%m-%d")
                if user.last_reset_date else None
            )

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Monthly file limit reached",
                    "files_processed": user.files_processed_this_month,
                    "plan_limit": limits.files_per_month,
                    "reset_date": reset_date,
                    "current_plan": user.plan,
                    "upgrade_options": _get_upgrade_options(user.plan)
                }
            )

    return user, limits


def validate_file_size(file_size_bytes: int, limits: PlanLimits, user: User):
    """
    Validate file size against current plan.
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


def validate_record_count(record_count: int, limits: PlanLimits, user: User):
    """
    Validate record count against current plan.
    """

    if record_count > limits.max_records_per_file:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Record count exceeds plan limit",
                "your_record_count": record_count,
                "plan_limit_records": limits.max_records_per_file,
                "current_plan": user.plan,
                "upgrade_options": _get_upgrade_options(user.plan)
            }
        )


def validate_preset_access(preset: PresetOperation, user: User):
    """
    Validate preset availability by plan.

    FREE plan only has access to 2 presets.
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
                    "error": "Preset not available for current plan",
                    "requested_preset": preset.display_name,
                    "available_presets": [p.display_name for p in allowed_presets],
                    "current_plan": user.plan,
                    "upgrade_options": _get_upgrade_options(user.plan)
                }
            )


def validate_custom_filter_access(
    has_custom_filter: bool,
    limits: PlanLimits,
    user: User
):
    """
    Validate custom filter availability by plan.
    """

    if has_custom_filter and not limits.custom_filters_allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Custom filters are not available for current plan",
                "current_plan": user.plan,
                "upgrade_options": _get_upgrade_options(user.plan)
            }
        )


def _get_upgrade_options(current_plan: str) -> dict | None:
    """
    Return upgrade guidance for the current plan.
    """

    upgrade_paths = {
        "FREE": {
            "recommended_plan": "STARTER",
            "benefits": [
                "Higher monthly file limits",
                "Larger file size limits",
                "Access to all presets",
                "Custom filters"
            ]
        },
        "STARTER": None
    }

    return upgrade_paths.get(current_plan)