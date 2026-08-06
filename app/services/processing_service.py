import os

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.job import ProcessingJob
from app.schemas.job import ProcessingRequest
from app.enums.file_format import FileFormat
from app.services.storage_service import storage_service
from app.processors.base_processor import make_temp_file
from app.processors.csv_processor import CsvProcessor
from app.processors.json_processor import JsonProcessor


PROCESSORS = {
    FileFormat.CSV: CsvProcessor,
    FileFormat.JSON: JsonProcessor,
}


class ProcessingService:

    def create_job(
        self, db: Session, file: UploadFile, request: ProcessingRequest
    ) -> ProcessingJob:
        """
        Sube el archivo al bucket en streaming y registra el job.

        Antes hacia file.file.read(), lo que dejaba el archivo completo en
        memoria antes de subirlo. UploadFile ya vive en disco arriba de 1 MB,
        asi que se entrega tal cual al cliente de MinIO.
        """
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)

        input_url = storage_service.upload_stream(file.file, file_size, file.filename)

        job = ProcessingJob(
            format=request.format,
            preset=request.preset,
            input_file_url=input_url,
            original_file_name=file.filename,
            file_size_bytes=file_size,
            filter_field=request.filter_field,
            filter_value=request.filter_value,
            filter_operator=request.filter_operator,
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return job

    def process_job(self, db: Session, job: ProcessingJob) -> None:
        """
        Ejecuta el job. Entrada y salida viajan por disco, nunca por memoria.

        El pico ya no depende del tamano del archivo: bucket -> temporal ->
        procesador (por bloques) -> temporal -> bucket.
        """
        input_path = None
        result = None

        try:
            job.mark_as_processing()
            db.commit()

            processor_class = PROCESSORS.get(job.format)
            if processor_class is None:
                raise ValueError(f"Formato no soportado: {job.format}")

            input_path = make_temp_file(f".{job.format.value.lower()}")
            storage_service.download_to_path(job.input_file_url, input_path)

            processor = processor_class(
                job.preset,
                job.filter_field,
                job.filter_value,
                job.filter_operator,
            )

            result = processor.process(input_path)

            output_url = storage_service.save_result_from_path(
                result.output_path, str(job.id), job.format.value
            )

            job.mark_as_completed(
                output_url,
                result.total_records,
                result.duplicates_removed,
                result.records_filtered,
            )
            db.commit()

            # El archivo fuente no sobrevive al proceso.
            try:
                storage_service.delete_file(job.input_file_url)
            except Exception as e:
                print(f"Warning: Could not delete input file: {e}")

        except Exception as e:
            job.mark_as_failed(str(e))
            db.commit()
            raise

        finally:
            # Sin esto, el disco del contenedor se llena en silencio cada vez
            # que un job truena.
            if input_path and os.path.exists(input_path):
                try:
                    os.unlink(input_path)
                except OSError:
                    pass

            if result is not None:
                result.cleanup()


processing_service = ProcessingService()
