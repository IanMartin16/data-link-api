from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.enums.job_status import JobStatus
from app.enums.file_format import FileFormat
from app.enums.preset_operation import PresetOperation
from app.enums.filter_operator import FilterOperator

class ProcessingRequest(BaseModel):
    format: FileFormat
    preset: PresetOperation
    filter_field: Optional[str] = None
    filter_value: Optional[str] = None
    filter_operator: Optional[FilterOperator] = None

class JobResponse(BaseModel):
    job_id: UUID
    status: str
    status_url: str
    message: str

class JobStats(BaseModel):
    total_records: int
    duplicates_removed: int
    records_filtered: int
    records_kept: int
    reduction_percentage: float

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    format: FileFormat
    preset: str
    original_file_name: str
    file_size_mb: float
    stats: Optional[JobStats] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
