from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import secrets

from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    # Identificación
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    
    # Plan
    plan = Column(
        SQLEnum('FREE', 'STARTER', 'PRO', 'BUSINESS', name='user_plan'),
        nullable=False,
        default='FREE',
        index=True
    )
    
    # Tracking de uso
    files_processed_this_month = Column(Integer, default=0, nullable=False)
    files_processed_total = Column(Integer, default=0, nullable=False)
    last_reset_date = Column(DateTime(timezone=True), server_default=func.now())
    
    # Stripe (para futuro)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    
    # Estado
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<User {self.email} ({self.plan})>"
    
    @staticmethod
    def generate_api_key():
        """Genera un API key seguro"""
        return secrets.token_urlsafe(32)
    
    def increment_usage(self):
        """Incrementa contador de archivos procesados"""
        self.files_processed_this_month += 1
        self.files_processed_total += 1
    
    def reset_monthly_usage(self):
        """Reset contador mensual (llamado por cron job)"""
        self.files_processed_this_month = 0
        self.last_reset_date = datetime.now()
