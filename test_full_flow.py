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
                    
            async def send_silence():
                silent_frame = b'\xff' * 160
                for i in range(50):
                    await websocket.send(json.dumps({
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(silent_frame).decode("ascii"),
                            "timestamp": str(int(time.time() * 1000))
                        }
                    }))
                    await asyncio.sleep(0.02)

            print("\n[Tester] Turn 1: 'Is Venus Big One product good? What are its benefits?'")
            await send_audio(text_to_pcmu("Is Venus Big One product good? What are its benefits?", "q1"))
            await send_silence()
            
            # Wait only 3 seconds before interrupting!
            print("[Tester] Waiting 3 seconds for AI to start answering before barging in...")
            await asyncio.sleep(3)

            print("\n[Tester] Turn 2 (Barge-in): 'Keep it short, what is the price for one box?'")
            await send_audio(text_to_pcmu("Keep it short, what is the price for one box?", "q2"))
            await send_silence()
            
            print("[Tester] Waiting 6 seconds for AI to answer price...")
            await asyncio.sleep(6)

            print("\n[Tester] Turn 3: 'Ok, I will take two boxes.'")
            await send_audio(text_to_pcmu("Ok, I will take two boxes.", "q3"))
            await send_silence()
            
            print("[Tester] Waiting 6 seconds for AI to confirm quantity and ask for info...")
            await asyncio.sleep(6)
            
            print("\n[Tester] Turn 4: 'My phone number is zero nine one two three four five six seven eight.'")
            await send_audio(text_to_pcmu("My phone number is zero nine one two three four five six seven eight.", "q4"))
            await send_silence()
            
            print("[Tester] Finished. Listening to AI final readback/close for 15 seconds...")
            await asyncio.sleep(15)
            
    except Exception as e:
        print("[Tester] Test failed:", e)

if __name__ == "__main__":
    asyncio.run(simulate_conversation())
