import asyncio
import sys

from google import genai
from google.genai import types

from app.config import config, require_env, gemini_system_instruction


def safe_print(message: str, end: str = "\n", flush: bool = True) -> None:
    try:
        print(message, end=end, flush=flush)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        try:
            safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
            print(safe_message, end=end, flush=flush)
        except Exception:
            try:
                safe_message = message.encode("ascii", errors="backslashreplace").decode("ascii")
                print(safe_message, end=end, flush=flush)
            except Exception:
                pass


async def get_user_input(prompt: str) -> str:
    # Run the blocking input() function in a separate thread
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)


async def main() -> None:
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    safe_print("Connecting to Gemini Live...")

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
                parts=[types.Part(text=gemini_system_instruction())]
            ),
        ),
    ) as session:
        safe_print("Connected! Type your message and press Enter. Type 'exit' to quit.\n")

        async def receive_loop():
            try:
                async for response in session.receive():
                    content = response.server_content
                    if not content:
                        continue
                    if content.output_transcription and content.output_transcription.text:
                        safe_print(content.output_transcription.text, end="", flush=True)
                    if content.turn_complete:
                        safe_print("")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                safe_print(f"\n[Error in receive loop: {e}]")

        receive_task = asyncio.create_task(receive_loop())

        try:
            # Trigger the initial greeting from Gemini config
            initial_prompt = (
                "အောက်ပါစာကြောင်းကို ဖုန်းခေါ်ဆိုမှုအစ နှုတ်ဆက်စကားအဖြစ် အတိအကျသာ ပြောပါ။ "
                f"အခြားအကြောင်းအရာ မထည့်ပါနှင့်: {config.gemini.initial_greeting}"
            )
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=initial_prompt)],
                ),
                turn_complete=True,
            )

            while True:
                # Wait 1 second to let Gemini's response print completely
                await asyncio.sleep(1.0)
                user_msg = await get_user_input("You: ")
                if user_msg.strip().lower() == "exit":
                    break

                if not user_msg.strip():
                    continue

                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=user_msg)],
                    ),
                    turn_complete=True,
                )
        finally:
            receive_task.cancel()
            await receive_task


if __name__ == "__main__":
    asyncio.run(main())
