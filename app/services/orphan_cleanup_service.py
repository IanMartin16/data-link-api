from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.job import ProcessingJob
from app.services.storage_service import storage_service
from app.config import get_settings

settings = get_settings()


class OrphanCleanupService:
    def get_referenced_objects(self, db: Session) -> set[str]:
        """
        Return all object names currently referenced by processing_jobs.
        """
        rows = db.query(
            ProcessingJob.input_file_url,
            ProcessingJob.output_file_url
        ).all()

        refs: set[str] = set()

        for input_file_url, output_file_url in rows:
            if input_file_url:
                refs.add(input_file_url)

            if output_file_url:
                refs.add(output_file_url)

        return refs

    def list_bucket_objects(self, prefixes: list[str]) -> list[dict]:
        """
        List objects from storage bucket for the given prefixes.
        """
        objects = []

        for prefix in prefixes:
            for obj in storage_service.client.list_objects(
                settings.minio_bucket,
                prefix=prefix,
                recursive=True
            ):
                objects.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                })

        return objects

    def cleanup_orphans(
        self,
        grace_minutes: int = 60,
        dry_run: bool = True
    ) -> dict:
        """
        Delete bucket objects that are not referenced by the DB.

        dry_run=True only reports what would be deleted.
        dry_run=False deletes the orphan objects.
        """

        db: Session = SessionLocal()

        try:
            referenced = self.get_referenced_objects(db)

            bucket_objects = self.list_bucket_objects(
                prefixes=["uploads/", "results/"]
            )

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=grace_minutes)

            orphan_objects = []

            for obj in bucket_objects:
                object_name = obj["object_name"]
                last_modified = obj["last_modified"]

                if object_name in referenced:
                    continue

                if last_modified and last_modified > cutoff:
                    continue

                orphan_objects.append(obj)

            deleted = []
            errors = []

            if not dry_run:
                for obj in orphan_objects:
                    object_name = obj["object_name"]

                    try:
                        storage_service.delete_file(object_name)
                        deleted.append(object_name)
                    except Exception as e:
                        errors.append({
                            "object_name": object_name,
                            "error": str(e)
                        })

            total_size_bytes = sum((obj["size"] or 0) for obj in orphan_objects)

            return {
                "dry_run": dry_run,
                "grace_minutes": grace_minutes,
                "referenced_objects": len(referenced),
                "bucket_objects_scanned": len(bucket_objects),
                "orphan_count": len(orphan_objects),
                "orphan_total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "orphans": [
                    {
                        "object_name": obj["object_name"],
                        "size_mb": round((obj["size"] or 0) / (1024 * 1024), 2),
                        "last_modified": obj["last_modified"].isoformat()
                        if obj["last_modified"] else None
                    }
                    for obj in orphan_objects
                ],
                "deleted_count": len(deleted),
                "deleted": deleted,
                "errors": errors
            }

        finally:
            db.close()


orphan_cleanup_service = OrphanCleanupService()