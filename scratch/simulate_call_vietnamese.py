import asyncio
import base64
import json
import io
import os
import wave
import av
import websockets
import audioop
import edge_tts


WS_URL = "ws://localhost:3000/telnyx/ws?token=telnyx_2eT8RzvL9qK4xP1mN6cY"

TURNS = [
    ("Sữa Venus BigOne dùng để làm gì và giá bao nhiêu vậy em?", "vi-VN-HoaiMyNeural"),
    ("Chị muốn mua 2 hộp.", "vi-VN-HoaiMyNeural"),
    ("Số điện thoại của chị là 0961695448.", "vi-VN-HoaiMyNeural"),
    ("Địa chỉ gửi về Hledan, đường Insein, Yangon nhé. Chị 28 tuổi.", "vi-VN-HoaiMyNeural"),
]

async def synthesize_vi(text: str, voice: str) -> bytes:
    temp_path = "scratch/temp_voice.mp3"
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(temp_path)
    
    container = av.open(temp_path)
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
            
    container.close()
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    # Convert PCM16 to PCMU (u-law)
    pcmu = audioop.lin2ulaw(bytes(pcm_out), 2)
    return pcmu

async def main():
    print("--- STARTING VIETNAMESE CUSTOMER CALL SIMULATION ---")
    
    async with websockets.connect(WS_URL) as ws:
        # 1. Send connected event
        await ws.send(json.dumps({"event": "connected"}))
        print("Sent 'connected' event")
        
        # 2. Send start event
        start_event = {
            "event": "start",
            "stream_id": "simulated-vietnamese-stream",
            "start": {
                "call_control_id": "call-sim-vietnamese-102",
                "from": "+84961695448",
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
        for i, (text, voice) in enumerate(TURNS, start=1):
            # Encode text safely for printing to avoid encoding error on Windows console
            safe_text = text.encode('ascii', errors='replace').decode()
            print(f"\n--- Customer Turn {i}: Synthesizing & streaming: '{safe_text}' ---")
            pcmu_data = await synthesize_vi(text, voice)
            
            # Send in 20ms chunks (160 bytes of PCMU)
            chunk_size = 160
            timestamp = 0
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
                
            # Wait 7 seconds for AI response before next turn
            print("Waiting for AI response...")
            await asyncio.sleep(7.0)
            
        # Send stop event
        print("\nSending 'stop' event...")
        await ws.send(json.dumps({"event": "stop"}))
        await asyncio.sleep(1.0)
        
        # Close connection
        await ws.close()
        recv_task.cancel()
        
    print("Simulation complete.")
    
    # Save the recorded AI audio to a WAV file
    wav_path = "scratch/ai_response_vietnamese.wav"
    with wave.open(wav_path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(bytes(ai_audio))
    print(f"Recorded AI response saved to {wav_path}")

if __name__ == "__main__":
    asyncio.run(main())
