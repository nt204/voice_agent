import asyncio
import websockets
import json
import base64
import os
import subprocess
import time

def text_to_pcmu(text: str, filename: str):
    subprocess.run(["say", "-o", f"{filename}.aiff", text], check=False)
    subprocess.run(["ffmpeg", "-y", "-i", f"{filename}.aiff", "-ar", "8000", "-ac", "1", "-f", "mulaw", f"{filename}.pcmu", "-hide_banner", "-loglevel", "error"])
    with open(f"{filename}.pcmu", "rb") as f:
        return f.read()

async def simulate_conversation():
    try:
        async with websockets.connect('ws://localhost:3001/telnyx/ws?token=telnyx_2eT8RzvL9qK4xP1mN6cY') as websocket:
            print("[Tester] Connected to WebSocket")
            
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
            print("[Tester] Sent start event. Waiting 2 seconds...")
            await asyncio.sleep(2)
            
            async def send_audio(pcm_data):
                chunk_size = 160
                for i in range(0, len(pcm_data), chunk_size):
                    chunk = pcm_data[i:i+chunk_size]
                    if len(chunk) < chunk_size:
                        chunk += b'\x00' * (chunk_size - len(chunk))
                    media_event = {
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(chunk).decode("ascii"),
                            "timestamp": str(int(time.time() * 1000))
                        }
                    }
                    await websocket.send(json.dumps(media_event))
                    await asyncio.sleep(0.02)

            print("[Tester] Simulating query 1: 'Sản phẩm này có những công dụng gì?'")
            audio1 = text_to_pcmu("Sản phẩm này có những công dụng gì?", "query1")
            await send_audio(audio1)
            # Send silence to trigger Speech ended
            silent_frame = b'\xff' * 160
            for i in range(20):
                await websocket.send(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(silent_frame).decode("ascii"),
                        "timestamp": str(int(time.time() * 1000))
                    }
                }))
                await asyncio.sleep(0.02)
            print("[Tester] Finished query 1. Listening to response for 2 seconds before interrupting...")
            await asyncio.sleep(2)

            print("[Tester] Simulating 2nd question (BARGE-IN): 'Giá bao nhiêu vậy em ơi?'")
            audio2 = text_to_pcmu("Giá bao nhiêu vậy em ơi?", "query2")
            await send_audio(audio2)
            for i in range(20):
                await websocket.send(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(silent_frame).decode("ascii"),
                        "timestamp": str(int(time.time() * 1000))
                    }
                }))
                await asyncio.sleep(0.02)
            print("[Tester] Finished barge-in. Listening to response for 10 seconds...")
            await asyncio.sleep(10)
            
    except Exception as e:
        print("[Tester] Test failed:", e)

if __name__ == "__main__":
    asyncio.run(simulate_conversation())
