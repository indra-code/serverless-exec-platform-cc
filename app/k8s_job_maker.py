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

def create_k8s_job(job_id: str, code_path: str):
    """
    Create a Kubernetes job to run the function
    
    Args:
        job_id: Unique identifier for the job
        code_path: Path to the function code file (already mapped to Minikube paths)
    """
    try:
        # Don't check file existence since we're using a Minikube path that exists in the VM, not the host
        # Instead, log the path we're using
        logger.info(f"Using code path in Minikube: {code_path}")
            
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
        
        # Create container configuration
        container = client.V1Container(
            name=container_name,
            image="python:3.9-slim",
            command=["python", f"/app/code/{code_file}"],  # Use the correct filename
            working_dir="/app/code",
            volume_mounts=[client.V1VolumeMount(
                mount_path="/app/code",
                name=volume_name
            )],
            resources=client.V1ResourceRequirements(
                requests={"memory": "128Mi", "cpu": "100m"},
                limits={"memory": "256Mi", "cpu": "500m"}
            ),
            env=[
                client.V1EnvVar(name="FUNCTION_ID", value=job_id),
                client.V1EnvVar(name="PYTHONUNBUFFERED", value="1")  # Ensure output is not buffered
            ]
        )

        # Create volume configuration to mount the code directory
        volume = client.V1Volume(
            name=volume_name,
            host_path=client.V1HostPathVolumeSource(
                path=code_dir,
                type="Directory"
            )
        )

        # Create pod template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"job": job_name}),
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
            metadata=client.V1ObjectMeta(name=job_name),
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
                    r.lpush('job_logs', json.dumps({
                        'job_id': job_id,
                        'logs': logs
                    }))
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
