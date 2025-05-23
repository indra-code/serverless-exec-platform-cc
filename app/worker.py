import redis
import json
import time
import os
import logging
import subprocess
import re
from k8s_job_maker import create_k8s_job

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("worker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("worker")

# Redis connection
r = redis.Redis(host='localhost', port=6379, db=0)

# Minikube path mapping - map host paths to minikube paths
HOST_PATH_PREFIX = "/home/jayanth/Documents/cc/serverless-exec-platform-cc"
MINIKUBE_PATH_PREFIX = "/hosthome/jayanth/serverless-exec-platform-cc"

def map_path_to_minikube(host_path):
    """Convert host path to minikube path"""
    # Get absolute path if it's not already absolute
    if not os.path.isabs(host_path):
        host_path = os.path.abspath(host_path)
        
    # Log original and absolute path
    logger.info(f"Original path: {host_path}")
    
    # Map the path to Minikube
    minikube_path = host_path
    if HOST_PATH_PREFIX in host_path:
        minikube_path = host_path.replace(HOST_PATH_PREFIX, MINIKUBE_PATH_PREFIX)
        logger.info(f"Mapped path to Minikube: {minikube_path}")
    else:
        # If direct replacement doesn't work, try to be smarter about mapping
        # Sometimes we need to handle relative paths differently
        rel_path = os.path.relpath(host_path, HOST_PATH_PREFIX)
        if not rel_path.startswith('..'):
            # The path is inside our project directory
            minikube_path = os.path.join(MINIKUBE_PATH_PREFIX, rel_path)
            logger.info(f"Mapped relative path to Minikube: {minikube_path}")
    
    return minikube_path

def ensure_required_imports(file_path):
    """Check and add any missing required imports"""
    try:
        # Read the file content
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Check for imports
        required_imports = {
            'os': 'import os',
            'sys': 'import sys',
            'json': 'import json'
        }
        
        missing_imports = []
        for module, import_stmt in required_imports.items():
            # Check if the module is imported using any method
            if not (re.search(fr'import\s+{module}\b', content) or 
                    re.search(fr'from\s+.*\s+import\s+.*\b{module}\b', content)):
                missing_imports.append(import_stmt)
                
        if missing_imports:
            logger.info(f"Adding missing imports to {file_path}: {missing_imports}")
            
            # Add imports at the beginning of the file
            new_content = '\n'.join(missing_imports) + '\n\n' + content
            
            # Write the updated content
            with open(file_path, 'w') as f:
                f.write(new_content)
                
            logger.info(f"Added missing imports to {file_path}")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error ensuring imports in file {file_path}: {str(e)}")
        return False

def cancel_job(job_id):
    """Cancel a running job in Kubernetes"""
    try:
        # Truncate job ID to 8 characters to match how it's created
        short_job_id = job_id[:8] if len(job_id) > 8 else job_id
        job_name = f"job-{short_job_id}"
        
        logger.info(f"Attempting to cancel job {job_name}")
        
        # Delete the job
        cmd = ["kubectl", "delete", "job", job_name, "--force", "--grace-period=0"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Successfully cancelled job {job_name}")
            
            # Add job to failed jobs list
            r.lpush('failed_jobs', json.dumps({
                'job_id': job_id,
                'error': "Job cancelled by user",
                'timestamp': time.time()
            }))
            
            return True
        else:
            logger.error(f"Failed to cancel job {job_name}: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {str(e)}")
        return False

logger.info("Worker started - waiting for jobs...")

while True:
    try:
        # Check for job cancellations first
        cancel_data = r.rpop('cancel_jobs')
        if cancel_data:
            try:
                cancel_info = json.loads(cancel_data)
                job_id = cancel_info.get('job_id')
                if job_id:
                    logger.info(f"Received cancellation request for job {job_id}")
                    cancel_job(job_id)
            except json.JSONDecodeError:
                logger.error(f"Invalid cancellation data: {cancel_data}")
        
        # Try to get a job from the queue
        job_data = r.rpop('job_queue')
        if job_data:
            try:
                job = json.loads(job_data)
                job_id = job['job_id']
                logger.info(f"Got job: {job_id}")
                
                # Map the code path to minikube path
                code_path = job['code_path']
                
                # Ensure the file has required imports before submitting to k8s
                ensure_required_imports(code_path)
                
                minikube_code_path = map_path_to_minikube(code_path)
                
                # Log the path mapping
                logger.info(f"Host path: {code_path}")
                logger.info(f"Minikube path: {minikube_code_path}")
                
                # Check if a specific runtime was requested
                runtime = job.get('runtime', 'default')
                logger.info(f"Requested runtime: {runtime}")
                
                # Extract additional parameters
                memory = job.get('memory', 128)  # Default to 128Mi
                timeout = job.get('timeout', 30)  # Default to 30 seconds
                data = job.get('data', {})  # Additional data for the function
                
                # Create the Kubernetes job
                try:
                    # Check if this is a gVisor job
                    if runtime == "gvisor":
                        from k8s_job_maker import create_gvisor_job
                        # Use the specialized gVisor job creation function
                        create_gvisor_job(
                            job_id=job_id,
                            code_path=minikube_code_path,
                            memory=memory,
                            timeout=timeout,
                            data=data
                        )
                        logger.info(f"gVisor job {job_id} created successfully")
                    else:
                        # Use the standard job creation function
                        from k8s_job_maker import create_k8s_job
                        create_k8s_job(
                            job_id=job_id, 
                            code_path=minikube_code_path, 
                            runtime=runtime,
                            memory=memory,
                            timeout=timeout,
                            data=data
                        )
                        logger.info(f"Standard job {job_id} created successfully with runtime {runtime}")
                    
                    # Add job to completed jobs list
                    r.lpush('completed_jobs', json.dumps({
                        'job_id': job_id,
                        'status': 'submitted',
                        'runtime': runtime,
                        'memory': memory,
                        'timeout': timeout,
                        'timestamp': time.time()
                    }))
                except Exception as e:
                    logger.error(f"Error creating job {job_id}: {str(e)}")
                    # Add job to failed jobs list
                    r.lpush('failed_jobs', json.dumps({
                        'job_id': job_id,
                        'error': str(e),
                        'timestamp': time.time()
                    }))
            except json.JSONDecodeError:
                logger.error(f"Invalid job data: {job_data}")
        else:
            # No job in queue
            time.sleep(1)
    except Exception as e:
        logger.error(f"Error processing job queue: {str(e)}")
        time.sleep(5)  # Wait a bit longer on errors

