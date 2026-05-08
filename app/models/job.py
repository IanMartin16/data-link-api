from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, ForeignKey
from datetime import datetime
import uuid

from app.database import Base
from app.enums.job_status import JobStatus
from app.enums.file_format import FileFormat
from app.enums.preset_operation import PresetOperation
from app.enums.filter_operator import FilterOperator

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Status and format
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    format = Column(SQLEnum(FileFormat), nullable=False)
    preset = Column(SQLEnum(PresetOperation), nullable=False)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True)
    
    # Files
    input_file_url = Column(String(500), nullable=False)
    original_file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    output_file_url = Column(String(500))
    
    # Filters
    filter_field = Column(String(100))
    filter_value = Column(String(500))
    filter_operator = Column(SQLEnum(FilterOperator))
    
    # Statistics
    total_records = Column(Integer)
    duplicates_removed = Column(Integer)
    records_filtered = Column(Integer)
    records_kept = Column(Integer)
    
    # Error handling
    error_message = Column(String(2000))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    def mark_as_processing(self):
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.utcnow()
    
    def mark_as_completed(self, output_url: str, total: int, duplicates: int, filtered: int):
        self.status = JobStatus.COMPLETED
        self.output_file_url = output_url
        self.total_records = total
        self.duplicates_removed = duplicates
        self.records_filtered = filtered
        self.records_kept = total - duplicates - filtered
        self.completed_at = datetime.utcnow()
    
    def mark_as_failed(self, error: str):
        self.status = JobStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
    
    @property
    def file_size_mb(self):
        return round(self.file_size_bytes / (1024 * 1024), 2)
