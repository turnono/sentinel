#!/bin/bash



echo "🛡️  Sentinel Hardened Launch Sequence Initiated..."

# Load env vars early for Python scripts
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
  echo "   Loaded .env variables"
  echo "   Sentinel Dashboard: http://${SENTINEL_HOST}:8765/dashboard/"
  echo "   ZeroClaw Gateway:   http://<YOUR_IP>:18789/chat?session=main (Password Protected)"
fi

# Set PYTHONPATH to include the project root for modular imports
export PYTHONPATH=$PYTHONPATH:.

# 1. Enforce Configuration
echo "🔒 Locking ZeroClaw configuration..."
python3 enforce_config.py

# 2. Kill Stale Servers (Robust)
echo "🧹 Cleaning up ports 8765 and 18790..."
for PORT in 8765 18790; do
  PID=$(lsof -t -i:$PORT || true)
  if [ -n "$PID" ]; then
    echo "   Killing old process on port $PORT (PID: $PID)"
    kill -9 $PID
  fi
done

echo "   Aggressively killing any lingering monitors..."
# pkill -9 -f "openclaw gateway" || true
# pkill -9 -f "ai.openclaw.gateway" || true
pkill -9 -f "scripts/monitoring/" || true
# Wait a moment for ports to actually free up
sleep 2

# ... [Trimming steps 3 and 4 which stay the same] ...

echo "✅ Sentinel Security Layers are active. (ZeroClaw Gateway Managed Separately)"


# Cleanup on exit
echo "🛑 Stopping background services..."
kill $SERVER_PID 2>/dev/null || true
kill $MONITOR_PID 2>/dev/null || true
kill $MONITOR_MODEL_PID 2>/dev/null || true
kill $MONITOR_HEAL_PID 2>/dev/null || true
