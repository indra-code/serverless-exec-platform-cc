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

def run_function_with_gvisor(code_path, runtime="slim"):
    """Run a function directly with gVisor"""
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
        
        # Run with gVisor
        result = subprocess.run(
            ["docker", "run", "--runtime=runsc", "--rm", 
             "-v", f"{function_dir}:/app", 
             f"python:3.9-{runtime}", "python", f"/app/{function_file}"],
            capture_output=True,
            text=True
        )
        
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
            print("✅ Function executed successfully!")
            print(f"\nOutput:\n{result.stdout}")
            print(f"\nLogs saved to {log_filename}")
            return True
        else:
            print("❌ Function execution failed!")
            print(f"\nError:\n{result.stderr}")
            print(f"\nLogs saved to {log_filename}")
            return False
            
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
    parser.add_argument("--engine", "-g", choices=["queue", "gvisor"], default="queue", 
                        help="Execution engine to use (queue or gvisor, default: queue)")
    parser.add_argument("--memory", "-m", default="128Mi", help="Memory limit for the function (default: 128Mi)")
    parser.add_argument("--check-worker", action="store_true", help="Check if the worker process is running")
    
    args = parser.parse_args()
    
    if args.check_worker:
        check_worker_status()
        sys.exit(0)
    
    if args.create_example:
        create_example_function(args.create_example)
        
    if args.code:
        if args.engine == "queue":
            if check_worker_status():
                submit_job_to_queue(args.code, args.runtime, args.memory)
            else:
                print("\nWould you like to continue submitting the job anyway? (y/n)")
                response = input().strip().lower()
                if response == 'y':
                    submit_job_to_queue(args.code, args.runtime, args.memory)
                else:
                    print("Job submission canceled")
        else:
            # For gVisor, extract just the tag if the full image is provided
            runtime_tag = args.runtime.split(":")[-1] if ":" in args.runtime else args.runtime
            run_function_with_gvisor(args.code, runtime_tag)
    elif not args.create_example and not args.check_worker:
        print("Please specify a function code file with --code or create an example with --create-example") 