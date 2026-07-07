import asyncio
import os
from google import genai
from google.genai import types
from app.config import config, require_env
from app.audio import frame_bytes_for_pcm16

async def main():
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    async with client.aio.live.connect(
        model=config.gemini.model,
        config=types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    prefix_padding_ms=300,
                    silence_duration_ms=500,
                ),
                activity_handling=types.ActivityHandling.NO_INTERRUPTION,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            ),
        ),
    ) as session:
        print("Connected!")
        # Send a client content to simulate the greeting
        await session.send_realtime_input(text="Xin chào")
        
        # Read a short wav file and send it
        import wave
        with wave.open("test-call.wav", "rb") as w:
            audio_bytes = w.readframes(w.getnframes())
            # test-call.wav might be 8kHz or 16kHz. 
            print(f"Read {len(audio_bytes)} bytes of audio. Rate: {w.getframerate()}")
            
            # Send in chunks
            chunk_size = 1024
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i+chunk_size]
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type=f"audio/pcm;rate={w.getframerate()}",
                    )
                )
                await asyncio.sleep(0.01)
            
            # Feed pure silence for 2 seconds to trigger VAD
            print("Sending silence...")
            for _ in range(50):
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=b"\x00" * chunk_size,
                        mime_type=f"audio/pcm;rate={w.getframerate()}",
                    )
                )
                await asyncio.sleep(0.01)
            
        print("Sent audio and silence! Now waiting...")

        async for response in session.receive():
            if response.server_content:
                if response.server_content.output_transcription:
                    print("Gemini:", response.server_content.output_transcription.text)
                if response.server_content.input_transcription:
                    print("User:", response.server_content.input_transcription.text)
                if response.server_content.turn_complete:
                    print("Turn complete!")
                    break

if __name__ == "__main__":
    asyncio.run(main())
