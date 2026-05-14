from sqlalchemy.orm import Session
from fastapi import UploadFile
from uuid import UUID

from app.models.job import ProcessingJob
from app.schemas.job import ProcessingRequest
from app.enums.file_format import FileFormat
from app.services.storage_service import storage_service
from app.processors.csv_processor import CsvProcessor
from app.processors.json_processor import JsonProcessor

class ProcessingService:
    def create_job(self, db: Session, file: UploadFile, request: ProcessingRequest) -> ProcessingJob:
        # Leer archivo
        file_data = file.file.read()
        file_size = len(file_data)
        
        # Subir a storage
        input_url = storage_service.upload_file(file_data, file.filename)

        del file_data
        
        # Crear job en BD
        job = ProcessingJob(
            format=request.format,
            preset=request.preset,
            input_file_url=input_url,
            original_file_name=file.filename,
            file_size_bytes=file_size,
            filter_field=request.filter_field,
            filter_value=request.filter_value,
            filter_operator=request.filter_operator
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)   
        
        return job
    
    def process_job(self, db: Session, job: ProcessingJob):

        input_data = None
        processor = None
        result = None

        try:
            # Marcar como procesando
            job.mark_as_processing()
            db.commit()
            
            # Descargar archivo
            input_data = storage_service.download_file(job.input_file_url)
            
            # Seleccionar processor
            if job.format == FileFormat.CSV:
                processor = CsvProcessor(
                    job.preset,
                    job.filter_field,
                    job.filter_value,
                    job.filter_operator
                )
            elif job.format == FileFormat.JSON:
                processor = JsonProcessor(
                    job.preset,
                    job.filter_field,
                    job.filter_value,
                    job.filter_operator
                )
            else:
                raise ValueError(f"Formato no soportado: {job.format}")
            
            # Procesar
            result = processor.process(input_data)
            
            del input_data
            input_data = None

            del processor
            processor = None

            # Guardar resultado
            output_url = storage_service.save_result(
                result.data, 
                str(job.id), 
                job.format.value
            )
            
            # Actualizar job
            job.mark_as_completed(
                output_url,
                result.total_records,
                result.duplicates_removed,
                result.records_filtered
            )
            db.commit()   

            del result
            result = None

            try:
                storage_service_delete_file(job.input_file_url)
            except Exception as e:
                print(f"Warning: Could not delete input file: {e}")    
            
        except Exception as e:
            job.mark_as_failed(str(e))
            db.commit()
            raise

        finally:
            if input_data is not None:
                del input_data
            if processor is not None:
                del processor
            if result is not None:
                del result            

processing_service = ProcessingService()
