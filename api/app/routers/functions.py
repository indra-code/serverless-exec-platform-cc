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
import redis
import json
import glob
from kubernetes import client
from kubernetes.config import load_kube_config
import subprocess

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/functions",
    tags=["functions"]
)

@router.post("/", response_model=FunctionInDB, status_code=status.HTTP_201_CREATED)
def create_function(function: FunctionCreate, db: Session = Depends(get_db)):
    try:
        # Check and add worker_pod column if needed
        try:
            from ..database.database import engine
            logger.info("Checking if worker_pod column exists in create_function")
            with engine.connect() as conn:
                # Check if column exists
                result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='functions' AND column_name='worker_pod'")
                column_exists = result.fetchone() is not None
                
                if not column_exists:
                    logger.info("Adding worker_pod column to functions table")
                    conn.execute("ALTER TABLE functions ADD COLUMN worker_pod VARCHAR")
                    logger.info("Successfully added worker_pod column")
                else:
                    logger.debug("worker_pod column already exists")
        except Exception as migration_error:
            logger.warning(f"Migration error in create_function (non-critical): {str(migration_error)}")
        
        logger.debug(f"Attempting to create function: {function.dict()}")
        
        # Create function data without worker_pod if there's an issue
        try:
            db_function = Function(**function.dict())
            db.add(db_function)
            db.commit()
            db.refresh(db_function)
            logger.info(f"Successfully created function with ID: {db_function.id}")
            return db_function
        except Exception as db_error:
            db.rollback()
            if "worker_pod" in str(db_error):
                logger.warning("Error with worker_pod column, trying without it")
                
                # Try again without the worker_pod field
                function_data = {k: v for k, v in function.dict().items() if k != 'worker_pod'}
                db_function = Function(**function_data)
                db.add(db_function)
                db.commit()
                db.refresh(db_function)
                logger.info(f"Successfully created function with ID: {db_function.id} (without worker_pod)")
                return db_function
            else:
                raise
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
        # Directly run the migration to add worker_pod column if needed
        try:
            from ..database.database import engine
            logger.info("Checking if worker_pod column exists and adding it if needed")
            with engine.connect() as conn:
                # Check if column exists
                result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='functions' AND column_name='worker_pod'")
                column_exists = result.fetchone() is not None
                
                if not column_exists:
                    logger.info("Adding worker_pod column to functions table")
                    conn.execute("ALTER TABLE functions ADD COLUMN worker_pod VARCHAR")
                    logger.info("Successfully added worker_pod column")
                else:
                    logger.info("worker_pod column already exists")
        except Exception as migration_error:
            logger.warning(f"Migration error (non-critical): {str(migration_error)}")
            
        logger.debug(f"Fetching functions with skip={skip}, limit={limit}")
        
        try:
            functions = db.query(Function).offset(skip).limit(limit).all()
            logger.info(f"Successfully fetched {len(functions)} functions")
            return functions
        except Exception as db_error:
            # If there's an error with the query, try a simpler query that doesn't include the worker_pod column
            logger.warning(f"Database error: {str(db_error)}")
            if "worker_pod" in str(db_error):
                logger.warning("Database error related to worker_pod column, trying simpler query")
                # Use a specific column list that excludes worker_pod
                functions = db.query(
                    Function.id, 
                    Function.name, 
                    Function.description,
                    Function.code_path,
                    Function.runtime,
                    Function.timeout,
                    Function.memory,
                    Function.is_active,
                    Function.created_at,
                    Function.updated_at
                ).offset(skip).limit(limit).all()
                
                # If we still get an empty list, return an empty list rather than raising an error
                if not functions:
                    logger.info("No functions found, returning empty list")
                    return []
                    
                logger.info(f"Successfully fetched {len(functions)} functions with simpler query")
                return functions
            else:
                # If we get any other error, return an empty list if there are no functions
                try:
                    count = db.query(Function.id).count()
                    if count == 0:
                        logger.info("No functions found, returning empty list")
                        return []
                    else:
                        raise db_error
                except:
                    raise db_error
                
    except Exception as e:
        logger.error(f"Error fetching functions: {str(e)}")
        # Return an empty list instead of raising an error
        return []

