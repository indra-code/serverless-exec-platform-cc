from kubernetes import client, config
import uuid
import logging
import os
import time
import json
import redis

# Configure logging
logger = logging.getLogger("worker.k8s_job_maker")

# Load Kubernetes configuration
try:
    config.load_kube_config()
    batch_v1 = client.BatchV1Api()
    core_v1 = client.CoreV1Api()
    logger.info("Successfully connected to Kubernetes cluster")
except Exception as e:
    logger.error(f"Failed to connect to Kubernetes: {str(e)}")
    raise

def create_gvisor_job(job_id: str, code_path: str, memory: int = 128, timeout: int = 30, data: dict = None):
    """
    Create a Kubernetes job with gVisor isolation to run the function
    
    Args:
        job_id: Unique identifier for the job
        code_path: Path to the function code file (already mapped to Minikube paths)
        memory: Memory limit in Mi
        timeout: Timeout in seconds
        data: Additional data to pass to the function
    """
    logger.info(f"Creating gVisor-isolated job for {job_id}")
    
    # Call the internal function directly with gVisor runtime
    return _create_k8s_job_internal(
        job_id=job_id,
        code_path=code_path,
        runtime="gvisor",
        memory=memory,
        timeout=timeout,
        data=data
    )

def create_k8s_job(job_id: str, code_path: str, runtime: str = "default", memory: int = 128, timeout: int = 30, data: dict = None):
    """
    Create a Kubernetes job to run the function
    
    Args:
        job_id: Unique identifier for the job
        code_path: Path to the function code file (already mapped to Minikube paths)
        runtime: Runtime environment to use (default, gvisor)
        memory: Memory limit in Mi
        timeout: Timeout in seconds
        data: Additional data to pass to the function
    """
    # For gVisor runtime, delegate to the specialized function
    if runtime == "gvisor":
        logger.info("Delegating to gVisor-specific job creation")
        return _create_k8s_job_internal(
            job_id=job_id,
            code_path=code_path,
            runtime=runtime,
            memory=memory,
            timeout=timeout,
            data=data
        )
    else:
        return _create_k8s_job_internal(
            job_id=job_id,
            code_path=code_path,
            runtime=runtime,
            memory=memory,
            timeout=timeout,
            data=data
        )

