# PowerShell script to set up gVisor in WSL
Write-Host "Setting up gVisor in WSL..."

# Check if WSL is installed
$wslInstalled = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wslInstalled) {
    Write-Error "WSL is not installed. Please install WSL first."
    exit 1
}

# Check if WSL 2 is the default version
$wslVersion = wsl --version
if (-not $wslVersion.Contains("WSL 2")) {
    Write-Error "WSL 2 is not the default version. Please set WSL 2 as the default version."
    exit 1
}

# Install gVisor
Write-Host "Installing gVisor..."
try {
    # Download and install gVisor
    wsl -e bash -c "curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg"
    wsl -e bash -c "echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main' | sudo tee /etc/apt/sources.list.d/gvisor.list"
    wsl -e bash -c "sudo apt-get update && sudo apt-get install -y runsc"
    
    # Configure Docker to use gVisor
    wsl -e bash -c "sudo mkdir -p /etc/docker"
    wsl -e bash -c "echo '{\"runtimes\": {\"runsc\": {\"path\": \"/usr/local/bin/runsc\"}}}' | sudo tee /etc/docker/daemon.json"
    wsl -e bash -c "sudo systemctl restart docker"
    
    # Verify gVisor installation
    $gvisorVersion = wsl -e bash -c "/usr/local/bin/runsc --version"
    if (-not $gvisorVersion) {
        Write-Error "Failed to verify gVisor installation."
        exit 1
    }
    
    Write-Host "gVisor installed successfully: $gvisorVersion"
    
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