@router.get("/{function_id}", response_model=FunctionInDB)
def get_function(function_id: int, db: Session = Depends(get_db)):
    try:
        # Check and add worker_pod column if needed
        try:
            from ..database.database import engine
            logger.info("Checking if worker_pod column exists in get_function")
            with engine.connect() as conn:
                # Check if column exists
                result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='functions' AND column_name='worker_pod'")
                column_exists = result.fetchone() is not None
                
                if not column_exists:
                    logger.info("Adding worker_pod column to functions table")
                    conn.execute("ALTER TABLE functions ADD COLUMN worker_pod VARCHAR")
                    logger.info("Successfully added worker_pod column")
                else:
                    logger.debug("worker_pod column already exists")
        except Exception as migration_error:
            logger.warning(f"Migration error in get_function (non-critical): {str(migration_error)}")
            
        logger.debug(f"Fetching function with ID: {function_id}")
        
        try:
            function = db.query(Function).filter(Function.id == function_id).first()
        except Exception as db_error:
            if "worker_pod" in str(db_error):
                logger.warning("Error with worker_pod column, trying without it")
                # Use specific columns excluding worker_pod
                function = db.query(
                    Function.id, 
                    Function.name, 
                    Function.description,
                    Function.code_path,
                    Function.runtime,
                    Function.timeout,
                    Function.memory,
                    Function.is_active,
                    Function.created_at,
                    Function.updated_at
                ).filter(Function.id == function_id).first()
            else:
                raise
                
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
        # Check and add worker_pod column if needed
        try:
            from ..database.database import engine
            logger.info("Checking if worker_pod column exists in update_function")
            with engine.connect() as conn:
                # Check if column exists
                result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='functions' AND column_name='worker_pod'")
                column_exists = result.fetchone() is not None
                
                if not column_exists:
                    logger.info("Adding worker_pod column to functions table")
                    conn.execute("ALTER TABLE functions ADD COLUMN worker_pod VARCHAR")
                    logger.info("Successfully added worker_pod column")
                else:
                    logger.debug("worker_pod column already exists")
        except Exception as migration_error:
            logger.warning(f"Migration error in update_function (non-critical): {str(migration_error)}")
            
        logger.debug(f"Updating function with ID: {function_id}")
        db_function = db.query(Function).filter(Function.id == function_id).first()
        if db_function is None:
            logger.warning(f"Function not found with ID: {function_id}")
            raise HTTPException(status_code=404, detail="Function not found")
        
        try:
            update_data = function.dict(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_function, key, value)
            
            db.commit()
            db.refresh(db_function)
            logger.info(f"Successfully updated function with ID: {function_id}")
            return db_function
        except Exception as db_error:
            db.rollback()
            if "worker_pod" in str(db_error):
                logger.warning("Error with worker_pod column, trying without it")
                
                # Try again without the worker_pod field
                update_data = {k: v for k, v in function.dict(exclude_unset=True).items() if k != 'worker_pod'}
                for key, value in update_data.items():
                    setattr(db_function, key, value)
                
                db.commit()
                db.refresh(db_function)
                logger.info(f"Successfully updated function with ID: {function_id} (without worker_pod)")
                return db_function
            else:
                raise
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
    runtime: Optional[str] = "cli",
    db: Session = Depends(get_db),
    fastapi_request: Request = None
):
    try:
        function = db.query(Function).filter(Function.id == function_id).first()
        if function is None:
            raise HTTPException(status_code=404, detail="Function not found")
        
        logger.info(f"Starting execution of function {function_id} with runtime {runtime}")
        
        # Initialize metrics collector
        metrics_collector = MetricsCollector(db)
        start_time = time.time()
        
        try:
            # Check if function already has a worker pod
            pod_name = function.worker_pod
            if pod_name:
                # Verify if the worker pod exists
                cmd = ["kubectl", "get", "pod", pod_name]
                pod_check = subprocess.run(cmd, capture_output=True, text=True)
                
                if pod_check.returncode != 0:
                    logger.info(f"Worker pod {pod_name} no longer exists. Creating a new one.")
                    pod_name = None
                else:
                    logger.info(f"Reusing existing worker pod: {pod_name}")
            
            # If no worker pod exists or the previous one is gone, create a new function execution
            if not pod_name:
                # Select execution engine based on runtime
                if runtime == "cli" and fastapi_request.state.cli_engine:
                    logger.info(f"Using CLI engine for function {function_id}")
                    engine = fastapi_request.state.cli_engine
                elif runtime == "docker":
                    logger.info(f"Using Docker engine for function {function_id}")
                    engine = fastapi_request.state.docker_engine
                elif runtime == "gvisor" and fastapi_request.state.gvisor_engine:
                    logger.info(f"Using gVisor engine for function {function_id}")
                    engine = fastapi_request.state.gvisor_engine
                else:
                    available_runtimes = ["docker"]
                    if hasattr(fastapi_request.state, 'cli_engine') and fastapi_request.state.cli_engine:
                        available_runtimes.append("cli")
                    if hasattr(fastapi_request.state, 'gvisor_engine') and fastapi_request.state.gvisor_engine:
                        available_runtimes.append("gvisor")
                        
                    raise HTTPException(
                        status_code=400,
                        detail=f"Runtime '{runtime}' not available. Available runtimes: {', '.join(available_runtimes)}"
                    )
                
                # Execute the function
                logger.info(f"Submitting function {function_id} to engine")
                result = await engine.execute_function(function, request)
                logger.info(f"Engine execution result: {result}")
                
                # Get job ID from result
                job_id = result.get("job_id")
                if not job_id:
                    raise HTTPException(status_code=500, detail="No job ID returned from execution")
                
                logger.info(f"Got job ID: {job_id}")
                
                # List all pods
                cmd = ["kubectl", "get", "pods"]
                pods_result = subprocess.run(cmd, capture_output=True, text=True)
                logger.info(f"Current pods:\n{pods_result.stdout}")
                
                # Wait for pod to be created and get its name
                max_retries = 60  # Wait up to 60 seconds for pod creation
                for attempt in range(max_retries):
                    logger.info(f"Waiting for pod to be created (attempt {attempt + 1}/{max_retries})")
                    
                    # First try with the job-name label - standard Kubernetes label
                    cmd = ["kubectl", "get", "pods", "--selector=batch.kubernetes.io/job-name=" + job_id, "-o", "jsonpath='{.items[*].metadata.name}'"]
                    pod_name_result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if pod_name_result.returncode == 0 and pod_name_result.stdout.strip("'"):
                        pod_name = pod_name_result.stdout.strip("'")
                        logger.info(f"Found pod name from batch.kubernetes.io/job-name label: {pod_name}")
                        break
                    
                    # Try alternative selector with job-name label
                    cmd = ["kubectl", "get", "pods", "--selector=job-name=" + job_id, "-o", "jsonpath='{.items[*].metadata.name}'"]
                    pod_name_result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if pod_name_result.returncode == 0 and pod_name_result.stdout.strip("'"):
                        pod_name = pod_name_result.stdout.strip("'")
                        logger.info(f"Found pod name from job-name label: {pod_name}")
                        break
                    
                    # Try direct name listing (look for pods that start with the job ID)
                    cmd = ["kubectl", "get", "pods", "-o", "name"]
                    pods_list_result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if pods_list_result.returncode == 0:
                        pod_lines = pods_list_result.stdout.strip().split('\n')
                        for pod_line in pod_lines:
                            # Extract just the pod name without the "pod/" prefix
                            if pod_line.startswith("pod/"):
                                potential_pod = pod_line[4:] # Skip "pod/"
                            else:
                                potential_pod = pod_line
                                
                            # Check if this pod starts with our job ID
                            if potential_pod.startswith(job_id):
                                pod_name = potential_pod
                                logger.info(f"Found pod name by prefix matching: {pod_name}")
                                break
                        
                        if pod_name:
                            break
                    
                    # Check for any recent pods (as a last resort)
                    if attempt > 10 and attempt % 5 == 0:
                        cmd = ["kubectl", "get", "pods", "--sort-by=.metadata.creationTimestamp", "-o", "jsonpath='{.items[-1:].metadata.name}'"]
                        latest_pod_result = subprocess.run(cmd, capture_output=True, text=True)
                        
                        if latest_pod_result.returncode == 0 and latest_pod_result.stdout.strip("'"):
                            latest_pod = latest_pod_result.stdout.strip("'")
                            # Only use this if it was created recently (last minute)
                            cmd = ["kubectl", "get", "pod", latest_pod, "-o", "jsonpath='{.metadata.creationTimestamp}'"]
                            timestamp_result = subprocess.run(cmd, capture_output=True, text=True)
                            
                            if timestamp_result.returncode == 0:
                                pod_time = timestamp_result.stdout.strip("'")
                                # Just use the most recent pod as a fallback
                                pod_name = latest_pod
                                logger.info(f"Using most recent pod as fallback: {pod_name} (created at {pod_time})")
                                break
                    
                    logger.info("Pod not found yet, waiting...")
                    time.sleep(1)
                
                if not pod_name:
                    logger.error("Failed to get pod name after maximum retries")
                    # List all pods to diagnose
                    cmd = ["kubectl", "get", "pods"]
                    all_pods = subprocess.run(cmd, capture_output=True, text=True)
                    logger.error(f"All pods: {all_pods.stdout}")
                    raise HTTPException(status_code=500, detail="Failed to get pod name after waiting")
                
                # Store the pod name in the function record
                function.worker_pod = pod_name
                db.commit()
                logger.info(f"Stored worker pod {pod_name} for function {function_id}")
            
            # At this point we have a valid pod_name (either existing or newly created)
            # Wait for job completion and get logs
            max_retries = 60  # Wait up to 60 seconds
            for attempt in range(max_retries):
                logger.info(f"Checking job status (attempt {attempt + 1}/{max_retries})")
                
                # Check job status
                cmd = ["kubectl", "get", "pod", pod_name, "-o", "json"]
                logger.info(f"Running command: {' '.join(cmd)}")
                status_result = subprocess.run(cmd, capture_output=True, text=True)
                
                if status_result.returncode == 0:
                    pod = json.loads(status_result.stdout)
                    status = pod["status"]["phase"]
                    logger.info(f"Pod status: {status}")
                    
                    # Log more pod details
                    logger.info(f"Pod details: {json.dumps(pod['status'], indent=2)}")
                    
                    if status == "Succeeded" or status == "Running":
                        logger.info("Job is running or succeeded, getting logs")
                        # Get logs
                        cmd = ["kubectl", "logs", pod_name]
                        logger.info(f"Running command: {' '.join(cmd)}")
                        logs_result = subprocess.run(cmd, capture_output=True, text=True)
                        
                        if logs_result.returncode == 0:
                            logs = logs_result.stdout
                            logger.info(f"Got logs (length: {len(logs)})")
                            
                            # If running and no logs yet, continue waiting
                            if status == "Running" and not logs:
                                logger.info("Pod is running but no logs yet, continuing to wait")
                                time.sleep(1)
                                continue
                            
                            end_time = time.time()
                            
                            # Collect metrics
                            await metrics_collector.collect_execution_metrics(
                                function=function,
                                request=request,
                                start_time=start_time,
                                end_time=end_time,
                                success=True,
                                error=None,
                                resource_usage={
                                    "memory_used": function.memory,
                                    "execution_time": end_time - start_time
                                }
                            )
                            
                            return {
                                "status": "success",
                                "pod_name": pod_name,
                                "logs": logs
                            }
                        else:
                            logger.error(f"Failed to get logs: {logs_result.stderr}")
                            raise HTTPException(status_code=500, detail=f"Failed to get job logs: {logs_result.stderr}")
                    elif status == "Failed":
                        logger.error("Job failed, getting failure logs")
                        # Get logs for failed job
                        cmd = ["kubectl", "logs", pod_name]
                        logs_result = subprocess.run(cmd, capture_output=True, text=True)
                        logs = logs_result.stdout if logs_result.returncode == 0 else "Failed to get logs"
                        logger.error(f"Failure logs: {logs}")
                        
                        # Since the pod failed, clear it from the function record
                        function.worker_pod = None
                        db.commit()
                        logger.info(f"Cleared failed worker pod for function {function_id}")
                        
                        # Get pod events
                        cmd = ["kubectl", "describe", "pod", pod_name]
                        events_result = subprocess.run(cmd, capture_output=True, text=True)
                        if events_result.returncode == 0:
                            logger.error(f"Pod events:\n{events_result.stdout}")
                        
                        end_time = time.time()
                        await metrics_collector.collect_execution_metrics(
                            function=function,
                            request=request,
                            start_time=start_time,
                            end_time=end_time,
                            success=False,
                            error="Job failed",
                            resource_usage={
                                "memory_used": function.memory,
                                "execution_time": end_time - start_time
                            }
                        )
                        
                        raise HTTPException(
                            status_code=500,
                            detail=f"Job failed: {logs}"
                        )
                else:
                    logger.error(f"Error getting pod status: {status_result.stderr}")
                    
                    # If we can't get the pod status, clear it from the function record
                    function.worker_pod = None
                    db.commit()
                    logger.info(f"Cleared worker pod for function {function_id} due to status check failure")
                
                time.sleep(1)
            
            # If we get here, the job timed out
            logger.error(f"Pod {pod_name} timed out after {max_retries} seconds")
            
            # Get final pod state
            cmd = ["kubectl", "describe", "pod", pod_name]
            final_state = subprocess.run(cmd, capture_output=True, text=True)
            logger.error(f"Final pod state:\n{final_state.stdout}")
            
            # Clear the worker pod from the function record on timeout
            function.worker_pod = None
            db.commit()
            logger.info(f"Cleared worker pod for function {function_id} due to timeout")
            
            end_time = time.time()
            await metrics_collector.collect_execution_metrics(
                function=function,
                request=request,
                start_time=start_time,
                end_time=end_time,
                success=False,
                error="Job timed out",
                resource_usage={
                    "memory_used": function.memory,
                    "execution_time": end_time - start_time
                }
            )
            
            raise HTTPException(status_code=500, detail="Job execution timed out")
            
        except Exception as e:
            logger.error(f"Error during execution: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Clear the worker pod on exception
            if function.worker_pod:
                function.worker_pod = None
                db.commit()
                logger.info(f"Cleared worker pod for function {function_id} due to exception")
                
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
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Function execution failed: {str(e)}"
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

@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get the status of a job"""
    try:
        # Get pod status using kubectl
        cmd = ["kubectl", "get", "pod", job_id, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return {"status": "not_found"}
            
        pod = json.loads(result.stdout)
        status = pod["status"]["phase"]
        
        if status == "Succeeded":
            return {"status": "completed"}
        elif status == "Failed":
            return {"status": "failed", "error": "Job failed in Kubernetes"}
        else:
            return {"status": "running"}
            
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting job status: {str(e)}"
        )

@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    """Get the logs for a completed job"""
    try:
        # Get pod logs using kubectl
        cmd = ["kubectl", "logs", job_id]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return {"logs": f"Error getting logs: {result.stderr}"}
            
        return {"logs": result.stdout}
        
    except Exception as e:
        logger.error(f"Error getting job logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting job logs: {str(e)}"
        ) 