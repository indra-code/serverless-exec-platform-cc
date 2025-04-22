#!/usr/bin/env python3
import os
import sys
import tempfile
import subprocess
import argparse
import json
import time
import uuid
import redis
from datetime import datetime

# Redis connection
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    redis_client.ping()  # Test connection
    redis_available = True
    print("Connected to Redis server")
except Exception as e:
    print(f"Warning: Redis connection failed: {e}")
    print("Will fall back to gVisor if Redis is not available")
    redis_available = False

def submit_job_to_queue(code_path, runtime="python:3.9-slim", memory="128Mi"):
    """Submit a function to the Redis job queue"""
    if not redis_available:
        print("Redis not available, falling back to gVisor")
        return run_function_with_gvisor(code_path, runtime.split(":")[1] if ":" in runtime else runtime)
        
    try:
        # Create an absolute path
        code_path = os.path.abspath(code_path)
        if not os.path.exists(code_path):
            print(f"Error: File {code_path} does not exist")
            return False
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Copy the function to a consistent location for Kubernetes to find
        function_filename = os.path.basename(code_path)
        function_dir = os.path.dirname(os.path.abspath(__file__))  # Dir where this script is located
        k8s_code_dir = os.path.join(function_dir, "functions")
        os.makedirs(k8s_code_dir, exist_ok=True)
        
        # Create a unique filename to avoid conflicts
        k8s_filename = f"function_{job_id}.py"
        k8s_code_path = os.path.join(k8s_code_dir, k8s_filename)
        
        # Copy the function code
        with open(code_path, 'r') as src_file:
            code_content = src_file.read()
            
        with open(k8s_code_path, 'w') as dst_file:
            dst_file.write(code_content)
            
        print(f"Function code copied to {k8s_code_path}")
        
        # Create job data
        job_data = {
            "job_id": job_id,
            "code_path": k8s_code_path,  # Use the copied file path
            "runtime": runtime,
            "memory": memory,
            "timestamp": datetime.now().isoformat()
        }
        
        # Create log file to capture eventual output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"function_job_{job_id}_{timestamp}.log"
        with open(log_filename, "w") as log_file:
            log_file.write(f"Job submitted to queue: {job_id}\n")
            log_file.write(f"Original code path: {code_path}\n")
            log_file.write(f"K8s code path: {k8s_code_path}\n")
            log_file.write(f"Runtime: {runtime}\n")
            log_file.write(f"Timestamp: {timestamp}\n")
            log_file.write("--------------------------------------------\n")
            log_file.write("Job has been queued for execution. Check worker logs for execution results.\n")
        
        # Submit to Redis queue
        redis_client.lpush('job_queue', json.dumps(job_data))
        
        print(f"\n✅ Job {job_id} submitted to queue successfully!")
        print(f"Job details saved to {log_filename}")
        print("\nThe worker process will execute this job from the queue.")
        print("Check the worker logs for execution results.")
        
        return True
            
    except Exception as e:
        print(f"Error submitting job to queue: {str(e)}")
        return False

