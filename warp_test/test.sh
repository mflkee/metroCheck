#!/bin/bash
set -e

echo "=== WARP Connectivity Test ==="

# 1. Start AWG container
echo "[1/3] Starting AWG container..."
docker compose -f "$(dirname "$0")/docker-compose.test.yml" up -d

# 2. Wait for interface
echo "[2/3] Waiting for AWG interface..."
sleep 5

# 3. Test OpenRouter
echo "[3/3] Testing OpenRouter..."
docker exec mkair_warp_test curl -sI https://openrouter.ai/api/v1/models

echo ""
echo "=== Test complete ==="
echo "If you see HTTP/2 200 above → WARP works"
echo "If not → check awg.conf or network"
