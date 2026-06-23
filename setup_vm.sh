#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "==========================================="
echo "   Mindi Bot VM Setup (OCI Ubuntu)         "
echo "==========================================="

# 1. Update package lists
echo "[1/7] Updating package lists..."
sudo apt-get update -y

# 2. Install prerequisites
echo "[2/7] Installing prerequisites..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    iptables-persistent

# 3. Add Docker's official GPG key and repository
echo "[3/7] Setting up Docker repository..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Install Docker Engine
echo "[4/7] Installing Docker..."
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 5. Start and enable Docker service
echo "[5/7] Configuring Docker service..."
sudo systemctl enable docker
sudo systemctl start docker

# 6. Add current user to docker group
echo "[6/7] Adding user '$USER' to the docker group..."
sudo usermod -aG docker $USER

# 7. Configure firewall for OCI/AWS (Crucial Step)
# OCI Ubuntu VMs block all ports except 22 by default at the OS level.
echo "[7/7] Configuring VM firewall to allow port 8000 (FastAPI)..."
if command -v iptables &> /dev/null; then
    # Insert rule to allow incoming TCP traffic on port 8000
    # OCI Ubuntu instances usually have a reject rule at line 6 or later.
    # We insert our accept rule at index 6 to ensure it runs before any reject rules.
    # If index 6 does not exist (e.g. on AWS EC2 standard AMIs), fallback to index 1.
    sudo iptables -I INPUT 6 -p tcp --dport 8000 -m state --state NEW,ESTABLISHED -j ACCEPT 2>/dev/null || \
    sudo iptables -I INPUT 1 -p tcp --dport 8000 -m state --state NEW,ESTABLISHED -j ACCEPT
    
    # Save rules so they persist across reboots
    if [ -f /etc/iptables/rules.v4 ]; then
        sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null
        echo "Saved iptables rules to /etc/iptables/rules.v4"
    fi
fi

# Check UFW (if enabled)
if command -v ufw &> /dev/null && sudo ufw status | grep -q "active"; then
    sudo ufw allow 8000/tcp
    echo "Configured UFW to allow port 8000/tcp"
fi

echo "==========================================="
echo "           Setup Complete!                 "
echo "==========================================="
echo "IMPORTANT: Please LOG OUT of your SSH session and LOG BACK IN"
echo "for the docker group changes to take effect."
echo "==========================================="
