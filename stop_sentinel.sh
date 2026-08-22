#!/bin/bash

echo "🛑 Stopping Sentinel and Claw Gateway services..."

# 1. Stop the gateway. The tree is mid-rename from openclaw to zeroclaw, so
#    resolve the CLI and match both spellings rather than assuming one.
echo "🦞 Stopping Claw Gateway..."
CLAW_CLI=""
for name in zeroclaw openclaw; do
  if command -v "$name" >/dev/null 2>&1; then
    CLAW_CLI="$name"
    break
  fi
done
if [ -n "$CLAW_CLI" ]; then
  "$CLAW_CLI" gateway stop || true
else
  echo "⚠️  No zeroclaw/openclaw CLI on PATH; falling back to signals."
fi
pkill -9 -f "(open|zero)claw gateway" || true
pkill -9 -f "ai\.(open|zero)claw\.gateway" || true

# 2. Stop Sentinel Components
echo "🧠 Stopping Sentinel Brain and Monitors..."
pkill -9 -f "src.api.server" || true
pkill -9 -f "scripts/monitoring/" || true
pkill -9 -f "context_monitor.py" || true
pkill -9 -f "model_monitor.py" || true

# 3. Port Cleanup (Extra Safety)
echo "🧹 Releasing ports 8765 and 18789..."
for PORT in 8765 18789; do
  PID=$(lsof -t -i:$PORT || true)
  if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null || true
  fi
done

echo "✅ All services stopped."
