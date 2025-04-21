import subprocess
import json
import logging
import os
import tempfile
import shutil
import time
from typing import Dict, Any, Optional
from ..models.function import Function
from ..schemas.function import FunctionExecutionRequest
import docker

logger = logging.getLogger(__name__)

class GVisorEngine:
    def __init__(self, is_wsl: bool = False):
        self.is_wsl = False  # Always use native Linux mode
        # We'll use subprocess for Docker operations instead of docker-py
        self.container_pool = {}
        self.function_metadata = {}  # Store function metadata
        
        # Verify runsc is available
        try:
            # Native Linux mode
            result = subprocess.run(['which', 'runsc'], 
                                 capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("runsc not found on native Linux")
            
            # Configure Docker to use gVisor
            self._configure_docker()
            
        except Exception as e:
            logger.error(f"Failed to initialize gVisor: {str(e)}")
            raise

    def _configure_docker(self):
        """Configure Docker to use gVisor runtime"""
        try:
            # Check if Docker is configured for gVisor
            result = subprocess.run(['docker', 'info'], 
                                 capture_output=True, text=True)
            if 'runsc' not in result.stdout:
                raise RuntimeError("Docker is not configured for gVisor on Linux. Please run the setup_gvisor_arch.sh script.")
            
            logger.info("Docker is correctly configured for gVisor on Linux")
            
        except Exception as e:
            logger.error(f"Failed to configure Docker for gVisor: {str(e)}")
            raise

    def register_function(self, function: Function):
        """Register function metadata for later use"""
        function_id = str(function.id)
        self.function_metadata[function_id] = {
            "id": function_id,
            "name": function.name,
            "description": function.description,
            "code_path": function.code_path,
            "runtime": function.runtime,
            "timeout": function.timeout,
            "memory": function.memory,
            "is_active": function.is_active
        }
        logger.info(f"Function {function.name} (ID: {function_id}) registered with gVisor engine")
        return self.function_metadata[function_id]

    def execute_function(self, function_id: str, code: str, runtime: str) -> dict:
        """Execute a function using gVisor"""
        try:
            # Create a temporary directory for the function
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write the function code to a file
                code_path = os.path.join(temp_dir, "function.py")
                with open(code_path, "w") as f:
                    f.write(code)

                # Native Linux mode
                # Execute the container directly using subprocess to avoid credential issues
                result = subprocess.run(
                    ['docker', 'run', '--runtime=runsc', '--rm', '-v', f'{temp_dir}:/app', f'python:3.9-{runtime}', 'python', '/app/function.py'],
                    capture_output=True,
                    text=True
                )

                return {
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr
                }

        except Exception as e:
            logger.error(f"Failed to execute function: {str(e)}")
            raise

    def cleanup(self):
        """Clean up any resources"""
        pass  # No cleanup needed as we use temporary directories
    
    def _get_container(self, function_id: str) -> Optional[str]:
        """Get a container from the pool or create a new one"""
        if function_id not in self.container_pool:
            self.container_pool[function_id] = []
        
        if self.container_pool[function_id]:
            return self.container_pool[function_id].pop()
        return None
    
    def _return_container(self, function_id: str, container_id: str):
        """Return a container to the pool"""
        if function_id not in self.container_pool:
            self.container_pool[function_id] = []
        
        if len(self.container_pool[function_id]) < 10:  # Max pool size
            self.container_pool[function_id].append(container_id)
        else:
            # Clean up excess container
            subprocess.run(['docker', 'stop', container_id], check=True)
            subprocess.run(['docker', 'rm', container_id], check=True)
    
    def _create_container(self, function: Function) -> str:
        """Create a new container for a function"""
        try:
            # Store function metadata if not already stored
            function_id = str(function.id)
            if function_id not in self.function_metadata:
                self.register_function(function)
                
            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Read function code from code_path
                with open(function.code_path, "r") as src_file:
                    code_content = src_file.read()
                    
                # Write the code to the temp directory
                with open(os.path.join(temp_dir, "handler.py"), "w") as f:
                    f.write(code_content)
                
                # Create a simple Dockerfile with additional dependencies if needed
                runtime = function.runtime
                dockerfile = f"""
FROM python:3.10-{runtime}
WORKDIR /app
COPY handler.py /app/
RUN pip install --no-cache-dir fastapi uvicorn
CMD ["python", "handler.py"]
"""
                with open(os.path.join(temp_dir, "Dockerfile"), "w") as f:
                    f.write(dockerfile)
                
                # Build the image using subprocess instead of docker-py
                image_name = f"function-{function.id}"
                subprocess.run(
                    ['docker', 'build', '-t', image_name, temp_dir],
                    check=True
                )
                
                # Run the container with gVisor using subprocess
                env_vars = [
                    "-e", f"FUNCTION_ID={function_id}",
                    "-e", f"FUNCTION_NAME={function.name}",
                    "-e", f"FUNCTION_TIMEOUT={function.timeout}"
                ]
                
                result = subprocess.run(
                    ['docker', 'run', '--runtime=runsc', '-d', '--memory', f"{function.memory}m"] + 
                    env_vars + [image_name],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Return the container ID
                container_id = result.stdout.strip()
                return container_id
            
        except Exception as e:
            logger.error(f"Error creating container: {str(e)}")
            raise
    
    async def execute_function(self, function: Function, request: FunctionExecutionRequest):
        start_time = time.time()
        
        # Register function metadata if not already registered
        function_id = str(function.id)
        if function_id not in self.function_metadata:
            self.register_function(function)
            
        try:
            # Try to get a container from the pool
            container_id = self._get_container(function_id)
            
            # If no container available, create a new one
            if not container_id:
                container_id = self._create_container(function)
            
            try:
                # Execute the function using Docker exec command
                env_vars = [
                    "-e", f"REQUEST_DATA={json.dumps(request.dict())}",
                    "-e", f"FUNCTION_TIMEOUT={function.timeout}"
                ]
                
                result = subprocess.run(
                    ['docker', 'exec'] + env_vars + [container_id, 'python', '/app/handler.py'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Return container to pool
                self._return_container(function_id, container_id)
                
                end_time = time.time()
                execution_time = end_time - start_time
                
                # Log metrics
                logger.info(f"Function {function.name} (ID: {function_id}) executed in {execution_time:.4f} seconds")
                
                return {
                    "status": "success",
                    "function_id": function_id,
                    "function_name": function.name,
                    "output": result.stdout,
                    "execution_time": execution_time
                }
                
            except subprocess.CalledProcessError as e:
                # If there's an error, clean up the container
                subprocess.run(['docker', 'stop', container_id], check=False)
                subprocess.run(['docker', 'rm', container_id], check=False)
                
                return {
                    "status": "error",
                    "function_id": function_id,
                    "function_name": function.name,
                    "error": e.stderr,
                    "execution_time": time.time() - start_time
                }
                
        except Exception as e:
            logger.error(f"Error executing function {function.id}: {str(e)}")
            end_time = time.time()
            return {
                "status": "error",
                "function_id": function_id,
                "function_name": function.name,
                "error": str(e),
                "execution_time": end_time - start_time
            } 