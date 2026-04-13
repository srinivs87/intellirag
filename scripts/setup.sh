#!/bin/bash
# IntelliRAG setup script

set -e

echo "IntelliRAG — On-premise RAG Platform"
echo "-------------------------------------"

# Check Docker
if ! command -v docker &> /dev/null; then
  echo "ERROR: Docker not found. Install Docker Desktop first."
  exit 1
fi

echo "Docker version: $(docker --version)"

# Copy .env if not exists
if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

# Step 1: Build and start
echo ""
echo "Step 1/3: Starting all services (this takes 3-5 min on first run)..."
docker compose up -d --build

# Step 2: Wait for backend
echo ""
echo "Step 2/3: Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "Backend is ready."
    break
  fi
  echo "  waiting... ($i/30)"
  sleep 5
done

# Step 3: Wait for models
echo ""
echo "Step 3/3: Waiting for LLM models to download..."
for i in $(seq 1 60); do
  status=$(docker inspect --format='{{.State.Status}}' intellirag-model-init 2>/dev/null || echo "missing")
  if [ "$status" = "exited" ]; then
    echo "Models ready."
    break
  fi
  echo "  downloading models... ($i/60)"
  sleep 5
done

# Summary
echo ""
echo "====================================="
echo "IntelliRAG is ready!"
echo "====================================="
echo ""
echo "  Admin Panel  ->  http://localhost:3000"
echo "  API Docs     ->  http://localhost:8000/docs"
echo "  Qdrant       ->  http://localhost:6333/dashboard"
echo "  MinIO        ->  http://localhost:9001"
echo ""
echo "Embed snippet:"
echo '  <script src="http://localhost:8000/widget.js" data-tenant="general"></script>'
echo ""
