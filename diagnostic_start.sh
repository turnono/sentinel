#!/bin/bash

# Ensure logs directory exists
mkdir -p logs

LOG_FILE="logs/sentinel_resource_monitor.log"
echo "🔍 Starting Sentinel Diagnostic Monitor..."
echo "📄 Logging resource usage to $LOG_FILE"
echo "----------------------------------------" > "$LOG_FILE"
echo "START TIME: $(date)" >> "$LOG_FILE"

# Start Sentinel in the background
./start_sentinel.sh &
SENTINEL_PID=$!

echo "🛡️  Sentinel started with PID $SENTINEL_PID"

cleanup() {
    echo "🛑 Stopping Sentinel and Monitor..."
    kill $SENTINEL_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "📊 Monitoring system resources (Top 5 CPU/MEM)..."

while true; do
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] System Load:" >> "$LOG_FILE"
    uptime >> "$LOG_FILE"
    
    echo "[$TIMESTAMP] Top 5 Processes by CPU:" >> "$LOG_FILE"
    ps -Ao pid,ppid,%cpu,%mem,comm | sort -k3 -r | head -n 6 >> "$LOG_FILE"
    
    echo "[$TIMESTAMP] Top 5 Processes by MEM:" >> "$LOG_FILE"
    ps -Ao pid,ppid,%cpu,%mem,comm | sort -k4 -r | head -n 6 >> "$LOG_FILE"
    
    echo "----------------------------------------" >> "$LOG_FILE"
    
    # Check if Sentinel is still running
    if ! kill -0 $SENTINEL_PID 2>/dev/null; then
        echo "⚠️  Sentinel process exited unexpectedly!"
        echo "[$TIMESTAMP] Sentinel exited unexpectedly." >> "$LOG_FILE"
        break
    fi
    
    sleep 2
done
