import asyncio
import io
import json
import re
import wave

from google import genai
from google.genai import types

from app.config import config, require_env
from app.gemini_retry import gemini_retry_delay_seconds, is_gemini_rate_limit_error


BURMESE_PHONE_DIGIT_GUIDE = """Burmese phone digits:
- A phone number may be spoken one digit at a time: 0 = သုည or ဝ; 1 = တစ်; 2 = နှစ်; 3 = သုံး; 4 = လေး; 5 = ငါး; 6 = ခြောက်; 7 = ခုနစ် or ခုနှစ်; 8 = ရှစ်; 9 = ကိုး.
- When the context is a phone number, recognize every spoken digit in order. Do not combine the sequence into a quantity, price, age, or arithmetic value.
- Listen through the entire audio before answering. Pauses between digits do not mean the phone number has ended.
- Preserve the complete digit sequence supported by the audio. Do not guess a missing or unclear digit.
"""


BURMESE_ORDER_LISTENING_GUIDE = """Burmese order words:
- Customers may say ၂ ဘူး, နှစ်ဘူး, နှစ်ပုဒ်, or similar casual speech to mean two boxes/items.
- In a sales-order context, do not confuse နှစ်ဘူး / နှစ်ပုဒ် with keypad, pressing, or unrelated words.
- Catalog vocabulary includes Venus BigOne and Combo 1, Combo 2, Combo 3, and Combo 5.
- Burmese pronunciation of the English word Combo may sound close to ကွန်ဘို, ကွန်ဂို, ကွန်ပူ, or ကုန်ပူ. When the audio supports that catalog word followed by 1, 2, 3, or 5, transcribe it as "Combo <number>"; never invent it from unclear audio.
- Preserve explicit order phrases such as အော်ဒါတင်ပေးပါ, ယူမယ်, ယူပါမယ်, မှာမယ်, မှာယူမယ်, Combo 2, Combo 3, and product names.
- Do not remove Burmese politeness particles or insert spaces that change a phrase's meaning. Keep corrections such as "တစ်ဘူး မဟုတ်ဘူး၊ နှစ်ဘူး ယူမယ်" complete.
"""


TRANSCRIPTION_PROMPT = """Transcribe this customer phone-call audio verbatim.

Rules:
- The speaker is expected to use Burmese for the Myanmar market, but may use Myanmar English or product names in English.
- Preserve the original language and writing system. Do not translate.
- Write exactly what is spoken; do not repair grammar, infer intent, or add product context.
- Preserve numbers, product names, quantities, and place names as heard.
- Return only the transcript, with no label, explanation, markdown, or quotation marks.
- If speech is genuinely unintelligible, return exactly [unclear].
""" + "\n" + BURMESE_PHONE_DIGIT_GUIDE + "\n" + BURMESE_ORDER_LISTENING_GUIDE


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
""" + "\n" + BURMESE_PHONE_DIGIT_GUIDE
    prompt += "\n" + BURMESE_ORDER_LISTENING_GUIDE
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
        normal_failures = 0
        max_retry_delay = max(1, config.gemini.rate_limit_retry_max_delay_seconds)
        while normal_failures < 4:
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
                        max_output_tokens=750,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                return clean_transcript_response(getattr(response, "text", "") or "")
            except Exception as exc:
                last_exc = exc
                if is_gemini_rate_limit_error(exc):
                    delay = gemini_retry_delay_seconds(
                        exc,
                        fallback_seconds=backoff,
                        max_delay_seconds=max_retry_delay,
                    )
                    await asyncio.sleep(delay)
                    backoff = min(
                        max(backoff * 2, delay * 1.5),
                        max_retry_delay,
                    )
                    continue
                normal_failures += 1
                if normal_failures < 4:
                    await asyncio.sleep(backoff)
                    backoff = min(
                        backoff * 2,
                        max_retry_delay,
                    )
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
        normal_failures = 0
        max_retry_delay = max(1, config.gemini.rate_limit_retry_max_delay_seconds)
        while normal_failures < 4:
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=types.Content(role="user", parts=parts),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=BATCH_TRANSCRIPTION_SCHEMA,
                        temperature=0,
                        max_output_tokens=min(2000, max(300, len(usable) * 180)),
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
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
                if is_gemini_rate_limit_error(exc):
                    delay = gemini_retry_delay_seconds(
                        exc,
                        fallback_seconds=backoff,
                        max_delay_seconds=max_retry_delay,
                    )
                    await asyncio.sleep(delay)
                    backoff = min(
                        max(backoff * 2, delay * 1.5),
                        max_retry_delay,
                    )
                    continue
                normal_failures += 1
                if normal_failures < 4:
                    await asyncio.sleep(backoff)
                    backoff = min(
                        backoff * 2,
                        max_retry_delay,
                    )
        raise last_exc