def verify_gvisor():
    """Verify that gVisor is properly installed and configured"""
    try:
        # First check if runsc binary exists
        runsc_check = subprocess.run(
            ["which", "runsc"],
            capture_output=True,
            text=True
        )
        if runsc_check.returncode != 0:
            print("❌ gVisor (runsc) binary not found in PATH")
            return False
            
        # Check if Docker is configured with gVisor runtime
        docker_info = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True
        )
        if docker_info.returncode != 0 or 'runsc' not in docker_info.stdout:
            print("❌ Docker is not configured with gVisor runtime")
            return False
            
        # Test gVisor with a simple container
        result = subprocess.run(
            ["docker", "run", "--runtime=runsc", "--rm", "hello-world"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"❌ gVisor test failed: {result.stderr}")
            return False
            
        print("✅ gVisor is properly installed and configured")
        return True
    except Exception as e:
        print(f"❌ Error verifying gVisor: {str(e)}")
        return False

def run_function_with_gvisor(code_path, runtime="slim", strict_verify=False):
    """Run a function directly with gVisor"""
    
    # First verify gVisor is available and working
    if not verify_gvisor():
        print("❌ Function execution aborted: gVisor is not properly configured")
        return False
        
    try:
        # Create an absolute path
        code_path = os.path.abspath(code_path)
        if not os.path.exists(code_path):
            print(f"Error: File {code_path} does not exist")
            return False
            
        # Get the directory containing the function
        function_dir = os.path.dirname(code_path)
        function_file = os.path.basename(code_path)
        
        print(f"Running function {code_path} with gVisor...")
        
        # Create a unique identifier for this run
        run_id = str(uuid.uuid4())[:8]
        
        # Create a wrapper script that verifies gVisor and runs the function
        wrapper_path = os.path.join(function_dir, f"_gvisor_wrapper_{run_id}.py")
        with open(wrapper_path, "w") as f:
            f.write(f"""
import os
import sys
import json
import subprocess

def verify_inside_gvisor():
    # Check for markers that we're running in gVisor
    # gVisor has specific dmesg signatures
    try:
        dmesg = subprocess.run(
            ["dmesg"], 
            capture_output=True, 
            text=True
        )
        if "runsc" in dmesg.stdout:
            print("RUNNING_IN_GVISOR: TRUE")
            return True
    except:
        pass
        
    # Alternative check: gVisor has different host info
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        if "SENTRY" in cpuinfo or "PTRACE" in cpuinfo:
            print("RUNNING_IN_GVISOR: TRUE")
            return True
    except:
        pass
            
    print("RUNNING_IN_GVISOR: FALSE")
    return False

# Run the verification first
is_gvisor = verify_inside_gvisor()

# Strict verification check - abort if not in gVisor
if not is_gvisor and {str(strict_verify).lower()}:
    print("❌ CRITICAL SECURITY ERROR: Not running in gVisor despite configuration!")
    print("GVISOR_SECURITY_VERIFICATION_FAILED")
    sys.exit(1)

# Then run the actual function
try:
    sys.path.append('{function_dir}')
    function_name = '{function_file}'.replace('.py', '')
    
    # Execute the actual function code
    if os.path.exists('{os.path.join("/app", function_file)}'):
        exec(open('{os.path.join("/app", function_file)}').read())
    else:
        print(f"ERROR: Could not find function file at {{'{os.path.join('/app', function_file)}'}}")
except Exception as e:
    print(f"ERROR executing function: {{str(e)}}")
""")
        
        try:
            # Run with gVisor and enforce the runtime
            result = subprocess.run(
                ["docker", "run", "--runtime=runsc", "--rm", 
                 "-v", f"{function_dir}:/app", 
                 f"python:3.9-{runtime}", "python", f"/app/{os.path.basename(wrapper_path)}"],
                capture_output=True,
                text=True
            )
            
            # Verify gVisor was actually used by checking for the marker in output
            if "RUNNING_IN_GVISOR: TRUE" not in result.stdout:
                print("❌ SECURITY ALERT: Function did NOT run in gVisor despite configuration!")
                if strict_verify:
                    print("⛔ Execution has been aborted for security reasons.")
                    result.returncode = 1  # Force error code
                    return False
                else:
                    print("⚠️ Function executed WITHOUT gVisor security - THIS IS UNSAFE")
            elif "GVISOR_SECURITY_VERIFICATION_FAILED" in result.stdout:
                print("❌ gVisor security verification failed inside container")
                return False
                
            # Save output to a file with timestamp
            job_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"function_output_{job_id}_{timestamp}.log"
            with open(log_filename, "w") as log_file:
                log_file.write(result.stdout)
                if result.stderr:
                    log_file.write("\n--- ERROR OUTPUT ---\n")
                    log_file.write(result.stderr)
            
            print("\n----- RESULT -----")
            if result.returncode == 0:
                print("✅ Function executed successfully with gVisor!")
                print(f"\nOutput:\n{result.stdout}")
                print(f"\nLogs saved to {log_filename}")
                return True
            else:
                print("❌ Function execution failed!")
                print(f"\nError:\n{result.stderr}")
                print(f"\nLogs saved to {log_filename}")
                return False
        finally:
            # Clean up the wrapper script
            try:
                os.unlink(wrapper_path)
            except:
                pass
            
    except Exception as e:
        print(f"Error running function: {str(e)}")
        return False

def create_example_function(path):
    """Create an example function at the given path"""
    try:
        with open(path, "w") as f:
            f.write("""
import os
import sys
import json

def main():
    import os
    import sys
    import json
    
    print("Function executed successfully!")
    print(f"Environment variables: {dict(os.environ)}")
    
    return {"status": "success", "message": "Hello from serverless function!"}
    
if __name__ == "__main__":
    result = main()
    print(json.dumps(result))
""")
        print(f"Example function created at {path}")
        return True
    except Exception as e:
        print(f"Error creating example function: {str(e)}")
        return False

def check_worker_status():
    """Check if the worker process is running"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*worker.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            pid = result.stdout.strip()
            print(f"✅ Worker process is running (PID: {pid})")
            return True
        else:
            print("❌ Worker process is not running")
            print("Start the worker with: python app/worker.py")
            return False
    except Exception as e:
        print(f"Error checking worker status: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit serverless functions to execution queue")
    parser.add_argument("--code", "-c", help="Path to the function code file")
    parser.add_argument("--create-example", "-e", help="Create an example function at the specified path")
    parser.add_argument("--runtime", "-r", default="python:3.9-slim", help="Container runtime to use (default: python:3.9-slim)")
    parser.add_argument("--engine", "-g", choices=["queue", "gvisor"], default="gvisor", 
                        help="Execution engine to use (queue or gvisor, default: gvisor)")
    parser.add_argument("--memory", "-m", default="128Mi", help="Memory limit (e.g. 128Mi, 256Mi)")
    parser.add_argument("--check-worker", action="store_true", help="Check if worker is running")
    parser.add_argument("--verify-gvisor", action="store_true", help="Verify gVisor installation")
    parser.add_argument("--verify-strict", action="store_true", help="Enforce strict gVisor verification")
    args = parser.parse_args()
    
    if args.verify_gvisor:
        if verify_gvisor():
            print("gVisor verification successful!")
            sys.exit(0)
        else:
            print("gVisor verification failed!")
            sys.exit(1)
    
    if args.check_worker:
        check_worker_status()
        sys.exit(0)
    
    if args.create_example:
        if create_example_function(args.create_example):
            print(f"Example function created at {args.create_example}")
            sys.exit(0)
        else:
            sys.exit(1)
    
    if not args.code:
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(args.code):
        print(f"Error: File {args.code} does not exist")
        sys.exit(1)
    
    # For gVisor execution, verify first
    if args.engine == "gvisor":
        print("Enforcing gVisor execution with strict verification...")
        if not verify_gvisor():
            print("❌ CRITICAL: gVisor is not properly configured!")
            print("Aborting execution for security reasons.")
            sys.exit(1)
            
        runtime_part = args.runtime.split(":")[1] if ":" in args.runtime else args.runtime
        if run_function_with_gvisor(args.code, runtime_part, strict_verify=args.verify_strict):
            sys.exit(0)
        else:
            print("❌ Function execution with gVisor failed")
            sys.exit(1)
    else: # queue
        # When queue is requested but gVisor is enforced
        if args.verify_strict:
            print("Strict security mode: even queue operations must use gVisor")
            gvisor_ok = verify_gvisor()
            if not gvisor_ok:
                print("❌ CRITICAL: gVisor not available for strict security mode")
                print("Execution aborted for security reasons")
                sys.exit(1)
                
        # Check if queue is available
        if redis_available and submit_job_to_queue(args.code, args.runtime, args.memory):
            sys.exit(0)
        else:
            print("❌ CRITICAL: Job queue unavailable and strict security requires gVisor")
            print("Execution aborted for security reasons")
            sys.exit(1) 