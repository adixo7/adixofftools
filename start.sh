#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[start] Starting Likes API (Python) on port 5001..."
cd "$ROOT_DIR/like_api" && python wsgi.py &
LIKES_PID=$!

echo "[start] Starting main server (Node.js) on port 5000..."
cd "$ROOT_DIR" && node server.js &
NODE_PID=$!

cleanup() {
  echo "[stop] Shutting down..."
  kill $LIKES_PID $NODE_PID 2>/dev/null
  wait
}
trap cleanup SIGTERM SIGINT

wait $NODE_PID
