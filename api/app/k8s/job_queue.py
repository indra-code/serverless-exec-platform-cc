import redis
import json
r = redis.Redis(host='localhost', port=6379, db=0)
def add_to_queue(job_id: str, code_path: str):
    j  = {
        "job_id": job_id,
        "code_path": code_path
    }
    json_data = json.dumps(j)
    r.lpush('job_queue', json_data)



