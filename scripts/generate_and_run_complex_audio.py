import asyncio
import json
import subprocess
from pathlib import Path
import websockets
import edge_tts

BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIO_ID = "audio-test-complex-myanmar"
AUDIO_DIR = BASE_DIR / "test_artifacts" / "myanmar_audio" / "complex_test"

SCENARIO_TURNS = [
    (2, "နို့မှုန့်က ဘာကောင်းလဲ။ အမျိုးသမီးတွေအတွက်ပဲလား။ ဈေးကရော ဘယ်လောက်လဲ။"),
    (4, "စျေးကြီးတယ်နော်။ တခြား ကွန်ဘိုတွေ မရှိဘူးလား။ ငါးဘူးဝယ်ရင် ဘယ်လောက်လဲ။"),
    (6, "ကွန်ဘို ၅ က တအားများတယ်။ ကွန်ဘို ၃ ယူမယ်။ မဟုတ်ဘူး၊ စဉ်းစားဦးမယ်... ကွန်ဘို ၃ မှာ ၃ ဘူးပါတယ်။ စျေးက ၃ သိန်းနော်။ ဟုတ်လား။"),
    (8, "အေး အဲ့ဒါဆို ကွန်ဘို ၃ ပဲ မှာယူမယ်။"),
    (10, "ဖုန်းနံပါတ်က ၀၉၇၈၄၄၃၃၅၅၆ ပါ။ လိပ်စာကတော့ ရန်ကုန်မြို့၊ ကမာရွတ်မြို့နယ်၊ လှည်းတန်းလမ်း၊ အမှတ် ၁၂၃၊ ဒုတိယထပ်ပါ။"),
    (12, "ဟုတ်ကဲ့၊ အဲဒါ အမှန်ပဲ။ ပို့ပေးလိုက်ပါ။")
]

async def synthesize(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice="my-MM-NilarNeural")
    await communicate.save(str(output_path))
    print(f"Synthesized audio: '{text[:30]}...' -> {output_path.name}")

def decode_mp3_to_pcm16_16k(mp3_path: Path) -> bytes:
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

async def main():
    print("==========================================")
    print("Step 1: Synthesizing Burmese Customer Audio Turns...")
    print("==========================================\n")
    
    # Synthesize all turns
    turn_files = []
    for turn_index, text in SCENARIO_TURNS:
        output_file = AUDIO_DIR / f"{turn_index:02d}-customer.mp3"
        await synthesize(text, output_file)
        turn_files.append((turn_index, text, output_file))
        
    print("\nAll audio turns synthesized successfully.")
    
    print("\n==========================================")
    print("Step 2: Streaming Audio to Server over WebSocket...")
    print("==========================================\n")
    
    uri = "ws://localhost:3000/infobip/ws"
    async with websockets.connect(uri) as ws:
        # Start background reader task to process keepalives
        async def receive_messages():
            try:
                async for message in ws:
                    pass
            except websockets.exceptions.ConnectionClosed:
                pass

        reader_task = asyncio.create_task(receive_messages())

        # Connect
        connect_payload = {
            "event": "websocket:connected",
            "callId": SCENARIO_ID,
            "content-type": "audio/x-private-pcm-16;rate=16000",
            "from": "+959793905153"
        }
        await ws.send(json.dumps(connect_payload))
        print("Connected to server. Waiting 4s for AI greeting...")
        await asyncio.sleep(4.0)

        # Stream turns
        for turn_index, text, audio_path in turn_files:
            print(f"\n--- Turn {turn_index} (Customer) ---")
            print(f"Spoken Text: \"{text}\"")
            
            pcm_data = decode_mp3_to_pcm16_16k(audio_path)
            print(f"Streaming {len(pcm_data)} bytes of real-time audio...")
            
            # Send in 20ms frames
            frame_size = 640
            sent_bytes = 0
            for i in range(0, len(pcm_data), frame_size):
                frame = pcm_data[i:i+frame_size]
                if len(frame) < frame_size:
                    frame = frame + b"\x00" * (frame_size - len(frame))
                await ws.send(frame)
                sent_bytes += len(frame)
                await asyncio.sleep(0.02)
                
            print(f"Finished streaming ({sent_bytes} bytes sent).")
            await ws.send(json.dumps({"event": "mock:audio_end"}))
            
            # Wait for AI response
            print("Waiting 6s for AI response & ASR...")
            await asyncio.sleep(6.0)

        print("\nScenario turns completed. Closing connection...")
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass

    print("\nTest completed. Waiting 2s for order processing...")
    await asyncio.sleep(2.0)
    
    # Query PostgreSQL
    print("\n==========================================")
    print("Step 3: Checking Extracted Database Records...")
    print("==========================================\n")
    
    import urllib.request
    url = f"http://localhost:3000/api/calls/{SCENARIO_ID}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode("utf-8"))
            print("--- Final Transcript ---")
            for item in data.get("transcript", []):
                print(f"{item['speaker'].upper()}: {item['text']}")
            
            print("\n--- Extracted Customer Info ---")
            print(json.dumps(data.get("customer", {}), ensure_ascii=False, indent=2))
            
            print("\n--- Extracted Combo Order ---")
            print(json.dumps(data.get("order", {}), ensure_ascii=False, indent=2))
            print(f"==========================================\n")
    except Exception as e:
        print(f"Failed to fetch results from {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
