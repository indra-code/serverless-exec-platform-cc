from typing import Dict, Optional, List, Any
import docker
import time
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from ..models.function import Function
from ..schemas.function import FunctionExecutionRequest
import tempfile
import subprocess

logger = logging.getLogger(__name__)

class ContainerPool:
    def __init__(self, max_size: int = 10, docker_client: Optional[docker.DockerClient] = None):
        self.max_size = max_size
        self.docker_client = docker_client or docker.from_env()
        self.pool: Dict[str, List[docker.models.containers.Container]] = {}
        self.lock = threading.Lock()
        self.ensure_docker_available()
        
    def ensure_docker_available(self):
        """Ensure Docker is available and running"""
        try:
            self.docker_client.ping()
            logger.info("Docker is available and running")
        except Exception as e:
            logger.error(f"Docker is not available: {str(e)}")
            raise
        
    def get_container(self, function_id: str) -> Optional[docker.models.containers.Container]:
        with self.lock:
            if function_id not in self.pool:
                self.pool[function_id] = []
            
            if self.pool[function_id]:
                return self.pool[function_id].pop()
            return None
    
    def return_container(self, function_id: str, container: docker.models.containers.Container):
        with self.lock:
            if function_id not in self.pool:
                self.pool[function_id] = []
            
            if len(self.pool[function_id]) < self.max_size:
                self.pool[function_id].append(container)
            else:
                container.stop()
                container.remove()
    
    def create_container(self, function: Function) -> docker.models.containers.Container:
        # Convert Windows path to WSL path if needed
        code_path = function.code_path
        if os.name == 'nt':  # Windows
            # Convert Windows path to WSL path
            code_path = code_path.replace('\\', '/')
            if code_path.startswith('C:'):
                code_path = '/mnt/c' + code_path[2:]
        
        container = self.docker_client.containers.run(
            image="python:3.10-slim",
            volumes={code_path: {'bind': '/app/code', 'mode': 'ro'}},
            command=["python", "/app/code/handler.py"],
            detach=True,
            mem_limit=f"{function.memory}m",
            environment={
                "FUNCTION_ID": str(function.id),
                "TIMEOUT": str(function.timeout)
            }
        )
        return container

class ExecutionEngine:
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        self.docker_client = docker_client or docker.from_env()
        self.container_pool = ContainerPool()
        self.warmup_queue = Queue()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.warmup_thread = threading.Thread(target=self._warmup_worker, daemon=True)
        self.warmup_thread.start()
    
    def _warmup_worker(self):
        while True:
            function = self.warmup_queue.get()
            try:
                container = self.container_pool.create_container(function)
                self.container_pool.return_container(str(function.id), container)
                logger.info(f"Warmed up container for function {function.id}")
            except Exception as e:
                logger.error(f"Error warming up container for function {function.id}: {str(e)}")
            finally:
                self.warmup_queue.task_done()
    
    def warmup_function(self, function: Function):
        self.warmup_queue.put(function)
    
    async def execute_function(self, function: Function, request: FunctionExecutionRequest):
        try:
            # Try to get a container from the pool
            container = self.container_pool.get_container(str(function.id))
            
            # If no container available, create a new one
            if not container:
                container = self.container_pool.create_container(function)
            
            try:
                # Execute the function
                result = container.exec_run(
                    cmd=["python", "/app/code/handler.py"],
                    environment={
                        "REQUEST_DATA": request.json()
                    }
                )
                
                # Check for errors
                if result.exit_code != 0:
                    raise Exception(f"Function execution failed: {result.output.decode()}")
                
                # Return container to pool
                self.container_pool.return_container(str(function.id), container)
                
                return {
                    "status": "success",
                    "output": result.output.decode(),
                    "exit_code": result.exit_code
                }
                
            except Exception as e:
                # If there's an error, remove the container and create a new one
                container.stop()
                container.remove()
                raise e
                
        except Exception as e:
            logger.error(f"Error executing function {function.id}: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def execute_function_from_code(self, function_id: str, code: str, runtime: str) -> dict:
        """Execute a function using Docker"""
        try:
            # Create a temporary directory for the function
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write the function code to a file
                code_path = os.path.join(temp_dir, "function.py")
                with open(code_path, "w") as f:
                    f.write(code)

                # Build and run the container
                container = self.docker_client.containers.run(
                    f"python:3.9-slim",
                    command=["python", "/app/function.py"],
                    volumes={temp_dir: {'bind': '/app', 'mode': 'ro'}},
                    remove=True,
                    detach=False
                )

                return {
                    "success": True,
                    "output": container.decode('utf-8') if isinstance(container, bytes) else container,
                    "error": None
                }

        except Exception as e:
            logger.error(f"Failed to execute function: {str(e)}")
            raise

    def cleanup(self):
        """Clean up any resources"""
        pass  # No cleanup needed as we use temporary directories 