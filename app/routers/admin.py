from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.services.orphan_cleanup_service import orphan_cleanup_service

settings = get_settings()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/storage/cleanup-orphans")
async def cleanup_orphan_storage(
    dry_run: bool = True,
    grace_minutes: int = 60,
    x_admin_token: str | None = Header(default=None)
):
    """
    Cleanup storage objects that are not referenced in processing_jobs.

    Use dry_run=true first.
    """

    if not settings.admin_cleanup_token:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_CLEANUP_TOKEN is not configured."
        )

    if x_admin_token != settings.admin_cleanup_token:
        raise HTTPException(status_code=403, detail="Invalid admin token.")

    return orphan_cleanup_service.cleanup_orphans(
        grace_minutes=grace_minutes,
        dry_run=dry_run
    )