import io
import re
import wave

from google import genai
from google.genai import types

from app.config import config, require_env


TRANSCRIPTION_PROMPT = """Transcribe this customer phone-call audio verbatim.

Rules:
- The speaker may use Myanmar, Vietnamese, English, Korean, or switch languages.
- Preserve the original language and writing system. Do not translate.
- Write exactly what is spoken; do not repair grammar, infer intent, or add product context.
- Preserve numbers, product names, quantities, and place names as heard.
- Return only the transcript, with no label, explanation, markdown, or quotation marks.
- If speech is genuinely unintelligible, return exactly [unclear].
"""


def build_transcription_prompt(*, live_candidate: str = "", language_priority: str = "") -> str:
    prompt = TRANSCRIPTION_PROMPT
    if language_priority.strip():
        prompt += (
            "\nLanguage priority:\n"
            f"- Expected customer languages, in priority order: {language_priority.strip()}.\n"
        )
        if "Vietnamese" in language_priority:
            prompt += (
                "- Vietnamese phone speech is often misheard as Myanmar or Korean when the audio is noisy.\n"
                "- Do not output Myanmar or Korean text unless the audio clearly supports it.\n"
                "- If the sound can reasonably be Vietnamese, keep Vietnamese in Latin script with accents when clear.\n"
                "- Do not switch writing systems just because the fast Live ASR candidate used that script.\n"
            )
    return prompt


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)
    return output.getvalue()


def clean_transcript_response(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(
        r"^(?:transcript|verbatim transcription)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    if cleaned.casefold() in {"[unclear]", "unclear", "[inaudible]", "inaudible"}:
        return ""
    return " ".join(cleaned.split())


class SecondaryAsrTranscriber:
    def __init__(
        self,
        client=None,
        model: str | None = None,
        language_priority: str | None = None,
    ) -> None:
        self.client = client or genai.Client(api_key=require_env("GEMINI_API_KEY"))
        self.model = model or config.gemini.secondary_asr_model
        self.language_priority = (
            config.gemini.secondary_asr_language_priority
            if language_priority is None
            else language_priority
        )

    async def transcribe(self, pcm: bytes, sample_rate: int, live_candidate: str = "") -> str:
        if len(pcm) < sample_rate // 5 * 2:
            return ""
        
        last_exc = None
        backoff = 0.5
        for attempt in range(4):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=build_transcription_prompt(
                                    live_candidate=live_candidate,
                                    language_priority=self.language_priority,
                                )
                            ),
                            types.Part(
                                inline_data=types.Blob(
                                    data=pcm16_to_wav(pcm, sample_rate),
                                    mime_type="audio/wav",
                                )
                            ),
                        ],
                    ),
                    config=types.GenerateContentConfig(
                        temperature=0,
                        max_output_tokens=250,
                    ),
                )
                return clean_transcript_response(getattr(response, "text", "") or "")
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise last_exc
