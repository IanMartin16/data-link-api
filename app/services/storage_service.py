from datetime import timedelta
from io import BytesIO
from typing import BinaryIO
import uuid

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

settings = get_settings()


class StorageService:
    def __init__(self):
        self.backend = settings.storage_backend
        self.bucket = settings.resolved_storage_bucket
        self.bucket_name = (
            getattr(settings, "s3_bucket", None)
            or getattr(settings, "storage_bucket", None)
            or getattr(settings, "minio_bucket", None)
        )
        if not self.bucket_name:
            raise RuntimeError("Storage bucket is not configured.")

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

    @staticmethod
    def _extension(filename: str) -> str:
        name = filename or ""
        return name.rsplit(".", 1)[-1].lower() if "." in name else "dat"

    # ------------------------------------------------------------------
    # Streaming — usar estos
    # ------------------------------------------------------------------
    def upload_stream(self, stream: BinaryIO, length: int, original_filename: str) -> str:
        """
        Sube desde un objeto de archivo sin leerlo a memoria.

        `UploadFile.file` de FastAPI ya es un archivo temporal en disco arriba
        de 1 MB, asi que se puede pasar tal cual: put_object lo lee por partes.
        """
        object_name = f"uploads/{uuid.uuid4()}.{self._extension(original_filename)}"

        stream.seek(0)
        self.client.put_object(self.bucket, object_name, stream, length)

        return object_name

    def download_to_path(self, object_name: str, destination: str) -> str:
        """Baja el objeto directo a disco. Nunca pasa por RAM."""
        self.client.fget_object(self.bucket, object_name, destination)
        return destination

    def save_result_from_path(self, source_path: str, job_id: str, format: str) -> str:
        """Sube el resultado desde disco. Nunca pasa por RAM."""
        clean_format = format.lower().replace(".", "")
        object_name = f"results/{job_id}.{clean_format}"

        self.client.fput_object(self.bucket, object_name, source_path)

        return object_name

    # ------------------------------------------------------------------
    # En memoria — solo para archivos chicos (descarga directa < 5 MB)
    # ------------------------------------------------------------------
    def download_file(self, object_name: str) -> bytes:
        """
        Lee el objeto COMPLETO a memoria.

        Solo para la descarga directa de archivos chicos en la ruta
        /jobs/{id}/download. El worker usa download_to_path.
        """
        response = None

        try:
            response = self.client.get_object(self.bucket, object_name)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def upload_file(self, file_data: bytes, original_filename: str) -> str:
        """Legado: mantiene el archivo entero en RAM. Preferir upload_stream."""
        object_name = f"uploads/{uuid.uuid4()}.{self._extension(original_filename)}"

        self.client.put_object(
            self.bucket, object_name, BytesIO(file_data), len(file_data)
        )

        return object_name

    def save_result(self, data: bytes, job_id: str, format: str) -> str:
        """Legado: mantiene el archivo entero en RAM. Preferir save_result_from_path."""
        clean_format = format.lower().replace(".", "")
        object_name = f"results/{job_id}.{clean_format}"

        self.client.put_object(self.bucket, object_name, BytesIO(data), len(data))

        return object_name

    # ------------------------------------------------------------------
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
            self.bucket, object_name, expires=timedelta(hours=expires_hours)
        )

    def get_file_size(self, object_name: str) -> int:
        try:
            stat = self.client.stat_object(self.bucket, object_name)
            return stat.size
        except S3Error:
            return 0


storage_service = StorageService()
