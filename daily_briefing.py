import asyncio
import websockets
import json
import logging
import sys
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] DailyBriefing: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

URI = "ws://127.0.0.1:18789"
TOKEN = "98a78e62552017edb19a9302e7eee104d51902e215381f66" # Dev token

async def run_briefing():
    logging.info(f"Connecting to OpenClaw Gateway at {URI}...")
    try:
        async with websockets.connect(URI) as websocket:
            logging.info("Connected.")
            
            # 1. Authenticate
            connect_req = {
                "id": "init",
                "type": "req",
                "method": "connect",
                "params": {
                    "auth": { "token": TOKEN },
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
                    if not data.get("ok"):
                        logging.error(f"Auth failed: {data}")
                        return
                    logging.info("Authenticated.")
                    break

            # 2. Trigger Workflow via Chat
            workflow_prompt = (
                "Execute the 'Daily Briefing' workflow:\n"
                "1. Use the browser to search for 'latest AI agent news'.\n"
                "2. Summarize the top 3 results.\n"
                "3. Present the summary on the Canvas with a title 'Daily AI Briefing'."
            )
            
            # Using chat.send with sessionKey and message as string, plus idempotencyKey
            req = {
                "id": "trigger",
                "type": "req",
                "method": "chat.send",
                "params": {
                    "sessionKey": "agent:main:main", 
                    "message": workflow_prompt,
                    "idempotencyKey": str(uuid.uuid4())
                }
            }
             
            logging.info(f"Sending workflow trigger to agent:main:main...")
            await websocket.send(json.dumps(req))
            
            # Wait for acknowledgement
            while True:
                resp = await websocket.recv()
                data = json.loads(resp)
                
                if data.get("id") == "trigger":
                    if data.get("ok"):
                        logging.info("Workflow triggered successfully! Check TUI for progress.")
                    else:
                         logging.error(f"Failed to trigger workflow: {data}")
                    break
                    
    except Exception as e:
        logging.error(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(run_briefing())
