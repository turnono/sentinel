#!/bin/bash

echo "🛑 Stopping Sentinel and OpenClaw Gateway services..."

# 1. Stop OpenClaw
echo "🦞 Stopping OpenClaw Gateway..."
openclaw gateway stop || true
pkill -9 -f "openclaw gateway" || true
pkill -9 -f "ai.openclaw.gateway" || true

# 2. Stop Sentinel Components
echo "🧠 Stopping Sentinel Brain and Monitors..."
pkill -9 -f "src.api.server" || true
pkill -9 -f "scripts/monitoring/context.py" || true
pkill -9 -f "scripts/monitoring/failover.py" || true

# 3. Port Cleanup (Extra Safety)
echo "🧹 Releasing ports 8765 and 18789..."
for PORT in 8765 18789; do
  PID=$(lsof -t -i:$PORT || true)
  if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null || true
  fi
done

echo "✅ All services stopped."
