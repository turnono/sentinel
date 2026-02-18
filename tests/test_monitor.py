import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.DEBUG)

URI = "ws://127.0.0.1:18789"
TOKEN = "98a78e62552017edb19a9302e7eee104d51902e215381f66"

async def monitor():
    print(f"Connecting to {URI}...")
    try:
        async with websockets.connect(URI) as websocket:
            print("Connected!")
            
            # Protocol: client sends "connect" with auth.
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
            
            print(f"Sending Connect: {json.dumps(connect_req)}")
            await websocket.send(json.dumps(connect_req))
            
            while True:
                resp = await websocket.recv()
                data = json.loads(resp)
                print(f"Received: {data}")
                
                if data.get("type") == "res" and data.get("id") == "init":
                    if data.get("ok"):
                        print("Auth successful!")
                        req = {
                            "id": "1",
                            "type": "req",
                            "method": "sessions.list",
                            "params": {
                                "limit": 1
                            }
                        }
                        print(f"Sending sessions.list: {json.dumps(req)}")
                        await websocket.send(json.dumps(req))
                    else:
                        print(f"Auth failed: {data}")
                        break

                if data.get("type") == "res" and data.get("id") == "1":
                    print("Got sessions list!")
                    sessions = data.get("payload", {}).get("sessions", [])
                    defaults = data.get("payload", {}).get("defaults", {})
                    
                    for s in sessions:
                        used = s.get("totalTokens", 0)
                        limit = s.get("contextTokens") or defaults.get("contextTokens")
                        print(f"Session {s.get('key')}: {used}/{limit} tokens")
                    break
    except Exception as e:
        print(f"Error: {e}")
                
asyncio.run(monitor())
