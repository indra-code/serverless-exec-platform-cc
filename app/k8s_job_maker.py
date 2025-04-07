from kubernetes import client, config
import uuid

config.load_kube_config() 

batch_v1 = client.BatchV1Api()
core_v1 = client.CoreV1Api()

def create_k8s_job(job_id: str, code_path: str):
    container_name = f"runner-{job_id}"
    job_name = f"job-{job_id[:8]}"
    volume_name = "code-volume"
    mount_path = "/app/code"

    container = client.V1Container(
        name=container_name,
        image="pes2ug22cs226/function-runner:latest",
        command=["python", "/app/code/handler.py"],
        working_dir="/app/code",
        volume_mounts=[client.V1VolumeMount(
            mount_path="/app/code",
            name=volume_name
        )]
    )

    volume = client.V1Volume(
        name=volume_name,
        host_path=client.V1HostPathVolumeSource(
            path=code_path,
            type="Directory"
        )
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"job": job_name}),
        spec=client.V1PodSpec(restart_policy="Never", containers=[container], volumes=[volume])
    )

    job_spec = client.V1JobSpec(template=template, backoff_limit=2)

    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name),
        spec=job_spec
    )

    api_response = batch_v1.create_namespaced_job(
        body=job,
        namespace="default"
    )
    print(f"Job {job_name} created")
    return api_response
