import asyncio

from google import genai
from google.genai import types

from app.config import config, require_env


async def main() -> None:
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    audio_bytes = 0
    transcript = []

    async with client.aio.live.connect(
        model=config.gemini.model,
        config=types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.gemini.voice_name
                    )
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=config.gemini.system_instruction)]
            ),
        ),
    ) as session:
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="Xin chào, bạn là AI nghe cuộc gọi Viber phải không?")],
            ),
            turn_complete=True,
        )

        async for response in session.receive():
            content = response.server_content
            if not content:
                continue

            if content.output_transcription and content.output_transcription.text:
                transcript.append(content.output_transcription.text)

            model_turn = content.model_turn
            if model_turn and model_turn.parts:
                for part in model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        data = part.inline_data.data
                        audio_bytes += len(data if isinstance(data, bytes) else data.encode())

            if content.turn_complete:
                break

    print("Gemini Live OK")
    print(f"Audio bytes received: {audio_bytes}")
    if transcript:
        print("Transcript:", "".join(transcript))


if __name__ == "__main__":
    asyncio.run(main())
