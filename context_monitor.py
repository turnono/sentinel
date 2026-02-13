import asyncio
import websockets
import json
import logging
import subprocess
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] ContextMonitor: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

URI = "ws://127.0.0.1:18789"
# Hardcoded for now as it's the fixed dev token in openclaw.json
TOKEN = "98a78e62552017edb19a9302e7eee104d51902e215381f66"

# Alert thresholds
ALERT_THRESHOLD_PERCENT = 90
CRITICAL_THRESHOLD_PERCENT = 98

# Debounce alerts to avoid spamming (seconds)
ALERT_COOLDOWN = 60
last_alert_time = 0

def send_notification(title, message, sound="Basso"):
    """Sends a macOS system notification."""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
        subprocess.run(["osascript", "-e", script], check=True)
        logging.info(f"Notification sent: {title} - {message}")
    except Exception as e:
        logging.error(f"Failed to send notification: {e}")

async def monitor():
    global last_alert_time
    logging.info(f"Starting Context Monitor. Connecting to {URI}...")
    
    while True:
        try:
            async with websockets.connect(URI) as websocket:
                logging.info("Connected to OpenClaw Gateway.")
                
                # Handshake / Connect
                connect_req = {
                    "id": "init",
                    "type": "req",
                    "method": "connect",
                    "params": {
                        "auth": {
                            "token": TOKEN
                        },
                        "client": {
                            "mode": "probe",
                            "platform": "darwin",
                            "version": "2026.2.9",
                            "id": "openclaw-probe"
                        },
                        "minProtocol": 3,
                        "maxProtocol": 3
                    }
                }
                
                await websocket.send(json.dumps(connect_req))
                
                # Wait for auth response
                while True:
                    resp = await websocket.recv()
                    data = json.loads(resp)
                    
                    if data.get("type") == "res" and data.get("id") == "init":
                        if data.get("ok"):
                            logging.info("Authentication successful.")
                            break
                        else:
                            logging.error(f"Authentication failed: {data}")
                            return

                # Polling loop
                while True:
                    try:
                        req = {
                            "id": "poll",
                            "type": "req",
                            "method": "sessions.list",
                            "params": {
                                "limit": 1
                            }
                        }
                        await websocket.send(json.dumps(req))
                        
                        resp = await websocket.recv()
                        data = json.loads(resp)
                        
                        if data.get("type") == "res" and data.get("id") == "poll" and data.get("ok"):
                            payload = data.get("payload", {})
                            sessions = payload.get("sessions", [])
                            defaults = payload.get("defaults", {})
                            
                            if sessions:
                                session = sessions[0]
                                # Logic to find current active session if multiple? 
                                # For now, taking the first one is likely sufficient for single-user TUI.
                                
                                total_tokens = session.get("totalTokens", 0)
                                # contextTokens can be on the session or fallback to defaults
                                context_limit = session.get("contextTokens") or defaults.get("contextTokens") or 1048576 # Default 1M fallback
                                
                                if context_limit > 0:
                                    usage_percent = (total_tokens / context_limit) * 100
                                    
                                    logging.debug(f"Usage: {usage_percent:.2f}% ({total_tokens}/{context_limit})")
                                    
                                    current_time = time.time()
                                    if usage_percent >= ALERT_THRESHOLD_PERCENT:
                                        if (current_time - last_alert_time) > ALERT_COOLDOWN:
                                            if usage_percent >= CRITICAL_THRESHOLD_PERCENT:
                                                send_notification(
                                                    "⚠️ CRITICAL: Context Full", 
                                                    f"Agent is at {usage_percent:.1f}% capacity! RESTART SOON.",
                                                    "Sosumi"
                                                )
                                            else:
                                                send_notification(
                                                    "Context Warning",
                                                    f"Agent context usage is high: {usage_percent:.1f}%",
                                                    "Ping"
                                                )
                                            last_alert_time = current_time
                        
                        # Wait before polling again
                        await asyncio.sleep(10) 
                        
                    except websockets.exceptions.ConnectionClosed:
                        logging.warning("Connection closed during polling. Reconnecting...")
                        break
                    except Exception as e:
                        logging.error(f"Error during polling: {e}")
                        await asyncio.sleep(5)

        except (OSError, websockets.exceptions.InvalidURI, websockets.exceptions.InvalidHandshake) as e:
             logging.error(f"Connection failed: {e}. Retrying in 10s...")
             await asyncio.sleep(10)
        except Exception as e:
             logging.error(f"Unexpected monitor error: {e}. Retrying in 10s...")
             await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        logging.info("Stopping Context Monitor.")
