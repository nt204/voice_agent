import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

from app.config import config, gemini_system_instruction, require_env


SCRIPTED_TURNS = [
    "မင်္ဂလာပါ၊ Venus BigOne က ဘာထုတ်ကုန်လဲဆိုတာ ရှင်းပြပေးပါ။",
    "တစ်ဗူးဈေးဘယ်လောက်လဲ။",
    "Combo စျေးတွေကိုလည်း ပြောပြပေးပါ။",
    "အဓိကအကျိုးကျေးဇူးတွေက ဘာတွေလဲ။",
    "ဘယ်လိုသောက်ရမလဲ၊ တစ်နေ့ဘယ်နှစ်ကြိမ်လဲ။",
    "ကျွန်မမှာ ဆီးချိုနည်းနည်းရှိတယ်၊ သောက်လို့ရလား။",
    "ပို့ခက ဘယ်လိုရှိလဲ။",
    "တစ်ဗူးမှာမယ်ဆိုရင် ဘာအချက်အလက် ပေးရမလဲ။",
    "ရလဒ်ကို ရာနှုန်းပြည့် အာမခံလား။",
]

INCOMPLETE_ENDINGS = (
    "ဆိုရင်",
    "ဝယ်ယူရင်",
    "ဝယ်ယူတဲ့",
    "နဲ့",
    "တော့",
    "အတွက်",
    "ပြီး",
    "လည်း",
    "နောက်",
    "Venus",
)


def _issue_flags(turn: int, answer: str) -> list[str]:
    flags = []
    stripped = answer.strip()
    if not stripped:
        flags.append("empty_answer")
        return flags

    if turn == 2 and any(term in answer for term in ("Combo", "ပို့ခ", "နှစ်ဗူး", "မှာယူ")):
        flags.append("price_only_overanswered")
    if any(stripped.endswith(ending) for ending in INCOMPLETE_ENDINGS):
        flags.append("incomplete_sentence")
    if turn == 6 and not any(term in answer for term in ("ဆီးချို", "မသုံးသင့်", "ဆရာဝန်", "ဆေးဝါးပညာရှင်")):
        flags.append("safety_answer_not_grounded")
    negative_guarantee_terms = ("မပေး", "မရှိ", "မပြော", "မဟုတ်", "ကွဲပြား")
    if turn == 9 and (
        "အာမခံပါတယ်" in answer
        or ("၁၀၀%" in answer and not any(term in answer for term in negative_guarantee_terms))
    ):
        flags.append("guarantee_overclaim")
    return flags


async def _collect_turn(session, text: str) -> str:
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part(text=text)]),
        turn_complete=True,
    )
    chunks: list[str] = []
    async for response in session.receive():
        content = response.server_content
        if not content:
            continue
        if content.output_transcription and content.output_transcription.text:
            chunks.append(content.output_transcription.text)
        if content.turn_complete:
            break
    return "".join(chunks).strip()


async def run(args: argparse.Namespace) -> None:
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    rows = []

    async with client.aio.live.connect(
        model=config.gemini.model,
        config=types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            speech_config=types.SpeechConfig(
                language_code=config.gemini.language_code,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.gemini.voice_name,
                    )
                ),
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=gemini_system_instruction())]
            ),
        ),
    ) as session:
        greeting = await _collect_turn(
            session,
            "Say exactly this greeting in natural Myanmar Burmese. Do not add anything else: "
            + config.gemini.initial_greeting,
        )
        rows.append(
            {
                "turn": 0,
                "user": "<initial greeting>",
                "assistant": greeting,
                "issues": _issue_flags(0, greeting),
            }
        )

        for turn, user_text in enumerate(SCRIPTED_TURNS, 1):
            answer = await _collect_turn(session, user_text)
            rows.append(
                {
                    "turn": turn,
                    "user": user_text,
                    "assistant": answer,
                    "issues": _issue_flags(turn, answer),
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(
                json.dumps(
                    {"timestamp": datetime.now().isoformat(timespec="seconds"), **row},
                    ensure_ascii=False,
                )
                + "\n"
            )

    issue_count = sum(len(row["issues"]) for row in rows)
    print(f"Wrote {len(rows)} turns to {out_path}")
    print(f"Detected {issue_count} issue flags")
    for row in rows:
        compact = {
            "turn": row["turn"],
            "assistant": row["assistant"],
            "issues": row["issues"],
        }
        print(json.dumps(compact, ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scripted Myanmar Gemini Live conversation.")
    parser.add_argument("--out", default="conversations/myanmar-long-conversation.jsonl")
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument("--max-output-tokens", type=int, default=config.gemini.max_output_tokens)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
