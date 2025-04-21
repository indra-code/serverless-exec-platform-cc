import time
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..database.database import get_db
from ..models.function import Function
from ..models.metrics import ExecutionMetric
from ..schemas.function import FunctionExecutionRequest

logger = logging.getLogger(__name__)

class MetricsCollector:
    def __init__(self, db: Session):
        self.db = db
        
        # Run the table creation migration if needed
        try:
            from ..database.create_metrics_table import run_migration
            run_migration()
        except Exception as e:
            logger.warning(f"Failed to run metrics table migration: {e}")
    
    async def collect_execution_metrics(self, function: Function, request: FunctionExecutionRequest, 
                                      start_time: float, end_time: float, 
                                      success: bool, error: Optional[str] = None,
                                      resource_usage: Optional[Dict[str, float]] = None):
        """Store execution metrics in the database"""
        try:
            execution_time = end_time - start_time
            
            # Create new metric record
            metric = ExecutionMetric(
                function_id=function.id,
                execution_time=execution_time,
                memory_used=resource_usage.get("memory_used") if resource_usage else None,
                success=success,
                error=str(error) if error else None,
                runtime=function.runtime,
                resource_usage=resource_usage,
                request_data=self._safe_convert_request(request) if request else None
            )
            
            self.db.add(metric)
            self.db.commit()
            logger.info(f"Stored execution metrics for function {function.id}")
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            self.db.rollback()
    
    def _safe_convert_request(self, request):
        """Safely convert request to a dictionary"""
        try:
            if hasattr(request, 'dict') and callable(request.dict):
                return request.dict()
            elif hasattr(request, '__dict__'):
                return request.__dict__
            elif isinstance(request, dict):
                return request
            else:
                return {"data": str(request)}
        except Exception as e:
            logger.warning(f"Could not convert request to dictionary: {e}")
            return {"error": "Could not convert request data"}
    
    def get_metrics(self, function_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
        """Get metrics from the database"""
        try:
            metrics = {}
            
            # Calculate time range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Base query to filter by date range
            base_query = self.db.query(ExecutionMetric).filter(
                ExecutionMetric.timestamp >= start_date,
                ExecutionMetric.timestamp <= end_date
            )
            
            # Filter by function_id if provided
            if function_id:
                base_query = base_query.filter(ExecutionMetric.function_id == function_id)
            
            # Get total executions
            metrics["total_executions"] = base_query.count()
            
            # Get successful executions
            metrics["successful_executions"] = base_query.filter(ExecutionMetric.success == True).count()
            
            # Get failed executions
            metrics["failed_executions"] = base_query.filter(ExecutionMetric.success == False).count()
            
            # Get active functions count
            metrics["active_functions"] = self.db.query(func.count(Function.id)).filter(Function.is_active == True).scalar() or 0
            
            # Get average execution time
            avg_time_result = base_query.with_entities(func.avg(ExecutionMetric.execution_time)).scalar()
            metrics["avg_execution_time"] = float(avg_time_result) if avg_time_result else 0
            
            # Get average memory usage
            avg_memory_result = base_query.with_entities(func.avg(ExecutionMetric.memory_used)).scalar()
            metrics["avg_memory_used"] = float(avg_memory_result) if avg_memory_result else 0
            
            # Function performance (execution time by function)
            if not function_id:
                function_performance = []
                
                # Get top 10 functions by execution count
                top_functions = self.db.query(
                    ExecutionMetric.function_id,
                    func.count(ExecutionMetric.id).label('count')
                ).group_by(
                    ExecutionMetric.function_id
                ).order_by(
                    desc('count')
                ).limit(10).all()
                
                for func_id, _ in top_functions:
                    # Get function details
                    function = self.db.query(Function).filter(Function.id == func_id).first()
                    if function:
                        # Get average execution time
                        avg_exec_time = self.db.query(
                            func.avg(ExecutionMetric.execution_time)
                        ).filter(
                            ExecutionMetric.function_id == func_id
                        ).scalar() or 0
                        
                        # Get execution count
                        exec_count = self.db.query(
                            func.count(ExecutionMetric.id)
                        ).filter(
                            ExecutionMetric.function_id == func_id
                        ).scalar() or 0
                        
                        function_performance.append({
                            "function_id": func_id,
                            "function_name": function.name,
                            "execution_time": float(avg_exec_time),
                            "execution_count": exec_count
                        })
                
                metrics["function_performance"] = function_performance
            
            # Recent executions
            recent_executions = []
            recent_metrics = base_query.order_by(ExecutionMetric.timestamp.desc()).limit(10).all()
            
            for metric in recent_metrics:
                # Get function name
                function = self.db.query(Function).filter(Function.id == metric.function_id).first()
                
                recent_executions.append({
                    "function_id": metric.function_id,
                    "function_name": function.name if function else "Unknown",
                    "timestamp": metric.timestamp.isoformat(),
                    "execution_time": metric.execution_time,
                    "success": metric.success,
                    "runtime": metric.runtime
                })
            
            metrics["recent_executions"] = recent_executions
            
            # Time series data for the last 30 days
            time_series = []
            
            # Group by day and count executions
            daily_counts = self.db.query(
                func.date_trunc('day', ExecutionMetric.timestamp).label('day'),
                func.count(ExecutionMetric.id).label('count')
            ).filter(
                ExecutionMetric.timestamp >= start_date,
                ExecutionMetric.timestamp <= end_date
            )
            
            if function_id:
                daily_counts = daily_counts.filter(ExecutionMetric.function_id == function_id)
            
            daily_counts = daily_counts.group_by('day').order_by('day').all()
            
            for day, count in daily_counts:
                time_series.append({
                    "date": day.strftime('%Y-%m-%d'),
                    "executions": count
                })
            
            metrics["time_series"] = time_series
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error retrieving metrics: {e}")
            return {
                "active_functions": 0,
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "avg_execution_time": 0,
                "avg_memory_used": 0,
                "function_performance": [],
                "recent_executions": [],
                "time_series": []
            } 