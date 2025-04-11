import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ..database.database import get_db
from ..models.function import Function
from ..schemas.function import FunctionExecutionRequest

logger = logging.getLogger(__name__)

class MetricsCollector:
    def __init__(self, db: Session):
        self.db = db
        self.metrics: Dict[str, Any] = {
            "execution_times": [],
            "error_counts": {},
            "resource_usage": [],
            "warmup_times": []
        }
    
    async def collect_execution_metrics(self, function: Function, request: FunctionExecutionRequest, 
                                      start_time: float, end_time: float, 
                                      success: bool, error: Optional[str] = None,
                                      resource_usage: Optional[Dict[str, float]] = None):
        execution_time = end_time - start_time
        
        # Record execution time
        self.metrics["execution_times"].append({
            "function_id": function.id,
            "timestamp": datetime.utcnow(),
            "execution_time": execution_time,
            "success": success
        })
        
        # Record error if any
        if not success:
            if function.id not in self.metrics["error_counts"]:
                self.metrics["error_counts"][function.id] = 0
            self.metrics["error_counts"][function.id] += 1
        
        # Record resource usage
        if resource_usage:
            self.metrics["resource_usage"].append({
                "function_id": function.id,
                "timestamp": datetime.utcnow(),
                **resource_usage
            })
    
    async def collect_warmup_metrics(self, function: Function, start_time: float, end_time: float):
        warmup_time = end_time - start_time
        self.metrics["warmup_times"].append({
            "function_id": function.id,
            "timestamp": datetime.utcnow(),
            "warmup_time": warmup_time
        })
    
    def get_metrics(self, function_id: Optional[int] = None) -> Dict[str, Any]:
        metrics = {}
        
        if function_id:
            # Filter metrics for specific function
            metrics["execution_times"] = [
                m for m in self.metrics["execution_times"]
                if m["function_id"] == function_id
            ]
            metrics["error_counts"] = self.metrics["error_counts"].get(function_id, 0)
            metrics["resource_usage"] = [
                m for m in self.metrics["resource_usage"]
                if m["function_id"] == function_id
            ]
            metrics["warmup_times"] = [
                m for m in self.metrics["warmup_times"]
                if m["function_id"] == function_id
            ]
        else:
            # Return all metrics
            metrics = self.metrics.copy()
        
        # Calculate averages
        if metrics["execution_times"]:
            metrics["avg_execution_time"] = sum(
                m["execution_time"] for m in metrics["execution_times"]
            ) / len(metrics["execution_times"])
        
        if metrics["warmup_times"]:
            metrics["avg_warmup_time"] = sum(
                m["warmup_time"] for m in metrics["warmup_times"]
            ) / len(metrics["warmup_times"])
        
        return metrics 