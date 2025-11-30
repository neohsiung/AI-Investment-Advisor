#!/bin/bash

# Ensure .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your credentials."
    exit 1
fi

echo "Starting Investment Advisor Platform..."

# Workaround for non-ASCII path issues in Docker Desktop
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

echo "1. Building and starting containers..."
if ! docker compose up -d --build; then
    echo "Error: Docker deployment failed!"
    exit 1
fi

echo ""
echo "=== Deployment Successful ==="
echo "Dashboard is running at: http://localhost:8501"
echo "Scheduler is running in background."
echo ""
echo "To stop the services, run: docker compose down"
echo "To view logs, run: docker compose logs -f"
