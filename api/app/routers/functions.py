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
from ..models.settings import PlatformSettings

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
    runtime: Optional[str] = "cli+gvisor",  # Default to CLI+gVisor runtime
    enforce_gvisor: Optional[bool] = None,  # Now optional, can be overridden by platform settings
    wait_for_logs: Optional[bool] = True,   # Whether to wait for logs
    max_wait_seconds: Optional[int] = 60,   # Maximum seconds to wait for job
    db: Session = Depends(get_db),
    fastapi_request: Request = None
):
    try:
        # Get platform-wide security settings
        try:
            platform_settings = PlatformSettings.get_settings(db)
            
            # If enforce_gvisor is not explicitly set in the request, use the platform setting
            if enforce_gvisor is None:
                enforce_gvisor = platform_settings.enforce_gvisor
        except Exception as settings_error:
            logger.warning(f"Could not load platform settings: {settings_error}")
            # Default to enforcing gVisor if settings can't be loaded
            if enforce_gvisor is None:
                enforce_gvisor = True
        
        function = db.query(Function).filter(Function.id == function_id).first()
        if function is None:
            raise HTTPException(status_code=404, detail="Function not found")
        
        logger.info(f"Starting execution of function {function_id} with runtime {runtime}, enforce_gvisor={enforce_gvisor}")
        
        # Initialize metrics collector
        metrics_collector = MetricsCollector(db)
        start_time = time.time()
        
        try:
            # Check Docker runtime permission from platform settings
            # Default to disallowing Docker runtime for security if platform settings don't exist
            docker_allowed = False
            try:
                if hasattr(locals(), 'platform_settings') and platform_settings and hasattr(platform_settings, 'allow_docker_runtime'):
                    docker_allowed = platform_settings.allow_docker_runtime
            except Exception as e:
                logger.warning(f"Could not check Docker runtime permission from platform settings: {e}")
                # Default to disallowing Docker for security
                docker_allowed = False
            
            if runtime == "docker" and not docker_allowed:
                raise HTTPException(
                    status_code=400,
                    detail="SECURITY ERROR: Docker runtime is disabled by platform configuration."
                )
            
            # Determine available engines with gVisor support if strict enforcement is enabled
            available_engines = []
            
            # Check if CLI+gVisor is available and has verified gVisor
            has_cli_gvisor = (
                hasattr(fastapi_request.state, 'cli_engine') and 
                fastapi_request.state.cli_engine is not None and
                getattr(fastapi_request.state.cli_engine, 'verified_gvisor', False)
            )
            
            # Check if dedicated gVisor engine is available 
            has_gvisor_engine = (
                hasattr(fastapi_request.state, 'gvisor_engine') and 
                fastapi_request.state.gvisor_engine is not None
            )
            
            # With strict gVisor enforcement, we need at least one secure runtime
            if enforce_gvisor and not (has_cli_gvisor or has_gvisor_engine):
                raise HTTPException(
                    status_code=400,
                    detail="SECURITY ERROR: gVisor security is required but no gVisor runtime is available. Function execution aborted."
                )
            
            # Select execution engine based on runtime
            if runtime in ["cli", "cli+gvisor"] and fastapi_request.state.cli_engine:
                # When enforcing gVisor, verify the CLI engine has gVisor support
                if enforce_gvisor and not has_cli_gvisor:
                    raise HTTPException(
                        status_code=400,
                        detail="SECURITY ERROR: CLI engine does not have verified gVisor support but gVisor is required. Function execution aborted."
                    )
                logger.info(f"Using CLI+gVisor engine for function {function_id}")
                engine = fastapi_request.state.cli_engine
            elif runtime == "docker":
                # Docker doesn't support gVisor isolation directly
                if enforce_gvisor:
                    raise HTTPException(
                        status_code=400,
                        detail="SECURITY ERROR: Docker runtime cannot provide gVisor isolation but gVisor is required. Function execution aborted."
                    )
                logger.info(f"Using Docker engine for function {function_id}")
                engine = fastapi_request.state.docker_engine
            elif runtime == "gvisor" and fastapi_request.state.gvisor_engine:
                logger.info(f"Using gVisor engine for function {function_id}")
                engine = fastapi_request.state.gvisor_engine
            else:
                # Build list of available secure runtimes
                secure_runtimes = []
                if has_cli_gvisor:
                    secure_runtimes.append("cli+gvisor") 
                if has_gvisor_engine:
                    secure_runtimes.append("gvisor")
                    
                # Add non-secure runtimes if not enforcing gVisor
                if not enforce_gvisor:
                    if hasattr(fastapi_request.state, 'docker_engine'):
                        secure_runtimes.append("docker")
                    if hasattr(fastapi_request.state, 'cli_engine') and not has_cli_gvisor:
                        secure_runtimes.append("cli")
                
                if not secure_runtimes:
                    runtime_msg = "No secure runtimes available" if enforce_gvisor else "No runtimes available"
                    raise HTTPException(
                        status_code=400,
                        detail=f"Runtime '{runtime}' not available. {runtime_msg}."
                    )
                else:
                    runtime_qualifier = "secure " if enforce_gvisor else ""
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Runtime '{runtime}' not available. Available {runtime_qualifier}runtimes: {', '.join(secure_runtimes)}"
                    )
            
            # Execute the function through the selected engine
            logger.info(f"Submitting function {function_id} to engine with gVisor security enforced={enforce_gvisor}")
            result = await engine.execute_function(function, request)
            logger.info(f"Engine execution result: {result}")
            
            # Check for security issues with gVisor if enforcing
            if enforce_gvisor and result.get("status") == "success" and not result.get("gvisor_verified", False):
                raise HTTPException(
                    status_code=500,
                    detail="SECURITY ERROR: Function executed but gVisor security could not be verified. Execution rejected."
                )
            
            # Other error checks
            if result.get("status") == "error" and result.get("security_issue"):
                raise HTTPException(
                    status_code=500,
                    detail=f"SECURITY ERROR: {result.get('error', 'Function execution failed with a security error')}. Execution aborted."
                )
            
            # Get job ID from result
            job_id = result.get("job_id")
            if not job_id:
                raise HTTPException(status_code=500, detail="No job ID returned from execution")
            
            logger.info(f"Got job ID: {job_id}")
            
            # Format job name for kubernetes
            short_job_id = job_id[:8] if len(job_id) > 8 else job_id
            job_name = f"job-{short_job_id}"
            logger.info(f"Job name: {job_name}")
            
            # Record metrics for job submission
            end_time = time.time()
            await metrics_collector.collect_execution_metrics(
                function=function,
                request=request,
                start_time=start_time,
                end_time=end_time,
                success=True,
                error=None,
                resource_usage={
                    "memory_used": function.memory,
                    "execution_time": 0,
                    "submission_time": end_time - start_time
                }
            )
            
            # If we're not waiting for logs, return immediately
            if not wait_for_logs:
                return {
                    "status": "submitted",
                    "job_id": job_id,
                    "job_name": job_name,
                    "message": "Function submitted, not waiting for logs",
                    "runtime": runtime
                }
            
            # Wait for job to complete and get logs
            logger.info(f"Waiting for job {job_name} to complete (max {max_wait_seconds} seconds)...")
            job_completed = False
            pod_name = None
            logs = ""
            
            # Wait loop for job completion
            for attempt in range(max_wait_seconds):
                # Try to check if job exists yet
                cmd = ["kubectl", "get", "job", job_name, "-o", "json"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    job_data = json.loads(result.stdout)
                    
                    # Check if job is complete
                    if job_data.get("status", {}).get("succeeded", 0) > 0:
                        logger.info(f"Job {job_name} completed successfully")
                        job_completed = True
                        break
                    elif job_data.get("status", {}).get("failed", 0) > 0:
                        logger.info(f"Job {job_name} failed")
                        job_completed = True
                        break
                    else:
                        # Try to find the pod
                        if not pod_name:
                            # Try multiple ways to find the pod
                            pod_cmd = ["kubectl", "get", "pods", f"--selector=job-name={job_name}", "-o", "jsonpath='{.items[0].metadata.name}'"]
                            pod_result = subprocess.run(pod_cmd, capture_output=True, text=True)
                            
                            if pod_result.returncode == 0 and pod_result.stdout.strip("'"):
                                pod_name = pod_result.stdout.strip("'")
                                logger.info(f"Found pod: {pod_name}")
                
                # If we found a pod, try to get logs even if job is not complete
                if pod_name:
                    logs_cmd = ["kubectl", "logs", pod_name]
                    logs_result = subprocess.run(logs_cmd, capture_output=True, text=True)
                    
                    if logs_result.returncode == 0 and logs_result.stdout:
                        logs = logs_result.stdout
                        logger.info(f"Retrieved logs from pod {pod_name} (length: {len(logs)})")
                
                # If job is still running, wait before checking again
                if not job_completed:
                    logger.info(f"Job still running, waiting... (attempt {attempt+1}/{max_wait_seconds})")
                    time.sleep(1)
                else:
                    break
            
            # If we didn't find logs from the pod, try getting logs directly from the job
            if not logs:
                logger.info(f"Trying to get logs directly from job {job_name}")
                job_logs_cmd = ["kubectl", "logs", f"job/{job_name}"]
                job_logs_result = subprocess.run(job_logs_cmd, capture_output=True, text=True)
                
                if job_logs_result.returncode == 0 and job_logs_result.stdout:
                    logs = job_logs_result.stdout
                    logger.info(f"Retrieved logs from job {job_name} (length: {len(logs)})")
            
            # Return the execution result with logs
            return {
                "status": "completed" if job_completed else "running",
                "job_id": job_id,
                "job_name": job_name,
                "pod_name": pod_name,
                "logs": logs,
                "wait_timeout": not job_completed and max_wait_seconds > 0,
                "runtime": runtime
            }
                
        except Exception as e:
            logger.error(f"Error during execution: {str(e)}")
            logger.error(traceback.format_exc())
                
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
            status_code=500,
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
    except Exception as e:
        logger.error(f"Error deleting function: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting function: {str(e)}"
        )

@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get the status of a job by checking function records, Kubernetes, and Redis"""
    try:
        # First check if we have a pod name stored for this job
        pod_name = None
        short_job_id = job_id[:8] if len(job_id) > 8 else job_id
        expected_job_name = f"job-{short_job_id}"
        
        # Find functions with worker pods that match our job ID pattern
        functions = db.query(Function).filter(Function.worker_pod.isnot(None)).all()
        for func in functions:
            if func.worker_pod and expected_job_name in func.worker_pod:
                pod_name = func.worker_pod
                logger.info(f"Found matching worker pod {pod_name} for job {job_id}")
                break
        
        # If we found a pod, check its status directly
        if pod_name:
            try:
                cmd = ["kubectl", "get", "pod", pod_name, "-o", "json"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    pod_data = json.loads(result.stdout)
                    pod_status = pod_data["status"]["phase"]
                    
                    if pod_status == "Succeeded":
                        return {"status": "completed", "pod_name": pod_name}
                    elif pod_status == "Failed":
                        return {"status": "failed", "error": "Pod failed", "pod_name": pod_name}
                    else:
                        return {"status": "running", "pod_status": pod_status, "pod_name": pod_name}
                else:
                    logger.warning(f"Failed to get status for pod {pod_name}: {result.stderr}")
                    # Pod might have been deleted, continue to other methods
            except Exception as pod_error:
                logger.warning(f"Error checking pod status: {str(pod_error)}")
        
        # If we couldn't find the pod or get its status, try checking job directly
        try:
            cmd = ["kubectl", "get", "job", expected_job_name, "-o", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                job_data = json.loads(result.stdout)
                
                # Check job status conditions
                if job_data.get("status", {}).get("succeeded", 0) > 0:
                    return {"status": "completed", "job_name": expected_job_name}
                elif job_data.get("status", {}).get("failed", 0) > 0:
                    return {"status": "failed", "error": "Job failed", "job_name": expected_job_name}
                else:
                    active = job_data.get("status", {}).get("active", 0)
                    if active > 0:
                        return {"status": "running", "job_name": expected_job_name}
                    else:
                        return {"status": "pending", "job_name": expected_job_name}
            # If job not found, continue to next check
        except Exception as job_error:
            logger.warning(f"Error checking job status: {str(job_error)}")
        
        # Check Redis for completed or failed jobs
        try:
            r = redis.Redis(host='localhost', port=6379, db=0)
            
            # Check completed jobs
            completed_jobs = r.lrange('completed_jobs', 0, -1)
            for job_data in completed_jobs:
                try:
                    job = json.loads(job_data)
                    if job.get('job_id') == job_id:
                        return {
                            "status": job.get('status', 'completed'),
                            "runtime": job.get('runtime'),
                            "timestamp": job.get('timestamp'),
                            "source": "redis_completed"
                        }
                except json.JSONDecodeError:
                    continue
            
            # Check failed jobs
            failed_jobs = r.lrange('failed_jobs', 0, -1)
            for job_data in failed_jobs:
                try:
                    job = json.loads(job_data)
                    if job.get('job_id') == job_id:
                        return {
                            "status": "failed",
                            "error": job.get('error'),
                            "timestamp": job.get('timestamp'),
                            "source": "redis_failed"
                        }
                except json.JSONDecodeError:
                    continue
            
            # Check job queue
            queued_jobs = r.lrange('job_queue', 0, -1)
            for job_data in queued_jobs:
                try:
                    job = json.loads(job_data)
                    if job.get('job_id') == job_id:
                        return {"status": "queued", "source": "redis_queue"}
                except json.JSONDecodeError:
                    continue
        except Exception as redis_error:
            logger.warning(f"Error checking Redis: {str(redis_error)}")
        
        # If not found anywhere, job doesn't exist or has been deleted
        return {"status": "not_found", "job_id": job_id}
            
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        return {"status": "error", "error": str(e), "job_id": job_id}

@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    """Get logs directly from Kubernetes for a job"""
    try:
        # Format the expected job name
        short_job_id = job_id[:8] if len(job_id) > 8 else job_id
        job_name = f"job-{short_job_id}"
        
        logger.info(f"========== LOG RETRIEVAL START FOR {job_id} ==========")
        logger.info(f"Using short job ID: {short_job_id}, job name: {job_name}")
        
        # First try to get logs directly from the job
        logger.info(f"ATTEMPT 1: Getting logs directly from job/{job_name}")
        cmd = ["kubectl", "logs", f"job/{job_name}"]
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        logger.info(f"Exit code: {result.returncode}")
        logger.info(f"Stdout length: {len(result.stdout)}")
        if result.stderr:
            logger.info(f"Stderr: {result.stderr}")
        
        if result.returncode == 0 and result.stdout:
            logger.info("SUCCESS: Got logs directly from job")
            logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
            return {"logs": result.stdout}
        
        # If that didn't work, find the pod associated with the job
        logger.info(f"ATTEMPT 2: Finding pod for job {job_name} using job-name selector")
        pod_cmd = ["kubectl", "get", "pods", "--selector=job-name=" + job_name, "-o", "jsonpath='{.items[0].metadata.name}'"]
        logger.info(f"Running command: {' '.join(pod_cmd)}")
        pod_result = subprocess.run(pod_cmd, capture_output=True, text=True)
        
        logger.info(f"Exit code: {pod_result.returncode}")
        logger.info(f"Stdout: {pod_result.stdout}")
        if pod_result.stderr:
            logger.info(f"Stderr: {pod_result.stderr}")
        
        # If first selector didn't work, try another common selector
        if pod_result.returncode != 0 or not pod_result.stdout.strip("'"):
            logger.info(f"ATTEMPT 3: Finding pod for job {job_name} using job selector")
            pod_cmd = ["kubectl", "get", "pods", "--selector=job=" + job_name, "-o", "jsonpath='{.items[0].metadata.name}'"]
            logger.info(f"Running command: {' '.join(pod_cmd)}")
            pod_result = subprocess.run(pod_cmd, capture_output=True, text=True)
            
            logger.info(f"Exit code: {pod_result.returncode}")
            logger.info(f"Stdout: {pod_result.stdout}")
            if pod_result.stderr:
                logger.info(f"Stderr: {pod_result.stderr}")
        
        # If pod found, get logs
        if pod_result.returncode == 0 and pod_result.stdout.strip("'"):
            pod_name = pod_result.stdout.strip("'")
            logger.info(f"SUCCESS: Found pod {pod_name}, getting logs")
            logs_cmd = ["kubectl", "logs", pod_name]
            logger.info(f"Running command: {' '.join(logs_cmd)}")
            logs_result = subprocess.run(logs_cmd, capture_output=True, text=True)
            
            logger.info(f"Exit code: {logs_result.returncode}")
            logger.info(f"Stdout length: {len(logs_result.stdout)}")
            if logs_result.stderr:
                logger.info(f"Stderr: {logs_result.stderr}")
            
            if logs_result.returncode == 0:
                logger.info("SUCCESS: Got logs from pod")
                logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
                return {"logs": logs_result.stdout}
            else:
                logger.error(f"FAILED: Error getting logs from pod {pod_name}")
                logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
                return {"logs": f"Error getting logs: {logs_result.stderr}", "error": True}
        
        # If we can't find pod by label, try listing all pods and grep for job ID
        logger.info(f"ATTEMPT 4: Listing all pods to find any related to job {job_name}")
        list_cmd = ["kubectl", "get", "pods", "-o", "wide"]
        logger.info(f"Running command: {' '.join(list_cmd)}")
        list_result = subprocess.run(list_cmd, capture_output=True, text=True)
        
        logger.info(f"Exit code: {list_result.returncode}")
        if list_result.stderr:
            logger.info(f"Stderr: {list_result.stderr}")
        
        if list_result.returncode == 0:
            # Log all pods for debugging
            logger.info(f"All pods: {list_result.stdout}")
            pod_found = False
            
            # Try to find any pod containing our job ID in the name
            for line in list_result.stdout.splitlines():
                if short_job_id in line:
                    parts = line.split()
                    if parts:
                        potential_pod = parts[0]
                        logger.info(f"Found potential pod: {potential_pod}")
                        pod_found = True
                        
                        # Try to get logs from this pod
                        logger.info(f"ATTEMPT 5: Getting logs from potential pod {potential_pod}")
                        pod_logs_cmd = ["kubectl", "logs", potential_pod]
                        logger.info(f"Running command: {' '.join(pod_logs_cmd)}")
                        pod_logs_result = subprocess.run(pod_logs_cmd, capture_output=True, text=True)
                        
                        logger.info(f"Exit code: {pod_logs_result.returncode}")
                        logger.info(f"Stdout length: {len(pod_logs_result.stdout)}")
                        if pod_logs_result.stderr:
                            logger.info(f"Stderr: {pod_logs_result.stderr}")
                        
                        if pod_logs_result.returncode == 0:
                            logger.info("SUCCESS: Got logs from potential pod")
                            logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
                            return {"logs": pod_logs_result.stdout}
            
            if not pod_found:
                logger.info("No pods found with matching job ID in name")
        
        # Last resort - describe the job for any useful information
        logger.info(f"ATTEMPT 6: Describing job {job_name}")
        describe_cmd = ["kubectl", "describe", f"job/{job_name}"]
        logger.info(f"Running command: {' '.join(describe_cmd)}")
        describe_result = subprocess.run(describe_cmd, capture_output=True, text=True)
        
        logger.info(f"Exit code: {describe_result.returncode}")
        logger.info(f"Stdout length: {len(describe_result.stdout)}")
        if describe_result.stderr:
            logger.info(f"Stderr: {describe_result.stderr}")
        
        if describe_result.returncode == 0:
            logger.info("SUCCESS: Got job description")
            logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
            return {"logs": f"Could not find direct logs, but here's job information:\n{describe_result.stdout}"}
        
        # Try listing jobs
        logger.info(f"ATTEMPT 7: Listing all jobs")
        jobs_cmd = ["kubectl", "get", "jobs"]
        logger.info(f"Running command: {' '.join(jobs_cmd)}")
        jobs_result = subprocess.run(jobs_cmd, capture_output=True, text=True)
        
        logger.info(f"Exit code: {jobs_result.returncode}")
        logger.info(f"Stdout: {jobs_result.stdout}")
        if jobs_result.stderr:
            logger.info(f"Stderr: {jobs_result.stderr}")
        
        # If we've tried everything and failed
        logger.info("FAILED: All attempts to get logs have failed")
        logger.info(f"========== LOG RETRIEVAL END FOR {job_id} ==========")
        return {"logs": f"No logs found for job {job_id}. The job may not have started yet or may have been deleted."}
            
    except Exception as e:
        logger.error(f"Error getting job logs: {str(e)}")
        logger.error(traceback.format_exc())
        return {"logs": f"Error retrieving logs: {str(e)}", "error": True} 