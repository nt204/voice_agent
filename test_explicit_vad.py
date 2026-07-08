import asyncio
import os
import json
from google import genai
from google.genai import types

async def main():
    client = genai.Client()
    
    # 24000Hz 1 channel 16-bit PCM silence
    silence = b"\x00" * 48000
    
    print("Connecting...")
    async with client.aio.live.connect(
        model="gemini-3.1-flash-live-preview",
        config=types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=None,  # explicitly OFF
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            ),
        )
    ) as session:
        print("Connected.")
        
        async def receive_task():
            try:
                async for response in session.receive():
                    print(f"[RECV] {response}")
            except Exception as e:
                print(f"[RECV] Error: {e}")
                
        t = asyncio.create_task(receive_task())
        
        print("\n--- TURN 1 ---")
        await session.send_realtime_input(activity_start=types.ActivityStart())
        print("Sent ActivityStart")
        
        await session.send_realtime_input(
            audio=types.Blob(
                mime_type="audio/pcm;rate=24000",
                data=b"\x00" * 48000
            )
        )
        print("Sent Audio")
        
        # NOTE: Do we need to send turn_complete=True? Let's just send ActivityEnd!
        await session.send_realtime_input(activity_end=types.ActivityEnd())
        await session.send_client_content(turn_complete=True)
        print("Sent ActivityEnd + turn_complete=True")
        
        await asyncio.sleep(5)
        
        print("\n--- TURN 2 ---")
        await session.send_realtime_input(activity_start=types.ActivityStart())
        print("Sent ActivityStart")
        
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="What did I just ask?")]),
            turn_complete=True
        )
        print("Sent Text")
        
        await session.send_realtime_input(activity_end=types.ActivityEnd())
        await session.send_client_content(turn_complete=True)
        print("Sent ActivityEnd + turn_complete=True")
        
        await asyncio.sleep(5)
        t.cancel()

if __name__ == "__main__":
    asyncio.run(main())
