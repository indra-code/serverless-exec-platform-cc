#!/bin/bash
# Script to execute a function by file path using the CLI tool

# Check if a file path is provided
if [ -z "$1" ]; then
    echo "Error: Please provide a file path to the function code."
    echo "Usage: $0 <file_path>"
    exit 1
fi

FILE_PATH="$1"

# Check if the file exists
if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File not found: $FILE_PATH"
    exit 1
fi

# Generate a unique request ID
REQUEST_ID=$(date +%s%N | md5sum | head -c 8)

echo "┌──────────────────────────────────────────────────────────"
echo "│ Serverless Function Execution API"
echo "│ Request ID: $REQUEST_ID"
echo "│ File: $FILE_PATH"
echo "└──────────────────────────────────────────────────────────"

echo "Step 1: Submitting function to execution queue..."

# Execute the function using the CLI tool
./run_function.py --code "$FILE_PATH"

# Get the job ID from the most recent log file
LOG_FILE=$(ls -t function_job_*.log | head -n 1)
JOB_ID=$(grep "Job submitted to queue" "$LOG_FILE" | awk '{print $4}')

echo "Step 2: Function submitted with Job ID: $JOB_ID"
echo "Step 3: Waiting for execution results..."

# Wait a moment for execution
sleep 2

# Display worker log for this job
echo "Step 4: Execution output:"
echo "┌──────────────────────────────────────────────────────────"
grep -a "$JOB_ID" worker.log
echo "└──────────────────────────────────────────────────────────"

echo "API Response:"
echo "{\"status\":\"success\",\"message\":\"Function submitted and executed\",\"job_id\":\"$JOB_ID\",\"log_file\":\"$LOG_FILE\"}" 