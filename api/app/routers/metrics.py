from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from ..database.database import get_db
from ..metrics.collector import MetricsCollector
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"]
)

@router.get("/")
async def get_all_metrics(
    days: int = Query(30, description="Number of days to include in metrics"),
    db: Session = Depends(get_db)
):
    """
    Get system-wide metrics for all functions
    """
    try:
        collector = MetricsCollector(db)
        return collector.get_metrics(days=days)
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return {
            "error": str(e),
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

@router.get("/functions/{function_id}")
async def get_function_metrics(
    function_id: int, 
    days: int = Query(30, description="Number of days to include in metrics"),
    db: Session = Depends(get_db)
):
    """
    Get detailed metrics for a specific function
    """
    try:
        collector = MetricsCollector(db)
        return collector.get_metrics(function_id=function_id, days=days)
    except Exception as e:
        logger.error(f"Error getting function metrics: {e}")
        return {
            "error": str(e),
            "function_id": function_id,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_execution_time": 0,
            "avg_memory_used": 0,
            "recent_executions": [],
            "time_series": []
        } 