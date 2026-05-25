#!/bin/bash
set -e

echo "Starting tinyproxy on :8888..."
tinyproxy -d &
sleep 1

echo "Starting AWG interface..."
wg-quick up /etc/awg/mkair.conf 2>&1 || echo "AWG failed (non-fatal)"

echo "=== Testing OpenRouter ==="
curl -sI --max-time 15 https://openrouter.ai/api/v1/models | head -5
echo ""

echo "=== Proxy ready on :8888 ==="
sleep infinity
