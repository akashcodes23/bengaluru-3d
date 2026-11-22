#!/usr/bin/env bash
set -euo pipefail

echo "=== Bengaluru 3D Build Pipeline ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

PYTHON="${ROOT_DIR}/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
  PYTHON="python3"
fi

echo "1. Checking python environment..."
"$PYTHON" --version

echo "2. Building terrain chunks..."
"$PYTHON" data/build_terrain.py

echo "3. Building landmarks dataset..."
"$PYTHON" data/build_landmarks.py

echo "4. Building building footprints & fusing heights..."
"$PYTHON" data/build_data.py

echo "5. Building metro transit network (OSM relations)..."
"$PYTHON" data/build_osm_metro.py

echo "6. Preparing hosting bundle and data files..."
"$PYTHON" data/prepare_hosting.py

echo "=== Build completed successfully! ==="
