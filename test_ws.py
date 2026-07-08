import asyncio
import websockets
import json
import base64
import os

async def simulate_call():
    try:
        async with websockets.connect('ws://localhost:3001/telnyx/ws?token=telnyx_2eT8RzvL9qK4xP1mN6cY') as websocket:
            print("Connected to WebSocket")
            
            # Send start event
            start_event = {
                "event": "start",
                "start": {
                    "stream_id": "test_stream",
                    "call_control_id": "test_call",
                    "media_format": {
                        "encoding": "PCMU",
                        "sample_rate": 8000
                    }
                }
            }
            await websocket.send(json.dumps(start_event))
            print("Sent start event")
            
            await asyncio.sleep(2)
            
            # Send media frames simulating speech (loud PCM)
            # Create a 20ms frame of loud noise
            # PCMU 8000Hz -> 160 bytes per 20ms
            import random
            loud_pcmu = bytes([random.randint(0, 255) for _ in range(160)])
            
            for i in range(10): # Send 10 frames (200ms) of loud speech to trigger barge-in
                media_event = {
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(loud_pcmu).decode("ascii"),
                        "timestamp": str(1000 + i * 20)
                    }
                }
                await websocket.send(json.dumps(media_event))
                await asyncio.sleep(0.02)
                
            print("Sent loud speech frames")
            
            # Wait to observe logs
            await asyncio.sleep(5)
            
    except Exception as e:
        print("Test failed:", e)

if __name__ == "__main__":
    asyncio.run(simulate_call())
