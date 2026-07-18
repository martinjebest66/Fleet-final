#!/bin/bash
set -e

echo "=== Fleet Manager - Start ==="

# Start Nginx (frontend)
echo "[1/2] Starting Nginx..."
nginx

# Start FastAPI backend (includes Teltonika TCP on port 5027)
echo "[2/2] Starting FastAPI + Teltonika TCP..."
cd /app/backend
exec uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1
