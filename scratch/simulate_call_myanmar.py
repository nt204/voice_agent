import asyncio
import base64
import json
import io
import time
import wave
import av
import websockets
import audioop

WS_URL = "ws://localhost:3000/telnyx/ws?token=telnyx_2eT8RzvL9qK4xP1mN6cY"

# We have these customer audio files in test_artifacts/myanmar_audio/my-buy-complete/
TURNS = [
    "test_artifacts/myanmar_audio/my-buy-complete/02-customer.mp3",
    "test_artifacts/myanmar_audio/my-buy-complete/04-customer.mp3",
    "test_artifacts/myanmar_audio/my-buy-complete/06-customer.mp3",
    "test_artifacts/myanmar_audio/my-buy-complete/08-customer.mp3",
]

def mp3_to_pcmu_8k(file_path: str) -> bytes:
    container = av.open(file_path)
    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=8000,
    )
    
    pcm_out = bytearray()
    for frame in container.decode(audio=0):
        resampled = resampler.resample(frame)
        if resampled:
            for rf in resampled:
                pcm_out.extend(rf.to_ndarray().tobytes())
                
    flushed = resampler.resample(None)
    if flushed:
        for rf in flushed:
            pcm_out.extend(rf.to_ndarray().tobytes())
            
    # Convert PCM16 to PCMU (u-law)
    pcmu = audioop.lin2ulaw(bytes(pcm_out), 2)
    return pcmu

async def main():
    print("--- STARTING MYANMAR CUSTOMER CALL SIMULATION ---")
    call_id = f"call-sim-myanmar-{int(time.time())}"
    print(f"Generated Unique Call ID: {call_id}")
    
    async with websockets.connect(WS_URL) as ws:
        # 1. Send connected event
        await ws.send(json.dumps({"event": "connected"}))
        print("Sent 'connected' event")
        
        # 2. Send start event
        start_event = {
            "event": "start",
            "stream_id": "simulated-myanmar-stream",
            "start": {
                "call_control_id": call_id,
                "from": "+85961695448",
                "to": "+19482194502",
                "media_format": {
                    "encoding": "PCMU",
                    "sample_rate": 8000
                }
            }
        }
        await ws.send(json.dumps(start_event))
        print("Sent 'start' event")
        
        # Record AI output
        ai_audio = bytearray()
        last_ai_audio_time = [time.time()]
        
        async def receive_loop():
            nonlocal ai_audio
            try:
                async for message in ws:
                    event = json.loads(message)
                    if event.get("event") == "media":
                        media = event.get("media") or {}
                        payload = base64.b64decode(media.get("payload") or "")
                        # Convert PCMU to PCM16
                        pcm = audioop.ulaw2lin(payload, 2)
                        ai_audio.extend(pcm)
                        last_ai_audio_time[0] = time.time()
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"Error in receive loop: {e}")

        # Start background receive task
        recv_task = asyncio.create_task(receive_loop())
        
        # Wait 4 seconds for the initial greeting
        print("Waiting for AI initial greeting...")
        await asyncio.sleep(4.0)
        
        # Silence frame in PCMU (160 bytes for 20ms)
        silence_frame = audioop.lin2ulaw(b'\x00' * 320, 2)
        
        # Play each customer turn
        timestamp = 0
        for i, turn_path in enumerate(TURNS, start=1):
            print(f"\n--- Customer Turn {i}: Streaming {turn_path} ---")
            pcmu_data = mp3_to_pcmu_8k(turn_path)
            
            # Send in 20ms chunks (160 bytes of PCMU)
            chunk_size = 160
            for offset in range(0, len(pcmu_data), chunk_size):
                chunk = pcmu_data[offset:offset+chunk_size]
                if len(chunk) < chunk_size:
                    chunk = chunk + silence_frame[:chunk_size - len(chunk)]
                
                media_event = {
                    "event": "media",
                    "media": {
                        "timestamp": str(timestamp),
                        "payload": base64.b64encode(chunk).decode("ascii")
                    }
                }
                await ws.send(json.dumps(media_event))
                timestamp += 20
                await asyncio.sleep(0.02)
                
            # Send 1 second of silence to trigger VAD speech end
            print("Finished speaking, sending silence for VAD...")
            for _ in range(50):
                media_event = {
                    "event": "media",
                    "media": {
                        "timestamp": str(timestamp),
                        "payload": base64.b64encode(silence_frame).decode("ascii")
                    }
                }
                await ws.send(json.dumps(media_event))
                timestamp += 20
                await asyncio.sleep(0.02)
                
            # Wait dynamically for AI response to finish speaking
            print("Waiting for AI response...")
            await asyncio.sleep(2.5)  # Wait at least 2.5 seconds for AI to start responding
            while True:
                now = time.time()
                if now - last_ai_audio_time[0] > 2.0:  # 2 seconds of silence from AI
                    break
                await asyncio.sleep(0.2)
            
        # Send stop event
        print("\nSending 'stop' event...")
        await ws.send(json.dumps({"event": "stop"}))
        await asyncio.sleep(1.0)
        
        # Close connection
        await ws.close()
        recv_task.cancel()
        
    print("Simulation complete.")
    
    # Save the recorded AI audio to a WAV file
    wav_path = "scratch/ai_response_myanmar.wav"
    with wave.open(wav_path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(bytes(ai_audio))
    print(f"Recorded AI response saved to {wav_path}")
    
    # Wait for the server background tasks to finish and fetch call details
    print("Waiting 5 seconds for server post-processing and order extraction...")
    await asyncio.sleep(5.0)
    
    url = f"http://localhost:3000/api/calls/{call_id}"
    print(f"Fetching call details from: {url}")
    import urllib.request
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            with open("scratch/call_detail_myanmar.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("Successfully saved call detail to scratch/call_detail_myanmar.json")
    except Exception as e:
        print(f"Error fetching call detail: {e}")

if __name__ == "__main__":
    asyncio.run(main())
