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
from ..metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)

class GVisorEngine:
    def __init__(self, is_wsl: bool = False):
        self.is_wsl = is_wsl
        if is_wsl:
            self.runsc_path = "/usr/local/bin/runsc"  # Path in WSL
            self.docker_socket = "unix:///var/run/docker.sock"
        else:
            self.runsc_path = "/usr/bin/runsc"  # Path in Linux
            self.docker_socket = "unix:///var/run/docker.sock"
        
        # Verify runsc is available
        if not os.path.exists(self.runsc_path):
            raise RuntimeError(f"runsc not found at {self.runsc_path}")
        
        # Configure Docker to use gVisor if not already configured
        self._configure_docker()

    def _configure_docker(self):
        """Configure Docker to use gVisor runtime"""
        docker_config_path = "/etc/docker/daemon.json"
        config = {
            "runtimes": {
                "runsc": {
                    "path": self.runsc_path
                }
            }
        }

        try:
            # Read existing config if it exists
            if os.path.exists(docker_config_path):
                with open(docker_config_path, 'r') as f:
                    existing_config = json.load(f)
                    if "runtimes" in existing_config:
                        existing_config["runtimes"].update(config["runtimes"])
                        config = existing_config

            # Write config
            with open(docker_config_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Restart Docker service
            if self.is_wsl:
                subprocess.run(["wsl", "-e", "sudo", "systemctl", "restart", "docker"], check=True)
            else:
                subprocess.run(["sudo", "systemctl", "restart", "docker"], check=True)

        except Exception as e:
            logger.error(f"Failed to configure Docker: {str(e)}")
            raise

    def execute_function(self, function_id: str, code: str, runtime: str) -> dict:
        """Execute a function using gVisor"""
        try:
            # Create a temporary directory for the function
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write the function code to a file
                code_path = os.path.join(temp_dir, "function.py")
                with open(code_path, "w") as f:
                    f.write(code)

                # Build and run the container
                docker_cmd = [
                    "docker", "run", "--rm",
                    "--runtime=runsc",
                    "-v", f"{temp_dir}:/app",
                    f"python:3.9-slim",
                    "python", "/app/function.py"
                ]

                if self.is_wsl:
                    # Convert Windows path to WSL path if needed
                    temp_dir = subprocess.check_output(
                        ["wsl", "wslpath", "-a", temp_dir]
                    ).decode().strip()
                    docker_cmd[4] = f"{temp_dir}:/app"

                result = subprocess.run(
                    docker_cmd,
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

    def ensure_gvisor_installed(self):
        try:
            # Check if we're in WSL
            if not os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop"):
                raise RuntimeError("gVisor requires WSL 2. Please ensure you're running in WSL 2.")
            
            # Check if gVisor is installed
            result = subprocess.run(["wsl", "-e", "bash", "-c", f"{self.runsc_path} --version"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("gVisor not installed in WSL. Please install gVisor first.")
                
        except Exception as e:
            logger.error(f"gVisor setup error: {str(e)}")
            raise RuntimeError("gVisor setup failed. Please ensure WSL 2 and gVisor are properly installed.")
    
    def _convert_windows_path_to_wsl(self, windows_path: str) -> str:
        """Convert Windows path to WSL path"""
        path = windows_path.replace('\\', '/')
        if path.startswith('C:'):
            return '/mnt/c' + path[2:]
        return path
    
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
            subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"{self.runsc_path} kill {container_id}"
            ], check=True)
    
    def _create_container(self, function: Function) -> str:
        """Create a new container for a function"""
        try:
            # Create a temporary directory in WSL
            temp_dir = subprocess.run(
                ["wsl", "-e", "bash", "-c", "mktemp -d"],
                capture_output=True, text=True
            ).stdout.strip()
            
            # Convert Windows path to WSL path
            code_path = self._convert_windows_path_to_wsl(function.code_path)
            
            # Copy function code to temp directory in WSL
            subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"cp {code_path} {temp_dir}/handler.py"
            ], check=True)
            
            # Create a simple Dockerfile
            dockerfile = f"""
FROM python:3.10-slim
WORKDIR /app
COPY handler.py /app/
CMD ["python", "handler.py"]
"""
            with open("Dockerfile", "w") as f:
                f.write(dockerfile)
            
            # Copy Dockerfile to WSL
            subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"cp /mnt/c/Users/{os.getenv('USERNAME')}/Dockerfile {temp_dir}/Dockerfile"
            ], check=True)
            
            # Build the image in WSL
            image_name = f"function-{function.id}"
            subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"cd {temp_dir} && docker build -t {image_name} ."
            ], check=True)
            
            # Run the container with gVisor in WSL
            container_id = subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"{self.runsc_path} run --rootless --network=none --memory-limit {function.memory}m {image_name}"
            ], capture_output=True, text=True).stdout.strip()
            
            # Clean up temp directory
            subprocess.run([
                "wsl", "-e", "bash", "-c",
                f"rm -rf {temp_dir}"
            ], check=True)
            
            return container_id
            
        except Exception as e:
            logger.error(f"Error creating container: {str(e)}")
            raise
    
    async def execute_function(self, function: Function, request: FunctionExecutionRequest):
        start_time = time.time()
        try:
            # Try to get a container from the pool
            container_id = self._get_container(str(function.id))
            
            # If no container available, create a new one
            if not container_id:
                container_id = self._create_container(function)
            
            try:
                # Execute the function
                result = subprocess.run([
                    "wsl", "-e", "bash", "-c",
                    f"{self.runsc_path} exec {container_id} python handler.py"
                ], capture_output=True, text=True)
                
                # Check for errors
                if result.returncode != 0:
                    raise Exception(f"Function execution failed: {result.stderr}")
                
                # Return container to pool
                self._return_container(str(function.id), container_id)
                
                end_time = time.time()
                
                return {
                    "status": "success",
                    "output": result.stdout,
                    "error": result.stderr,
                    "exit_code": result.returncode,
                    "execution_time": end_time - start_time
                }
                
            except Exception as e:
                # If there's an error, clean up the container
                subprocess.run([
                    "wsl", "-e", "bash", "-c",
                    f"{self.runsc_path} kill {container_id}"
                ], check=True)
                raise e
                
        except Exception as e:
            logger.error(f"Error executing function {function.id}: {str(e)}")
            end_time = time.time()
            return {
                "status": "error",
                "error": str(e),
                "execution_time": end_time - start_time
            } 