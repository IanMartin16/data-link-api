from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str

    # Storage - new generic config
    storage_backend: str = "minio"  # minio | s3
    storage_endpoint: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    storage_bucket: str | None = None
    storage_secure: bool | None = None
    storage_auto_create_bucket: bool = True

    # MinIO - legacy/local config
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str | None = None
    minio_secure: bool = False

    # Cleanup
    cleanup_enabled: bool = True
    cleanup_interval_seconds: int = 3600

    # App
    max_file_size_mb: int = 500
    worker_enabled: bool = True
    worker_interval_seconds: int = 15
    environment: str = "development"

    class Config:
        env_file = ".env"

    @property
    def resolved_storage_endpoint(self) -> str:
        value = self.storage_endpoint or self.minio_endpoint
        if not value:
            raise ValueError("Storage endpoint is required")
        return value

    @property
    def resolved_storage_access_key(self) -> str:
        value = self.storage_access_key or self.minio_access_key
        if not value:
            raise ValueError("Storage access key is required")
        return value

    @property
    def resolved_storage_secret_key(self) -> str:
        value = self.storage_secret_key or self.minio_secret_key
        if not value:
            raise ValueError("Storage secret key is required")
        return value

    @property
    def resolved_storage_bucket(self) -> str:
        value = self.storage_bucket or self.minio_bucket
        if not value:
            raise ValueError("Storage bucket is required")
        return value

    @property
    def resolved_storage_secure(self) -> bool:
        if self.storage_secure is not None:
            return self.storage_secure
        return self.minio_secure


@lru_cache()
def get_settings():
    return Settings()