# Rename the original implementation to _create_k8s_job_internal
def _create_k8s_job_internal(job_id: str, code_path: str, runtime: str = "default", memory: int = 128, timeout: int = 30, data: dict = None):
    try:
        # Don't check file existence since we're using a Minikube path that exists in the VM, not the host
        # Instead, log the path we're using
        logger.info(f"Using code path in Minikube: {code_path}")
        logger.info(f"Using runtime: {runtime}")
        logger.info(f"Memory limit: {memory}Mi, Timeout: {timeout}s")
            
        # Truncate job ID to 8 characters to avoid DNS issues
        short_job_id = job_id[:8] if len(job_id) > 8 else job_id
        container_name = f"runner-{short_job_id}"
        job_name = f"job-{short_job_id}"
        volume_name = "code-volume"
        mount_path = "/app/code"
        
        logger.info(f"Creating job {job_name} to run code at {code_path}")

        # Get the directory containing the code file
        code_dir = os.path.dirname(code_path)
        code_file = os.path.basename(code_path)
        
        # Setup command with data arguments if provided
        command = ["python", f"/app/code/{code_file}"]
        if data:
            # Convert data to command-line arguments
            for key, value in data.items():
                command.extend([f"--{key}", str(value)])
            logger.info(f"Added data parameters to command: {command}")
        
        # Create container configuration
        container = client.V1Container(
            name=container_name,
            image="python:3.9-slim",
            command=command,  # Use the command with arguments
            working_dir="/app/code",
            volume_mounts=[client.V1VolumeMount(
                mount_path="/app/code",
                name=volume_name
            )],
            resources=client.V1ResourceRequirements(
                requests={"memory": f"{memory}Mi", "cpu": "100m"},
                limits={"memory": f"{memory*2}Mi", "cpu": "500m"}  # Double the memory for the limit
            ),
            env=[
                client.V1EnvVar(name="FUNCTION_ID", value=job_id),
                client.V1EnvVar(name="PYTHONUNBUFFERED", value="1"),  # Ensure output is not buffered
                client.V1EnvVar(name="RUNTIME", value=runtime),  # Pass runtime to the container
                client.V1EnvVar(name="TIMEOUT", value=str(timeout))  # Pass timeout to the container
            ]
        )
        
        # Set security context based on runtime
        security_context = None
        if runtime == "gvisor":
            logger.info("Setting up gVisor-specific container configuration")
            
            # Add additional security context for gVisor
            security_context = client.V1SecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                run_as_group=1000,
                read_only_root_filesystem=True,
                allow_privilege_escalation=False,
                privileged=False,
                # Drop all capabilities
                capabilities=client.V1Capabilities(
                    drop=["ALL"],
                    add=["NET_BIND_SERVICE"]  # Only add the minimal capability needed
                ),
                # Enable seccomp profile
                seccomp_profile=client.V1SeccompProfile(
                    type="RuntimeDefault"
                )
            )
            
            # Add additional environment variables for gVisor
            container.env.append(client.V1EnvVar(name="GVISOR_ENABLED", value="true"))
            
            # Update container with security context
            container.security_context = security_context

            # Add readiness and liveness probes for better monitoring
            container.readiness_probe = client.V1Probe(
                http_get=None,
                exec=client.V1ExecAction(
                    command=["cat", "/tmp/ready"]
                ),
                initial_delay_seconds=1,
                period_seconds=5
            )
            
            # Add resource limits
            container.resources = client.V1ResourceRequirements(
                limits={
                    "memory": f"{memory}Mi", 
                    "cpu": "500m",
                    "ephemeral-storage": "1Gi"  # Limit disk usage
                },
                requests={
                    "memory": f"{int(memory * 0.8)}Mi",  # Request slightly less
                    "cpu": "100m",
                    "ephemeral-storage": "500Mi"
                }
            )

        # Create volume configuration to mount the code directory
        volume = client.V1Volume(
            name=volume_name,
            host_path=client.V1HostPathVolumeSource(
                path=code_dir,
                type="Directory"
            )
        )

        # Create pod template with specific annotations for gVisor if needed
        pod_metadata = client.V1ObjectMeta(
            labels={"job": job_name, "runtime": runtime.replace("+", "-")}
        )
        
        # Add runtime annotations for gVisor if needed
        if runtime == "gvisor":
            pod_metadata.annotations = {
                "io.kubernetes.cri.untrusted-workload": "true",  # Use gVisor for this workload
                "container.apparmor.security.beta.kubernetes.io/container": "runtime/default",
                "container.seccomp.security.alpha.kubernetes.io/container": "runtime/default"
            }

        template = client.V1PodTemplateSpec(
            metadata=pod_metadata,
            spec=client.V1PodSpec(
                restart_policy="Never", 
                containers=[container], 
                volumes=[volume]
            )
        )

        # Create job specification
        job_spec = client.V1JobSpec(
            template=template, 
            backoff_limit=2,
            ttl_seconds_after_finished=600  # Delete job after 10 minutes
        )

        # Create job object
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name, labels={"runtime": runtime.replace("+", "-")}),
            spec=job_spec
        )

        # Create the job in Kubernetes
        logger.info(f"Submitting job {job_name} to Kubernetes")
        api_response = batch_v1.create_namespaced_job(
            body=job,
            namespace="default"
        )
        
        # Wait for job completion and get logs
        logger.info(f"Waiting for job {job_name} to complete...")
        start_time = time.time()
        while True:
            job_status = batch_v1.read_namespaced_job_status(job_name, "default")
            if job_status.status.succeeded is not None:
                # Get pod name
                pods = core_v1.list_namespaced_pod(
                    namespace="default",
                    label_selector=f"job={job_name}"
                )
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    # Get pod logs
                    logs = core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace="default"
                    )
                    # Store logs in Redis
                    r = redis.Redis(host='localhost', port=6379, db=0)
                    
                    # Create a more detailed log structure for gVisor jobs
                    log_data = {
                        'job_id': job_id,
                        'logs': logs,
                        'runtime': runtime,
                        'memory': memory,
                        'timeout': timeout,
                        'execution_time': time.time() - start_time,  # Calculate execution time
                        'status': 'completed'
                    }
                    
                    # Add the job log to Redis
                    r.lpush('job_logs', json.dumps(log_data))
                    
                    # If this is a gVisor job, also record detailed metrics
                    if runtime == "gvisor":
                        # Record gVisor-specific metrics
                        gvisor_metrics = {
                            'job_id': job_id,
                            'runtime': runtime,
                            'memory': memory,
                            'timeout': timeout,
                            'execution_time': time.time() - start_time,
                            'timestamp': time.time(),
                            'status': 'completed'
                        }
                        
                        # Store gVisor metrics in a separate list for analytics
                        r.lpush('gvisor_metrics', json.dumps(gvisor_metrics))
                        logger.info(f"Recorded gVisor metrics for job {job_id}")
                break
            elif job_status.status.failed is not None:
                logger.error(f"Job {job_name} failed")
                break
            time.sleep(1)
        
        logger.info(f"Job {job_name} completed successfully")
        return api_response
        
    except Exception as e:
        logger.error(f"Failed to create Kubernetes job: {str(e)}")
        raise
