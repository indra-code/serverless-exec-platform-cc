import logging
import os
import subprocess
import time
import uuid
import asyncio
import json
import redis
from typing import Dict, Any, Optional
import tempfile
from pathlib import Path

from .engine import ExecutionEngine
from ..models.function import Function
from ..schemas.function import FunctionExecutionRequest

logger = logging.getLogger(__name__)

class GVisorEngine(ExecutionEngine):
    """
    Dedicated gVisor engine that provides maximum isolation for function execution.
    This engine uses OCI containers with gVisor runtime for full isolation.
    """
    
    def __init__(self, is_wsl=False):
        self.logger = logging.getLogger(__name__)
        self.is_wsl = is_wsl
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        
        # Verify gVisor installation
        self.verified_gvisor = self._verify_gvisor()
        if not self.verified_gvisor:
            raise RuntimeError("gVisor installation could not be verified")
    
    def _verify_gvisor(self) -> bool:
        """
        Verify that gVisor (runsc) is properly installed and configured
        """
        try:
            # Check that runsc is available
            runsc_check = subprocess.run(
                ["runsc", "--version"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if runsc_check.returncode != 0:
                self.logger.error("gVisor not available: runsc command failed")
                return False
            
            # Check that runsc is registered as a container runtime
            runtimes_check = subprocess.run(
                ["runsc", "list"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if runtimes_check.returncode != 0:
                self.logger.error("gVisor runtime list check failed")
                return False
            
            # All checks passed
            self.logger.info(f"gVisor verified: {runsc_check.stdout.strip()}")
            return True
            
        except Exception as e:
            self.logger.error(f"gVisor verification error: {str(e)}")
            return False
    
    async def execute_function(self, function, request) -> Dict[str, Any]:
        """
        Submit function to the Redis queue for execution in a secure gVisor container
        by the worker process. This allows for better integration with the existing
        execution flow and worker system.
        """
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        # Log the execution request
        self.logger.info(f"Submitting function {function.id} to job queue with job ID {job_id}")
        
        try:
            # Create job data for the queue
            job_data = {
                "job_id": job_id,
                "code_path": function.code_path,
                "runtime": "gvisor",  # Specify gVisor runtime for the worker
                "memory": function.memory,
                "timeout": function.timeout,
                "data": request.data if hasattr(request, 'data') else {}
            }
            
            # Submit to Redis queue
            self.r.lpush('job_queue', json.dumps(job_data))
            
            self.logger.info(f"Function {function.id} submitted to job queue successfully as job {job_id}")
            
            # Return immediately with job ID for async tracking
            return {
                "status": "success",
                "job_id": job_id,
                "message": "Function submitted to queue for execution",
                "gvisor_verified": True,
                "execution_method": "gvisor"
            }
                
        except Exception as e:
            self.logger.error(f"Error submitting function to job queue: {str(e)}")
            return {
                "status": "error",
                "job_id": job_id,
                "logs": "",
                "error": f"Queue submission error: {str(e)}",
                "gvisor_verified": False,
                "security_issue": False,
                "execution_method": "gvisor"
            }
    
    def stop_function(self, job_id: str) -> bool:
        """Stop a function execution by job ID"""
        container_name = f"gvisor-function-{job_id}"
        
        try:
            # Try to delete the container
            subprocess.run(["runsc", "delete", "-f", container_name], check=True)
            self.logger.info(f"Stopped container {container_name}")
            
            # Also add to a cancel_job queue to inform worker
            self.r.lpush('cancel_jobs', json.dumps({
                'job_id': job_id,
                'timestamp': time.time()
            }))
            
            return True
        except Exception as e:
            self.logger.error(f"Error stopping container {container_name}: {str(e)}")
            return False 