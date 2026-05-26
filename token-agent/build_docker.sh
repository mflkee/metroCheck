#!/bin/bash
# Build token-agent.exe for Windows using Docker + PyInstaller
set -e

IMAGE="cdrx/pyinstaller-windows:latest"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SRC_DIR/dist"

echo "Pulling PyInstaller Windows image..."
docker pull "$IMAGE" 2>/dev/null || true

echo "Building token-agent.exe..."
docker run --rm \
  -v "$SRC_DIR:/src" \
  -w /src \
  "$IMAGE" \
  "pip install -r /src/requirements.txt && pyinstaller --onefile --console --name token-agent --hidden-import=uvicorn.loops.asyncio --hidden-import=uvicorn.loops.auto /src/main.py"

mkdir -p "$OUTPUT_DIR"
if [ -f "$SRC_DIR/token-agent.exe" ]; then
  mv "$SRC_DIR/token-agent.exe" "$OUTPUT_DIR/"
fi
if [ -f "$SRC_DIR/dist/token-agent.exe" ]; then
  mv "$SRC_DIR/dist/token-agent.exe" "$OUTPUT_DIR/"
fi

echo ""
echo "=== Build complete ==="
ls -lh "$OUTPUT_DIR/token-agent.exe" 2>/dev/null && echo "Executable: $OUTPUT_DIR/token-agent.exe" || echo "Build failed"
