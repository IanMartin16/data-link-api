from minio import Minio
from minio.error import S3Error
from io import BytesIO
from datetime import timedelta
import uuid

from app.config import get_settings

settings = get_settings()


class StorageService:
    def __init__(self):
        self.backend = settings.storage_backend
        self.bucket = settings.resolved_storage_bucket

        self.client = Minio(
            settings.resolved_storage_endpoint,
            access_key=settings.resolved_storage_access_key,
            secret_key=settings.resolved_storage_secret_key,
            secure=settings.resolved_storage_secure,
        )

        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if self.client.bucket_exists(self.bucket):
                print(f"Storage bucket ready: {self.bucket}")
                return

            if settings.storage_auto_create_bucket:
                self.client.make_bucket(self.bucket)
                print(f"Storage bucket created: {self.bucket}")
                return

            raise RuntimeError(
                f"Storage bucket '{self.bucket}' does not exist "
                f"and auto-create is disabled."
            )

        except S3Error as e:
            print(f"Storage bucket check failed: {e}")
            raise

    def upload_file(self, file_data: bytes, original_filename: str) -> str:
        file_id = str(uuid.uuid4())
        extension = original_filename.split(".")[-1].lower()
        object_name = f"uploads/{file_id}.{extension}"

        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(file_data),
            len(file_data),
        )

        return object_name

    def download_file(self, object_name: str) -> bytes:
        response = None

        try:
            response = self.client.get_object(self.bucket, object_name)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def save_result(self, data: bytes, job_id: str, format: str) -> str:
        clean_format = format.lower().replace(".", "")
        object_name = f"results/{job_id}.{clean_format}"

        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(data),
            len(data),
        )

        return object_name

    def delete_file(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket, object_name)
            return True
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return False
            raise

    def get_presigned_url(self, object_name: str, expires_hours: int = 24) -> str:
        return self.client.presigned_get_object(
            self.bucket,
            object_name,
            expires=timedelta(hours=expires_hours),
        )

    def get_file_size(self, object_name: str) -> int:
        try:
            stat = self.client.stat_object(self.bucket, object_name)
            return stat.size
        except S3Error:
            return 0


storage_service = StorageService()