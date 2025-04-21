from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database.database import Base

class Function(Base):
    __tablename__ = "functions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    code_path = Column(String, nullable=False)
    runtime = Column(String, default="python")
    timeout = Column(Integer, default=30)  # in seconds
    memory = Column(Integer, default=128)  # in MB
    is_active = Column(Boolean, default=True)
    worker_pod = Column(String, nullable=True)  # Store the worker pod name
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship to execution metrics
    execution_metrics = relationship("ExecutionMetric", back_populates="function", cascade="all, delete-orphan") 