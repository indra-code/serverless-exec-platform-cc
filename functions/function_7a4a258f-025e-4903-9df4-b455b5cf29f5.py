import os
import sys
import json

def main():
    print("Function executed successfully!")
    print(f"Environment variables: {dict(os.environ)}")
    
    return {"status": "success", "message": "Hello from serverless function!"}
    
if __name__ == "__main__":
    result = main()
    print(json.dumps(result))
