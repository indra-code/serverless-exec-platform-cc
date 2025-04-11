from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database.database import get_db
from ..metrics.collector import MetricsCollector

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"]
)

@router.get("/")
async def get_all_metrics(db: Session = Depends(get_db)):
    collector = MetricsCollector(db)
    return collector.get_metrics()

@router.get("/functions/{function_id}")
async def get_function_metrics(function_id: int, db: Session = Depends(get_db)):
    collector = MetricsCollector(db)
    return collector.get_metrics(function_id) 