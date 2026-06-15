#!/bin/bash
set -e

echo "==========================================="
echo "   Mindi Bot Deployment Automator          "
echo "==========================================="

# 1. Check if .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file is missing!"
    echo "Please create a .env file based on .env.example before deploying."
    exit 1
fi

# 2. Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Please run setup_vm.sh first."
    exit 1
fi

# 3. Run docker compose build and run
echo "Building and starting Docker containers..."
docker compose up -d --build

# 4. Wait for FastAPI to spin up and check health
echo "Waiting for Mindi Bot service to start (checking health)..."
max_attempts=30
attempt=1
success=false

while [ $attempt -le $max_attempts ]; do
    # Attempt to fetch health and parse using python or grep
    HEALTH_RESP=$(curl -s --max-time 2 http://localhost:8000/health || true)
    if echo "$HEALTH_RESP" | grep -q '"status":"online"'; then
        success=true
        break
    fi
    echo -n "."
    sleep 2
    attempt=$((attempt+1))
done
echo ""

if [ "$success" = true ]; then
    echo "==========================================="
    echo "   Bot Deployed and Running Successfully!  "
    echo "==========================================="
    echo "Service Status:"
    echo "$HEALTH_RESP"
    echo ""
    echo "API endpoints available at: http://localhost:8000"
    echo "Check container status:    docker compose ps"
    echo "Check application logs:    docker compose logs -f web"
    echo "==========================================="
else
    echo "==========================================="
    echo "ERROR: Bot healthcheck failed to respond within time."
    echo "Printing container status and logs for diagnostics:"
    echo "==========================================="
    docker compose ps
    echo "--- Container Logs ---"
    docker compose logs --tail=50 web
    exit 1
fi
