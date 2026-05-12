from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import secrets

from app.database import Base


class User(Base):
    __tablename__ = "users"

    # Identity
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    api_key = Column(String(64), unique=True, nullable=False, index=True)

    # Plan
    plan = Column(
        SQLEnum('FREE', 'STARTER', name='user_plan'),
        nullable=False,
        default='FREE',
        index=True
    )

    # Usage tracking
    files_processed_this_month = Column(Integer, default=0, nullable=False)
    files_processed_total = Column(Integer, default=0, nullable=False)
    last_reset_date = Column(DateTime(timezone=True), server_default=func.now())

    # Billing placeholders (future use)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.email} ({self.plan})>"

    @staticmethod
    def generate_api_key():
        """Generate a secure API key."""
        return secrets.token_urlsafe(32)

    def increment_usage(self):
        """Increment processed file counters."""
        self.files_processed_this_month += 1
        self.files_processed_total += 1

    def reset_monthly_usage(self):
        """Reset monthly usage counters."""
        self.files_processed_this_month = 0
        self.last_reset_date = datetime.now()