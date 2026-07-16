import asyncio
import io
import json
import re
import wave

from google import genai
from google.genai import types

from app.config import config, require_env


TRANSCRIPTION_PROMPT = """Transcribe this customer phone-call audio verbatim.

Rules:
- The speaker is expected to use Burmese for the Myanmar market, but may use Myanmar English or product names in English.
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
            "- Use this order only as a language prior; the audio remains the source of truth.\n"
            "- Choose the writing system supported by the audio, independent of any Live ASR candidate.\n"
        )
    return prompt


def build_batch_transcription_prompt(*, language_priority: str = "") -> str:
    prompt = """Transcribe each numbered customer phone-call audio clip verbatim.

Rules:
- Preserve the spoken language and writing system; do not translate or infer intent.
- Keep product names, quantities, phone numbers, and place names exactly as supported by audio.
- Return one result for every clip. Use an empty string when a clip is unintelligible.
- Return JSON matching the supplied schema only.
"""
    if language_priority.strip():
        prompt += (
            "\nExpected customer languages, in priority order: "
            f"{language_priority.strip()}. Use this only as a prior; audio is authoritative.\n"
        )
    return prompt


BATCH_TRANSCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        }
    },
    "required": ["turns"],
}


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

    async def transcribe_many(
        self,
        turns: list[tuple[int, bytes, int, str]],
    ) -> dict[int, str]:
        usable = [
            (index, pcm, sample_rate, live_candidate)
            for index, pcm, sample_rate, live_candidate in turns
            if len(pcm) >= sample_rate // 5 * 2
        ]
        if not usable:
            return {}

        parts = [
            types.Part(
                text=build_batch_transcription_prompt(
                    language_priority=self.language_priority,
                )
            )
        ]
        for index, pcm, sample_rate, _ in usable:
            parts.extend(
                [
                    types.Part(text=f"Audio turn {index}:"),
                    types.Part(
                        inline_data=types.Blob(
                            data=pcm16_to_wav(pcm, sample_rate),
                            mime_type="audio/wav",
                        )
                    ),
                ]
            )

        last_exc = None
        backoff = 0.5
        for attempt in range(4):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=types.Content(role="user", parts=parts),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=BATCH_TRANSCRIPTION_SCHEMA,
                        temperature=0,
                        max_output_tokens=min(2000, max(300, len(usable) * 180)),
                    ),
                )
                payload = json.loads(getattr(response, "text", "") or "{}")
                expected = {index for index, _, _, _ in usable}
                result: dict[int, str] = {}
                for item in payload.get("turns") or []:
                    index = item.get("index")
                    if index in expected:
                        result[index] = clean_transcript_response(str(item.get("text") or ""))
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise last_exc
