#!/bin/bash
set -e

# setup_vm.sh
# Usage: ./setup_vm.sh
# Description: Installs Docker, Docker Compose, and starts the Investment Advisor services.
# Assumes: This script is run inside the project root directory on the VM (e.g. after git clone or scp).

echo "=== [1/4] Updating System Packages ==="
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

echo "=== [2/4] Installing Docker & Docker Compose ==="
# Add Docker's official GPG key:
sudo mkdir -p /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi

# Set up the repository:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Setup permissions
if ! groups $USER | grep &>/dev/null '\bdocker\b'; then
    echo "Adding user $USER to docker group..."
    sudo usermod -aG docker $USER
    # Activate group changes for current session (simplified) or creating a new login shell might differ
    # We will use 'newgrp' ideally, but in a script it only affects subshell.
    # We'll use sudo for docker commands in this script to ensure success.
fi

echo "=== [3/4] Verifying Environment ==="
# Check for .env file
if [ ! -f .env ]; then
    echo "WARNING: .env file not found in current directory!"
    echo "Please create or upload your .env file before checking services."
    # We don't exit here, to allow user to add it later and restart
fi

# Create data directory if not exists
mkdir -p data prompts logs

echo "=== [4/4] Starting Services with Docker Compose ==="
# Using sudo to ensure it works even if group change hasn't propagated
sudo docker compose up -d --build

echo "============================================"
echo "Deployment Complete!"
echo "Dashboard should be accessible at: http://<VM_EXTERNAL_IP>:8501"
echo "To view logs: sudo docker compose logs -f"
echo "To restart: sudo docker compose restart"
echo "============================================"
