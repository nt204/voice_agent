import asyncio
import json
import subprocess
from pathlib import Path
import websockets

BASE_DIR = Path(__file__).resolve().parent.parent

def decode_mp3_to_pcm16_16k(mp3_relative_path: str) -> bytes:
    mp3_path = BASE_DIR / mp3_relative_path.replace("\\", "/")
    if not mp3_path.exists():
        raise FileNotFoundError(f"Audio file not found: {mp3_path}")
    
    cmd = [
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", "-"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {stderr.decode('utf-8')}")
    return stdout

async def run_scenario(scenario_id: str):
    uri = "ws://localhost:3000/infobip/ws"
    
    manifest_path = BASE_DIR / "test_artifacts" / "myanmar_audio" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Filter turns for the requested scenario
    turns = [turn for turn in manifest if turn["scenario_id"] == scenario_id]
    turns.sort(key=lambda t: t["turn_index"])
    
    if not turns:
        print(f"No audio files found for scenario: {scenario_id}")
        return

    print(f"\n==========================================")
    print(f"Starting Audio Scenario Test: {scenario_id}")
    print(f"==========================================\n")

    async with websockets.connect(uri) as ws:
        # Start a background task to receive/drain messages to keep connection alive
        async def receive_messages():
            try:
                async for message in ws:
                    pass
            except websockets.exceptions.ConnectionClosed:
                pass

        reader_task = asyncio.create_task(receive_messages())

        # 1. Connect
        connect_payload = {
            "event": "websocket:connected",
            "callId": f"audio-test-{scenario_id}",
            "content-type": "audio/x-private-pcm-16;rate=16000",
            "from": "+959793905153"
        }
        await ws.send(json.dumps(connect_payload))
        print("Connected to WebSocket. Waiting 4s for AI greeting...")
        await asyncio.sleep(4.0)

        # 2. Stream turns
        for turn in turns:
            print(f"\n--- Turn {turn['turn_index']} (Customer) ---")
            print(f"Expected Text: \"{turn['text']}\"")
            
            pcm_data = decode_mp3_to_pcm16_16k(turn["path"])
            print(f"Decoded {len(pcm_data)} bytes PCM (16kHz, 16-bit). Streaming in real-time...")
            
            # Send audio in 20ms frames (640 bytes)
            frame_size = 640
            sent_bytes = 0
            for i in range(0, len(pcm_data), frame_size):
                frame = pcm_data[i:i+frame_size]
                # Pad final frame if necessary
                if len(frame) < frame_size:
                    frame = frame + b"\x00" * (frame_size - len(frame))
                await ws.send(frame)
                sent_bytes += len(frame)
                await asyncio.sleep(0.02)
                
            print(f"Finished streaming customer audio ({sent_bytes} bytes sent).")
            # Signal end of customer speech
            await ws.send(json.dumps({"event": "mock:audio_end"}))
            
            # Wait for AI response
            print("Waiting 6s for AI response and ASR transcription...")
            await asyncio.sleep(6.0)

        print("\nScenario turns completed. Closing connection...")
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        
    print("\nTest completed. Checking database for extracted order...")
    await asyncio.sleep(2.0)
    
    # HTTP query to the local server
    import urllib.request
    call_id = f"audio-test-{scenario_id}"
    url = f"http://localhost:3000/api/calls/{call_id}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"\n==========================================")
            print(f"RESULTS FOR CALL: {call_id}")
            print(f"==========================================")
            print("\n--- Final Transcript ---")
            for item in data.get("transcript", []):
                print(f"{item['speaker'].upper()}: {item['text']}")
            
            print("\n--- Extracted Customer & Order Info ---")
            print(json.dumps(data.get("customer", {}), ensure_ascii=False, indent=2))
            print("\n--- Extracted Combo Order ---")
            print(json.dumps(data.get("order", {}), ensure_ascii=False, indent=2))
            print(f"==========================================\n")
    except Exception as e:
        print(f"Failed to fetch results from {url}: {e}")
    
if __name__ == "__main__":
    import sys
    scenario = sys.argv[1] if len(sys.argv) > 1 else "my-buy-complete"
    asyncio.run(run_scenario(scenario))
