#!/bin/bash

# Sentinel: Sovereign Security Guardian
# Optimized for ZeroClaw Integration & Privacy

# 1. Environment & Initialization
echo "🛡️  Initializing Sentinel Security Layers..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# 2. Port Check & Cleanup
for PORT in 8765 18790; do
  PID=$(lsof -ti :$PORT)
  if [ ! -z "$PID" ]; then
    echo "⚠️  Port $PORT occupied by PID $PID. Clearing..."
    kill -9 $PID
  fi
done

echo "   Aggressively killing any lingering instances..."
pkill -9 -f "scripts/monitoring/" || true
pkill -9 -f "sentinel_server.py" || true
pkill -9 -f "context_monitor.py" || true
pkill -9 -f "model_monitor.py" || true
sleep 2

# 3. Start Sentinel Server (Brain)
echo "🧠 Starting Sentinel Brain..."
source .venv/bin/activate
python -u sentinel_server.py > /tmp/sentinel.log 2>&1 &
SERVER_PID=$!

# 4. Start New Upstream Monitors
echo "👀 Starting Context & Model Monitors..."
python -u context_monitor.py > /tmp/context_monitor.log 2>&1 &
MONITOR_PID=$!
python -u model_monitor.py > /tmp/model_monitor.log 2>&1 &
MONITOR_MODEL_PID=$!

# 5. Start Autonomic Healing (Phase 7 upgrade)
echo "🩹 Starting Autonomic Healing Monitor..."
python -u scripts/monitoring/autonomic.py > /tmp/sentinel_healing.log 2>&1 &
MONITOR_HEAL_PID=$!

echo "✅ Sentinel Security Layers are active."
echo "   (ZeroClaw Gateway is managed as a background service via launchd)"

# Cleanup on exit
trap 'kill $SERVER_PID $MONITOR_PID $MONITOR_MODEL_PID $MONITOR_HEAL_PID 2>/dev/null' EXIT

# Keep script alive to maintain background monitors
wait
