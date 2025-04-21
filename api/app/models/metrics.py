from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database.database import Base

class ExecutionMetric(Base):
    __tablename__ = "execution_metrics"

    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, ForeignKey("functions.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    execution_time = Column(Float, nullable=False)  # in seconds
    memory_used = Column(Float, nullable=True)  # in MB
    success = Column(Boolean, default=True)
    error = Column(String, nullable=True)
    runtime = Column(String, nullable=False)
    
    # Optional metadata as JSON
    resource_usage = Column(JSON, nullable=True)  # CPU, memory, etc.
    request_data = Column(JSON, nullable=True)  # Store request parameters
    
    # Relationship to the function
    function = relationship("Function", back_populates="execution_metrics")

# Update Function model in function.py to include this relationship:
# execution_metrics = relationship("ExecutionMetric", back_populates="function", cascade="all, delete-orphan") 