#!/bin/bash



echo "🛡️  Sentinel Hardened Launch Sequence Initiated..."

# Load env vars early for Python scripts
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
  echo "   Loaded .env variables"
  echo "   Sentinel Dashboard: http://${SENTINEL_HOST}:8765/dashboard/"
  echo "   OpenClaw Gateway:   http://<YOUR_IP>:18789/chat?session=main (Password Protected)"
fi

# Set PYTHONPATH to include the project root for modular imports
export PYTHONPATH=$PYTHONPATH:.

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

echo "   Aggressively killing any lingering OpenClaw instances..."
pkill -9 -f "openclaw gateway" || true
pkill -9 -f "ai.openclaw.gateway" || true
# Wait a moment for ports to actually free up
sleep 2

# 3. Start Sentinel Server (Background)
echo "🧠 Starting Sentinel Brain..."
source .venv/bin/activate
python -u -m src.api.server > /tmp/sentinel.log 2>&1 &
SERVER_PID=$!
echo "   Sentinel Server PID: $SERVER_PID"

# 4. Start Context Monitor (Background)
echo "👀 Starting Context Monitor..."
python -u scripts/monitoring/context.py > /tmp/context_monitor.log 2>&1 &
MONITOR_PID=$!
echo "   Context Monitor PID: $MONITOR_PID"

# 4a. Start Model Monitor (Background)
echo "🧠 Starting Model Monitor (Smart Fallback)..."
python -u scripts/monitoring/failover.py > /tmp/model_monitor.log 2>&1 &
MONITOR_MODEL_PID=$!
echo "   Model Monitor PID: $MONITOR_MODEL_PID"

# Wait for server to be ready (simple sleep for now)
sleep 2

# 5. Start OpenClaw Gateway (Loop for Auto-Restart)
echo "🦞 Releasing the Lobster..."
# Load nvm to ensure openclaw is in PATH
# Load nvm if available, but dont fail if not found
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
    nvm use v22.14.0 || echo "nvm use failed, proceeding with system node"
else
    echo "nvm not found, proceeding with system node/openclaw"
fi

OPENCLAW_PATH=$(which openclaw)
if [ -z "$OPENCLAW_PATH" ]; then
    # Fallback to common nvm location if which failed
    OPENCLAW_PATH="$HOME/.nvm/versions/node/v22.14.0/bin/openclaw"
fi

# Final check
if [ ! -x "$OPENCLAW_PATH" ]; then
    echo "❌ Error: openclaw executable not found at $OPENCLAW_PATH"
    echo "   Please ensure OpenClaw is installed and in PATH."
    # Try one last ditch effort with system node
    OPENCLAW_PATH="openclaw" 
fi

echo "   OpenClaw Path: $OPENCLAW_PATH"



# Managed Persistence Configuration (Exponential Backoff)
BACKOFF_SEC=2
MAX_BACKOFF_SEC=60
RESET_WINDOW_SEC=300
LAST_RESTART_TIME=$(date +%s)

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - LAST_RESTART_TIME))

    # Reset backoff if service was stable for a while
    if [ $ELAPSED -gt $RESET_WINDOW_SEC ]; then
        BACKOFF_SEC=2
    fi

    echo "🦞 Starting OpenClaw Gateway (Managed Persistence)..."
    echo "   Priority: Low (nice +10) | Backoff Potential: ${BACKOFF_SEC}s"
    
    # Run with lower priority to prevent system freeze
    # Log BOTH stdout and stderr to file
    LOG_FILE="$(pwd)/logs/openclaw_gateway.log"
    nice -n 10 "$OPENCLAW_PATH" gateway run --password "${OPENCLAW_PASSWORD}" > "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    LAST_RESTART_TIME=$(date +%s)
  
    if [ -f "/tmp/openclaw_restart_requested" ]; then
        echo "🔄 Restarting OpenClaw due to Smart Model Switch..."
        rm /tmp/openclaw_restart_requested
        BACKOFF_SEC=2 # Reset backoff on intentional restart
        sleep 2
        continue
    fi

    echo "⚠️  OpenClaw Gateway crashed (Code: $EXIT_CODE). Backing off for ${BACKOFF_SEC}s..."
    sleep $BACKOFF_SEC
    
    # Exponential Backoff for next time (cap at 60s)
    BACKOFF_SEC=$((BACKOFF_SEC * 2))
    if [ $BACKOFF_SEC -gt $MAX_BACKOFF_SEC ]; then
        BACKOFF_SEC=$MAX_BACKOFF_SEC
    fi
done

# Cleanup on exit
echo "🛑 Stopping background services..."
kill $SERVER_PID 2>/dev/null || true
kill $MONITOR_PID 2>/dev/null || true
kill $MONITOR_MODEL_PID 2>/dev/null || true
