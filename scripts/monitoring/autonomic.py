import time
import os
import subprocess
import logging
import re
from pathlib import Path

# Configuration
SENTINEL_DIR = Path.home() / "sentinel"
GATEWAY_LOG = SENTINEL_DIR / "logs" / "openclaw_gateway.log"
HEALING_LOG = Path.home() / "taajirah_systems" / "JOURNAL" / "SENTINEL_HEALING.log"
ENFORCE_SCRIPT = SENTINEL_DIR / "enforce_config.py"

# Healing Registry (Pattern -> Action Description)
HEALING_PATTERNS = {
    r"unauthorized: gateway password missing": "Authentication drift detected. Re-enforcing config.",
    r"gateway connect failed": "Gateway connection failure. Forcing restart.",
    r"EADDRINUSE": "Port conflict detected. Cleaning up and restarting.",
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [AutonomicSentinel] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(HEALING_LOG, mode='a')
    ]
)

def log_healing(message):
    """Log a healing gesture to the sovereign journal."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(HEALING_LOG, "a") as f:
        f.write(f"[{timestamp}] 🛠️ HEALING GESTURE: {message}\n")
    logging.info(f"🛠️ {message}")

def heal_auth():
    """Resolve authentication drift."""
    log_healing("Initiating Auth Repair (enforce_config.py)...")
    try:
        subprocess.run(["python3", str(ENFORCE_SCRIPT)], check=True, cwd=str(SENTINEL_DIR))
        log_healing("Auth Repair complete. Restarting gateway...")
        subprocess.run(["pkill", "-f", "openclaw gateway"], check=False)
    except Exception as e:
        log_healing(f"Auth Repair FAILED: {e}")

def heal_connection():
    """Resolve gateway connection failures."""
    log_healing("Initiating Connection Repair (Gatekeeper reset)...")
    try:
        subprocess.run(["pkill", "-9", "-f", "openclaw gateway"], check=False)
        log_healing("Connection Repair complete. Sentinel loop will restart.")
    except Exception as e:
        log_healing(f"Connection Repair FAILED: {e}")

def monitor_loop():
    """Tails the gateway log and triggers healing protocols."""
    HEALING_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_healing("Mission 006: Autonomic Self-Healing ACTIVE.")

    if not GATEWAY_LOG.exists():
        logging.info(f"Waiting for gateway log at {GATEWAY_LOG}...")
        while not GATEWAY_LOG.exists():
            time.sleep(2)

    logging.info(f"Monitoring logs for failure patterns...")
    
    with open(GATEWAY_LOG, "r") as f:
        # Seek to end
        f.seek(0, os.SEEK_END)
        
        while True:
            line = f.readline()
            if not line:
                # Check for log rotation cases (if needed)
                time.sleep(1)
                continue

            # Match patterns
            if "unauthorized: gateway password missing" in line:
                heal_auth()
                time.sleep(5) # Cooldown
                f.seek(0, os.SEEK_END)
            elif "gateway connect failed" in line:
                heal_connection()
                time.sleep(5) # Cooldown
                f.seek(0, os.SEEK_END)
            elif "EADDRINUSE" in line:
                log_healing("Port conflict detected. Executing purge sequence...")
                subprocess.run(["lsof", "-t", "-i:18789"], check=False)
                heal_connection() # Trigger restart
                time.sleep(5)
                f.seek(0, os.SEEK_END)

if __name__ == "__main__":
    try:
        monitor_loop()
    except KeyboardInterrupt:
        log_healing("Autonomic monitor offline.")
