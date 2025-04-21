import os
import sys
import json

def main():
    print("Starting loop function...")
    for i in range(10):
        print(i)

    return {"status": "success", "message": "Loop completed successfully", "values": list(range(10))}

if __name__ == "__main__":
    result = main()
    print(json.dumps(result))