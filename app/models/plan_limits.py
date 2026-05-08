from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime
from sqlalchemy.sql import func

from app.database import Base


class PlanLimits(Base):
    __tablename__ = "plan_limits"
    
    # Plan (PRIMARY KEY)
    plan = Column(String(20), primary_key=True)
    
    # Límites de archivos
    files_per_month = Column(Integer, nullable=False)
    # -1 significa ilimitado
    
    max_file_size_mb = Column(Integer, nullable=False)
    max_records_per_file = Column(Integer, nullable=False)
    
    # Features
    num_presets = Column(Integer, nullable=False)
    custom_filters_allowed = Column(Boolean, nullable=False, default=False)
    
    # API
    api_keys_count = Column(Integer, nullable=False, default=0)
    requests_per_hour = Column(Integer, nullable=False)
    
    # SLA (opcional, puede ser NULL para FREE/STARTER)
    sla_uptime = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<PlanLimits {self.plan}>"
    
    @property
    def is_unlimited_files(self):
        """Verifica si tiene archivos ilimitados"""
        return self.files_per_month == -1
    
    def can_process_file(self, file_size_mb: float, current_month_files: int) -> tuple[bool, str]:
        """
        Verifica si puede procesar un archivo
        
        Returns:
            (can_process, error_message)
        """
        
        # Verificar límite mensual
        if not self.is_unlimited_files:
            if current_month_files >= self.files_per_month:
                return False, f"Monthly limit reached ({self.files_per_month} files)"
        
        # Verificar tamaño
        if file_size_mb > self.max_file_size_mb:
            return False, f"File too large ({file_size_mb:.1f}MB > {self.max_file_size_mb}MB)"
        
        return True, ""


# Seed data para inicializar la tabla
PLAN_LIMITS_SEED = [
    {
        "plan": "FREE",
        "files_per_month": 10,
        "max_file_size_mb": 10,
        "max_records_per_file": 200000,
        "num_presets": 2,
        "custom_filters_allowed": False,
        "api_keys_count": 0,
        "requests_per_hour": 10,
        "sla_uptime": None
    },
    {
        "plan": "STARTER",
        "files_per_month": 100,
        "max_file_size_mb": 100,
        "max_records_per_file": 2000000,
        "num_presets": 5,
        "custom_filters_allowed": True,
        "api_keys_count": 1,
        "requests_per_hour": 100,
        "sla_uptime": None
    },
    {
        "plan": "PRO",
        "files_per_month": 500,
        "max_file_size_mb": 500,
        "max_records_per_file": 10000000,
        "num_presets": 5,
        "custom_filters_allowed": True,
        "api_keys_count": 3,
        "requests_per_hour": 500,
        "sla_uptime": 99.50
    },
    {
        "plan": "BUSINESS",
        "files_per_month": -1,  # Ilimitado
        "max_file_size_mb": 2000,
        "max_records_per_file": 40000000,
        "num_presets": 5,
        "custom_filters_allowed": True,
        "api_keys_count": 10,
        "requests_per_hour": 2000,
        "sla_uptime": 99.90
    }
]
