from minio import Minio
from minio.error import S3Error
from io import BytesIO
import uuid
from app.config import get_settings

settings = get_settings()

class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        self._ensure_bucket()
    
    def _ensure_bucket(self):
        """Crea el bucket si no existe"""
        try:
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
        except S3Error as e:
            print(f"Error creando bucket: {e}")
    
    def upload_file(self, file_data: bytes, original_filename: str) -> str:
        """Sube un archivo y retorna la URL"""
        file_id = str(uuid.uuid4())
        extension = original_filename.split('.')[-1]
        object_name = f"uploads/{file_id}.{extension}"
        
        self.client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(file_data),
            len(file_data)
        )
        
        return object_name
    
    def download_file(self, object_name: str) -> bytes:
        """Descarga un archivo"""
        response = self.client.get_object(settings.minio_bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    
    def save_result(self, data: bytes, job_id: str, format: str) -> str:
        """Guarda el resultado procesado"""
        object_name = f"results/{job_id}.{format}"
        
        self.client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            len(data)
        )
        
        return object_name
    
    def delete_file(self, object_name: str) -> bool:
        """
        Elimina un archivo del storage.
        
        Returns:
            True si se eliminó exitosamente
            False si el archivo no existía
        """
        try:
            self.client.remove_object(settings.minio_bucket, object_name)
            return True
        except S3Error as e:
            # Si el objeto no existe, no es un error crítico
            if e.code == 'NoSuchKey':
                return False
            raise
    
    def get_presigned_url(self, object_name: str, expires_hours: int = 24) -> str:
        """
        Genera URL temporal para descarga.
        
        Args:
            object_name: Nombre del objeto en MinIO
            expires_hours: Horas de validez (default: 24)
        
        Returns:
            URL pre-firmada válida por el tiempo especificado
        """
        from datetime import timedelta
        return self.client.presigned_get_object(
            settings.minio_bucket,
            object_name,
            expires=timedelta(hours=expires_hours)
        )
    
    def get_file_size(self, object_name: str) -> int:
        """
        Obtiene el tamaño de un archivo en bytes.
        
        Útil para verificar tamaños antes de descargar.
        """
        try:
            stat = self.client.stat_object(settings.minio_bucket, object_name)
            return stat.size
        except S3Error:
            return 0

storage_service = StorageService()
