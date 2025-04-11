from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import traceback
import time
from ..database.database import get_db
from ..models.function import Function
from ..schemas.function import FunctionCreate, FunctionUpdate, FunctionInDB, FunctionExecutionRequest
from ..metrics.collector import MetricsCollector

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/functions",
    tags=["functions"]
)

@router.post("/", response_model=FunctionInDB, status_code=status.HTTP_201_CREATED)
def create_function(function: FunctionCreate, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Attempting to create function: {function.dict()}")
        db_function = Function(**function.dict())
        db.add(db_function)
        db.commit()
        db.refresh(db_function)
        logger.info(f"Successfully created function with ID: {db_function.id}")
        return db_function
    except Exception as e:
        logger.error(f"Error creating function: {str(e)}")
        logger.error(traceback.format_exc())
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating function: {str(e)}"
        )

@router.get("/", response_model=List[FunctionInDB])
def list_functions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Fetching functions with skip={skip}, limit={limit}")
        functions = db.query(Function).offset(skip).limit(limit).all()
        logger.info(f"Successfully fetched {len(functions)} functions")
        return functions
    except Exception as e:
        logger.error(f"Error fetching functions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching functions: {str(e)}"
        )

@router.get("/{function_id}", response_model=FunctionInDB)
def get_function(function_id: int, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Fetching function with ID: {function_id}")
        function = db.query(Function).filter(Function.id == function_id).first()
        if function is None:
            logger.warning(f"Function not found with ID: {function_id}")
            raise HTTPException(status_code=404, detail="Function not found")
        logger.info(f"Successfully fetched function with ID: {function_id}")
        return function
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching function: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching function: {str(e)}"
        )

@router.put("/{function_id}", response_model=FunctionInDB)
def update_function(function_id: int, function: FunctionUpdate, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Updating function with ID: {function_id}")
        db_function = db.query(Function).filter(Function.id == function_id).first()
        if db_function is None:
            logger.warning(f"Function not found with ID: {function_id}")
            raise HTTPException(status_code=404, detail="Function not found")
        
        update_data = function.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_function, key, value)
        
        db.commit()
        db.refresh(db_function)
        logger.info(f"Successfully updated function with ID: {function_id}")
        return db_function
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating function: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating function: {str(e)}"
        )

@router.post("/{function_id}/execute", status_code=status.HTTP_200_OK)
async def execute_function(
    function_id: int,
    request: FunctionExecutionRequest,
    runtime: Optional[str] = "docker",
    db: Session = Depends(get_db),
    fastapi_request: Request = None
):
    try:
        function = db.query(Function).filter(Function.id == function_id).first()
        if function is None:
            raise HTTPException(status_code=404, detail="Function not found")
        
        # Initialize metrics collector
        metrics_collector = MetricsCollector(db)
        start_time = time.time()
        
        try:
            # Select execution engine based on runtime
            if runtime == "docker":
                engine = fastapi_request.state.docker_engine
            elif runtime == "gvisor" and fastapi_request.state.gvisor_engine:
                engine = fastapi_request.state.gvisor_engine
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Runtime '{runtime}' not available. Available runtimes: docker" + 
                          (", gvisor" if fastapi_request.state.gvisor_engine else "")
                )
            
            # Execute the function
            result = await engine.execute_function(function, request)
            end_time = time.time()
            
            # Collect metrics
            await metrics_collector.collect_execution_metrics(
                function=function,
                request=request,
                start_time=start_time,
                end_time=end_time,
                success=result["status"] == "success",
                error=result.get("error"),
                resource_usage={
                    "memory_used": function.memory,
                    "execution_time": end_time - start_time
                }
            )
            
            if result["status"] == "error":
                raise HTTPException(status_code=500, detail=result["error"])
            
            return result
            
        except Exception as e:
            end_time = time.time()
            await metrics_collector.collect_execution_metrics(
                function=function,
                request=request,
                start_time=start_time,
                end_time=end_time,
                success=False,
                error=str(e)
            )
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing function: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing function: {str(e)}"
        )

@router.delete("/{function_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_function(function_id: int, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Deleting function with ID: {function_id}")
        function = db.query(Function).filter(Function.id == function_id).first()
        if function is None:
            logger.warning(f"Function not found with ID: {function_id}")
            raise HTTPException(status_code=404, detail="Function not found")
        
        db.delete(function)
        db.commit()
        logger.info(f"Successfully deleted function with ID: {function_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting function: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting function: {str(e)}"
        ) 