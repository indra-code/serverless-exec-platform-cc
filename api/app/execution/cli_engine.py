import logging
import os
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import asyncio
from ..models.function import Function
from ..schemas.function import FunctionExecutionRequest

logger = logging.getLogger(__name__)

class CLIExecutionEngine:
    """Execution engine that uses the run_function.py CLI tool"""
    
    def __init__(self):
        self.project_root = Path(os.path.abspath(__file__)).parent.parent.parent.parent
        self.run_function_path = self.project_root / "run_function.py"
        
        # Ensure the CLI tool exists and is executable
        if not self.run_function_path.exists():
            raise FileNotFoundError(f"CLI tool not found at {self.run_function_path}")
        
        # Make sure it's executable
        try:
            os.chmod(self.run_function_path, 0o755)
        except Exception as e:
            logger.warning(f"Could not set executable permissions on {self.run_function_path}: {e}")
        
        logger.info(f"CLI Execution Engine initialized with run_function.py at {self.run_function_path}")
    
    async def execute_function(self, function: Function, request: FunctionExecutionRequest) -> Dict[str, Any]:
        """Execute a function using the CLI tool"""
        try:
            logger.info(f"Executing function {function.id} using CLI tool")
            
            # Convert code_path to absolute path if it's not already
            code_path = Path(function.code_path)
            if not code_path.is_absolute():
                code_path = code_path.absolute()
            
            # Validate function code path exists
            if not code_path.exists():
                error_msg = f"Function file {code_path} does not exist"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
            
            # Store any data for the function in a temporary file
            with tempfile.NamedTemporaryFile(suffix='.json', mode='wb', delete=False) as temp_data:
                temp_data_path = temp_data.name
                json_data = json.dumps(request.data).encode('utf-8')
                temp_data.write(json_data)
            
            try:
                # Build command
                cmd = [
                    str(self.run_function_path),
                    "--code", str(code_path)
                ]
                
                # Set runtime if specified
                runtime = getattr(function, 'runtime', None)
                if runtime:
                    cmd.extend(["--runtime", runtime])
                
                # Set memory if specified
                memory = getattr(function, 'memory', None)
                if memory:
                    cmd.extend(["--memory", f"{memory}Mi"])
                
                # Execute the command
                logger.debug(f"Executing command: {' '.join(cmd)}")
                
                # Use asyncio to run the command asynchronously
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await proc.communicate()
                
                # Process the results
                exit_code = proc.returncode
                stdout_text = stdout.decode('utf-8') if stdout else ""
                stderr_text = stderr.decode('utf-8') if stderr else ""
                
                if exit_code != 0:
                    logger.error(f"CLI execution failed with exit code {exit_code}: {stderr_text}")
                    return {
                        "status": "error",
                        "error": f"CLI execution failed with exit code {exit_code}: {stderr_text}",
                        "stdout": stdout_text
                    }
                
                # Extract job ID from output
                job_id = None
                for line in stdout_text.split('\n'):
                    if "Job" in line and "submitted to queue successfully" in line:
                        parts = line.split()
                        if len(parts) > 1:
                            job_id = parts[1]
                            break
                
                if not job_id:
                    logger.warning("Could not extract job ID from CLI output")
                    job_id = "unknown"
                
                return {
                    "status": "success",
                    "message": "Function submitted to execution queue",
                    "job_id": job_id,
                    "stdout": stdout_text,
                    "execution_method": "cli"
                }
                
            finally:
                # Clean up the temporary data file
                try:
                    os.unlink(temp_data_path)
                except Exception as e:
                    logger.warning(f"Could not delete temporary data file {temp_data_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error executing function with CLI: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def cleanup(self):
        """Clean up any resources"""
        pass  # No cleanup needed 