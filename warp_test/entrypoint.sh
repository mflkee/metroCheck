#!/bin/bash
set -e

# Start tinyproxy
echo "Starting tinyproxy on :8888..."
tinyproxy -d &
sleep 1

# Bring up AWG interfaces using host tools
for f in /config/*.conf; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .conf)
    echo "Starting AWG interface: $name"
    wg-quick up "$f" 2>&1 || true
done

# Test connectivity
echo "=== Testing OpenRouter ==="
curl -sI --max-time 15 https://openrouter.ai/api/v1/models | head -5
echo ""

echo "=== WARP proxy ready on :8888 ==="
sleep infinity
