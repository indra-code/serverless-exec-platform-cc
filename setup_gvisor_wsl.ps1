# PowerShell script to set up gVisor in WSL
Write-Host "Setting up gVisor in WSL..."

# Install gVisor
Write-Host "Installing gVisor..."
try {
    # Download and install gVisor
    wsl -e bash -c "curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg"
    wsl -e bash -c "echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main' | sudo tee /etc/apt/sources.list.d/gvisor.list"
    wsl -e bash -c "sudo apt-get update && sudo apt-get install -y runsc"
    
    # Install Docker if not already installed
    wsl -e bash -c "sudo apt-get update && sudo apt-get install -y docker.io"
    
    # Add user to docker group
    wsl -e bash -c "sudo usermod -aG docker $USER"
    
    # Configure Docker to use gVisor
    wsl -e bash -c "sudo mkdir -p /etc/docker"
    wsl -e bash -c "echo '{\"runtimes\":{\"runsc\":{\"path\":\"/usr/bin/runsc\",\"runtimeArgs\":[]}}}' | sudo tee /etc/docker/daemon.json"
    
    # Start Docker service
    wsl -e bash -c "sudo service docker start"
    
    # Verify gVisor installation
    $gvisorVersion = wsl -e bash -c "runsc --version"
    if (-not $gvisorVersion) {
        Write-Error "Failed to verify gVisor installation."
        exit 1
    }
    
    Write-Host "gVisor installed successfully: $gvisorVersion"
    
    # Wait for Docker to be ready
    Start-Sleep -Seconds 5
    
    # Test gVisor with a simple container
    Write-Host "Testing gVisor with a simple container..."
    wsl -e bash -c "docker run --runtime=runsc hello-world"
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "gVisor test failed."
        exit 1
    }
    
    Write-Host "gVisor setup completed successfully!"
    
} catch {
    Write-Error "Error setting up gVisor: $_"
    exit 1
} 