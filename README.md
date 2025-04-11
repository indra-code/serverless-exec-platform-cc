# Serverless Function Platform

A serverless execution platform that supports both Docker and gVisor runtimes, with automatic platform detection for WSL and Linux environments.

## Features

- Docker-based function execution
- gVisor-based function execution (if available)
- Function warm-up mechanism
- Container pooling
- Metrics collection
- Error handling
- Automatic platform detection (WSL/Linux)

## Prerequisites

### For WSL (Windows Subsystem for Linux)
1. Install WSL 2:
   ```powershell
   wsl --install
   wsl --set-default-version 2
   ```

2. Install Ubuntu or your preferred Linux distribution from Microsoft Store

3. Install Docker Desktop for Windows with WSL 2 backend:
   - Download from [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Enable WSL 2 backend in settings

### For Linux
1. Install Docker:
   ```bash
   # For Ubuntu/Debian
   sudo apt update
   sudo apt install -y docker.io

   # For Arch Linux
   sudo pacman -S docker
   ```

2. Start and enable Docker service:
   ```bash
   sudo systemctl enable --now docker
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd serverless-exec-platform-cc
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   
   # On Windows/WSL
   .\venv\Scripts\activate
   
   # On Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Setup gVisor

### For WSL
1. Open PowerShell as administrator and run:
   ```powershell
   .\setup_gvisor_wsl.ps1
   ```

2. Restart WSL:
   ```powershell
   wsl --shutdown
   ```

### For Linux
1. Run the setup script:
   ```bash
   chmod +x setup_gvisor_arch.sh
   sudo ./setup_gvisor_arch.sh
   ```

## Running the Application

1. Start the FastAPI server:
   ```bash
   python -m api.app.main
   ```

2. The server will be available at `http://localhost:8000`

3. Access the API documentation at `http://localhost:8000/docs`

## API Usage

### Creating a Function

```bash
curl -X POST "http://localhost:8000/functions" \
     -H "Content-Type: application/json" \
     -d '{
           "name": "hello-world",
           "description": "A simple hello world function",
           "code": "print(\"Hello, World!\")",
           "runtime": "python3"
         }'
```

### Executing a Function

```bash
curl -X POST "http://localhost:8000/functions/{function_id}/execute" \
     -H "Content-Type: application/json" \
     -d '{
           "input": {}
         }'
```

### Checking Function Status

```bash
curl "http://localhost:8000/functions/{function_id}"
```

## Platform Detection

The application automatically detects whether it's running in WSL or Linux and configures itself accordingly. You can check the current platform by visiting the root endpoint:

```bash
curl http://localhost:8000/
```

The response will include the platform information and available runtimes.

## Troubleshooting

### Common Issues

1. **Docker not running**
   - WSL: Ensure Docker Desktop is running
   - Linux: Run `sudo systemctl start docker`

2. **gVisor not available**
   - Check if gVisor is installed correctly
   - Verify Docker is configured to use gVisor runtime
   - Check logs for specific error messages

3. **Permission issues**
   - Ensure your user is in the docker group:
     ```bash
     sudo usermod -aG docker $USER
     ```
   - Log out and log back in for changes to take effect

### Logs

Logs are available in the console where the application is running. For more detailed logging, you can modify the logging configuration in `api/app/main.py`.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 