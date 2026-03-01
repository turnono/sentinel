import time
import os
import json
import logging
import signal
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
LOG_DIR = Path("/tmp/openclaw")
CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
RESTART_FLAG = Path("/tmp/openclaw_restart_requested")

# Error Patterns to Trigger Failover
QUOTA_ERRORS = [
    '"status": 429',
    '"code": 429',
    'RESOURCE_EXHAUSTED',
    'Quota exceeded', 
    'token limit reached'
]

# Supported Models in Rotation Order
MODEL_ROTATION = [
    "google-gemini-cli/gemini-3-pro-preview",
    "ollama/gemma3"
    ]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ModelMonitor] %(message)s',
    datefmt='%H:%M:%S'
)

def get_latest_log_file():
    """Find the most recent OpenClaw log file."""
    try:
        logs = list(LOG_DIR.glob("openclaw-*.log"))
        if not logs:
            return None
        # Sort by modification time
        return max(logs, key=os.path.getmtime)
    except Exception:
        return None

def rotate_model():
    """Update openclaw.json to the next model in rotation."""
    if not CONFIG_PATH.exists():
        logging.error("Config file not found!")
        return False
        
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            
        current_model = config.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")
        logging.info(f"Current Model: {current_model}")
        
        # Find next model
        try:
            idx = MODEL_ROTATION.index(current_model)
            next_idx = (idx + 1) % len(MODEL_ROTATION)
        except ValueError:
            # If current unknown, default to first fallback
            next_idx = 0
            
        next_model = MODEL_ROTATION[next_idx]
        logging.info(f"🔄 Switching to Falback Model: {next_model}")
        
        # Update Config
        if "agents" not in config: config["agents"] = {}
        if "defaults" not in config["agents"]: config["agents"]["defaults"] = {}
        if "model" not in config["agents"]["defaults"]: config["agents"]["defaults"]["model"] = {}
        
        config["agents"]["defaults"]["model"]["primary"] = next_model
        
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
            
        return next_model
        
    except Exception as e:
        logging.error(f"Failed to rotate model: {e}")
        return False

def trigger_restart():
    """Signal Sentinel to restart OpenClaw."""
    logging.info("🚨 Triggering OpenClaw Restart...")
    RESTART_FLAG.touch()
    
    # Kill the OpenClaw Gateway process to force the restart loop
    try:
        # Find process named 'openclaw gateway' or arguments containing it
        # Using pkill is simplest for 'node' running 'openclaw' script
        # But 'openclaw' might be the process name if compiled binary
        # Let's try flexible pkill
        subprocess.run(["pkill", "-f", "openclaw gateway"], check=False)
        logging.info("Sent kill signal to OpenClaw Gateway.")
    except Exception as e:
        logging.error(f"Failed to kill process: {e}")

def monitor_logs():
    logging.info("Starting OpenClaw Model Monitor...")
    
    log_file = None
    while not log_file:
        log_file = get_latest_log_file()
        if not log_file:
            logging.info("Waiting for log file...")
            time.sleep(2)
            
    logging.info(f"Monitoring: {log_file}")
    
    f = open(log_file, "r")
    # Seek to end to monitor new logs only
    f.seek(0, os.SEEK_END)
    
    while True:
        line = f.readline()
        if not line:
            # Check if log rotated (file deleted/new one created)
            current_latest = get_latest_log_file()
            if current_latest and current_latest != log_file:
                logging.info(f"Log rotated to {current_latest}")
                f.close()
                log_file = current_latest
                f = open(log_file, "r")
                continue
                
            time.sleep(0.5)
            continue
            
        # Check for errors
        if any(err in line for err in QUOTA_ERRORS):
            logging.warning(f"⚠️ QUOTA ERROR DETECTED: {line.strip()}")
            new_model = rotate_model()
            if new_model:
                logging.info(f"✅ Failover successful. New model: {new_model}")
                trigger_restart()
                # Wait for restart before verifying log again to avoid loop
                time.sleep(10)
                # Re-open log file as process likely restarted
                f.close()
                log_file = None
                while not log_file:
                    log_file = get_latest_log_file()
                    time.sleep(1)
                f = open(log_file, "r")
                f.seek(0, os.SEEK_END) 

if __name__ == "__main__":
    try:
        monitor_logs()
    except KeyboardInterrupt:
        logging.info("Monitor stopped.")
