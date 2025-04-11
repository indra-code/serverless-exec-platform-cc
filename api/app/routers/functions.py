from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
import traceback
from ..database.database import get_db
from ..models.function import Function
from ..schemas.function import FunctionCreate, FunctionUpdate, FunctionInDB
from ..k8s.job_queue import add_to_queue

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
def execute_function(function_id: int, db: Session = Depends(get_db)):
    function = db.query(Function).filter(Function.id == function_id).first()
    if function is None:
        raise HTTPException(status_code=404, detail="Function not found")
    else:
        add_to_queue(function_id, function.code_path)
        return {"message": "Function execution requested"}
    
    

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