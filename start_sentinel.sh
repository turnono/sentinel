#!/bin/bash
set -e

echo "🛡️  Sentinel Hardened Launch Sequence Initiated..."

# 1. Enforce Configuration
echo "🔒 Locking OpenClaw configuration..."
python3 enforce_config.py

# 2. Kill Stale Servers (Robust)
echo "🧹 Cleaning up ports 8765 and 18789..."
for PORT in 8765 18789; do
  PID=$(lsof -t -i:$PORT || true)
  if [ -n "$PID" ]; then
    echo "   Killing old process on port $PORT (PID: $PID)"
    kill -9 $PID
  fi
done

# 3. Start Sentinel Server (Background)
echo "🧠 Starting Sentinel Brain..."
source .venv/bin/activate
python -u sentinel_server.py > /tmp/sentinel.log 2>&1 &
SERVER_PID=$!
echo "   PID: $SERVER_PID"

# Wait for server to be ready (simple sleep for now)
sleep 2

# 4. Start OpenClaw Gateway (Foreground)
echo "🦞 Releasing the Lobster..."
# Load nvm to ensure openclaw is in PATH
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
openclaw gateway

# Cleanup on exit
kill $SERVER_PID
