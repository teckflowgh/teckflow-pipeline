#!/usr/bin/env bash
# Start alle pipeline services via PM2
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

pm2 delete all 2>/dev/null || true

pm2 start "uvicorn api.main:app --host 0.0.0.0 --port 8000" \
    --name "teckflow-api" \
    --cwd "$PROJECT_DIR"

pm2 start "node .next/standalone/server.js" \
    --name "teckflow-dashboard" \
    --cwd "$PROJECT_DIR/dashboard" \
    --env "PORT=3000,HOSTNAME=0.0.0.0"

pm2 save
pm2 list
echo ""
echo "API:       http://localhost:8000"
echo "Dashboard: http://localhost:3000"
