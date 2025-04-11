#!/bin/bash

echo "Setting up gVisor on Arch Linux..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Install required packages
echo "Installing required packages..."
pacman -S --noconfirm docker runsc

# Start and enable Docker service
echo "Starting Docker service..."
systemctl enable --now docker

# Configure Docker to use gVisor
echo "Configuring Docker to use gVisor..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << EOF
{
    "runtimes": {
        "runsc": {
            "path": "/usr/bin/runsc"
        }
    }
}
EOF

# Restart Docker to apply changes
echo "Restarting Docker service..."
systemctl restart docker

# Verify gVisor installation
echo "Verifying gVisor installation..."
runsc --version

if [ $? -ne 0 ]; then
    echo "Failed to verify gVisor installation."
    exit 1
fi

# Test gVisor with a simple container
echo "Testing gVisor with a simple container..."
docker run --runtime=runsc hello-world

if [ $? -ne 0 ]; then
    echo "gVisor test failed."
    exit 1
fi

echo "gVisor setup completed successfully!" 