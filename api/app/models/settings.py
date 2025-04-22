from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from sqlalchemy.sql import func

from ..db.base_class import Base

class PlatformSettings(Base):
    """
    Platform-wide settings for the serverless execution service.
    This singleton table stores configuration that applies to all functions.
    """
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Security Settings
    enforce_gvisor = Column(Boolean, default=True)
    allow_docker_runtime = Column(Boolean, default=False)
    allow_unsecured_networks = Column(Boolean, default=False)
    allow_custom_containers = Column(Boolean, default=False)
    
    # Resource Limitations
    max_concurrent_functions = Column(Integer, default=10)
    default_memory_limit = Column(Integer, default=256)  # MB
    default_cpu_limit = Column(Float, default=0.5)  # CPU cores
    default_timeout = Column(Integer, default=300)  # seconds
    
    # Audit and Compliance
    enable_detailed_logging = Column(Boolean, default=True)
    retain_execution_logs_days = Column(Integer, default=30)
    
    # There should only be one row in this table
    @classmethod
    def get_settings(cls, db):
        """
        Get the singleton settings object. Creates default settings if none exist.
        """
        settings = db.query(cls).first()
        if not settings:
            settings = cls(
                enforce_gvisor=True,
                allow_docker_runtime=False,
                allow_unsecured_networks=False,
                allow_custom_containers=False,
                max_concurrent_functions=10,
                default_memory_limit=256,
                default_cpu_limit=0.5,
                default_timeout=300,
                enable_detailed_logging=True,
                retain_execution_logs_days=30
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings 