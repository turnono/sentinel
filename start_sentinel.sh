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
echo "   Sentinel Server PID: $SERVER_PID"

# 4. Start Context Monitor (Background)
echo "👀 Starting Context Monitor..."
python -u context_monitor.py > /tmp/context_monitor.log 2>&1 &
MONITOR_PID=$!
echo "   Context Monitor PID: $MONITOR_PID"

# 4a. Start Model Monitor (Background)
echo "🧠 Starting Model Monitor (Smart Fallback)..."
python -u model_monitor.py > /tmp/model_monitor.log 2>&1 &
MONITOR_MODEL_PID=$!
echo "   Model Monitor PID: $MONITOR_MODEL_PID"

# Wait for server to be ready (simple sleep for now)
sleep 2

# 5. Start OpenClaw Gateway (Loop for Auto-Restart)
echo "🦞 Releasing the Lobster..."
# Load nvm to ensure openclaw is in PATH
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use v22.14.0

OPENCLAW_PATH=$(which openclaw)
echo "   OpenClaw Path: $OPENCLAW_PATH"

while true; do
    openclaw gateway
    EXIT_CODE=$?
  
    if [ -f "/tmp/openclaw_restart_requested" ]; then
        echo "🔄 Restarting OpenClaw due to Smart Model Switch..."
        rm /tmp/openclaw_restart_requested
        sleep 2
        continue
    else
        break
    fi
done

# Cleanup on exit
echo "🛑 Stopping background services..."
kill $SERVER_PID 2>/dev/null || true
kill $MONITOR_PID 2>/dev/null || true
kill $MONITOR_MODEL_PID 2>/dev/null || true
