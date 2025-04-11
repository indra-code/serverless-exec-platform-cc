import redis
import json
import time
from k8s_job_maker import create_k8s_job
r = redis.Redis(host='localhost', port=6379, db=0)

while True:
    job = r.rpop('job_queue')
    if job:
        job = json.loads(job)
        print(f"Got job: {job['job_id']}")
        job_id = job['job_id']
        code_path = job['code_path']
        create_k8s_job(job_id, code_path)
        print(f"Job {job_id} created")
    else:
        print("No job in queue")
        time.sleep(1)

