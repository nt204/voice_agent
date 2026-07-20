import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import edge_tts

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import gemini_system_instruction
from app.gemini_bridge import GeminiCallBridge
from app.order_extraction import analyze_call_with_gemini
from app.sales_analysis import _extract_phone_from_turns, _extract_phone_precise
from app.secondary_asr import SecondaryAsrTranscriber


DEFAULT_OUTPUT_DIR = BASE_DIR / "test_artifacts" / "long_phone_matrix"


SCENARIOS = [
    {
        "id": "confusable-correction-09780771433",
        "phone": "09780771433",
        "phone_turn": 4,
        "product_name": "Venus BigOne Combo 3",
        "quantity": 3,
        "total_price": 390000,
        "address": "အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန်",
        "turns": [
            "Venus BigOne က ဘာအတွက်ကောင်းလဲ၊ ဘယ်လိုသောက်ရမလဲ၊ တစ်ဘူးနဲ့ ကွန်ဘိုဈေးတွေကိုလည်း ရှင်းပြပေးပါရှင်။",
            "ကွန်ဘို ၂ နဲ့ ကွန်ဘို ၃ ကို စဉ်းစားနေတယ်။ လက်ဆောင်နဲ့ ပို့ခကိုပါ ပြောပေးပါ။",
            "ကောင်းပါပြီ၊ ကွန်ဘို ၃ ကို မှာယူမယ်။ လက်ခံမယ့်နာမည်က May Thinzar ပါရှင်။",
            "ဖုန်းနံပါတ် သုည ကိုး ကိုး ရှစ် သုည ကိုး ကိုး တစ် လေး သုံး သုံး မဟုတ်ပါဘူးရှင်။ နံပါတ်အမှန်က သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး ပါရှင်။",
            "ဟုတ်ကဲ့၊ ဖုန်းနံပါတ် သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး က မှန်ပါတယ်ရှင်။",
            "ပို့ရမယ့်လိပ်စာက အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန် ပါရှင်။",
            "ဟုတ်ကဲ့၊ အမှတ် ၁၂၃ ဗိုလ်ချုပ်လမ်း လသာမြို့နယ် ရန်ကုန် လိပ်စာက မှန်ပါတယ်ရှင်။",
            "ကွန်ဘို ၃၊ နာမည် May Thinzar၊ ဖုန်းနံပါတ်နဲ့ လိပ်စာ အားလုံးမှန်ပါတယ်။ အော်ဒါအတည်ပြုပေးပါရှင်။",
        ],
    },
    {
        "id": "ten-digit-repeated-0961695448",
        "phone": "0961695448",
        "phone_turn": 4,
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "total_price": 210000,
        "address": "အမှတ် ၄၈၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်၊ ရန်ကုန်",
        "turns": [
            "ဒီနို့မှုန့်မှာ ဘာတွေပါလဲ၊ အသက်သုံးဆယ်ကျော်အမျိုးသမီးတွေ သောက်လို့ရလား၊ ဈေးနှုန်းလည်း ပြောပြပေးပါရှင်။",
            "နှစ်ဘူးယူရင် ပို့ခအခမဲ့လား၊ စုစုပေါင်း နှစ်သိန်းတစ်သောင်းပဲလား။",
            "ဟုတ်ကဲ့၊ ကွန်ဘို ၂ နှစ်ဘူး မှာယူမယ်။ လက်ခံမယ့်နာမည်က Su Su ပါရှင်။",
            "ပို့ဆောင်ရန်ဖုန်းနံပါတ်ကို တစ်လုံးချင်းပြောမယ်နော်။ သုည ကိုး ခြောက် တစ် ခြောက် ကိုး ငါး လေး လေး ရှစ် ပါရှင်။",
            "ဟုတ်ကဲ့၊ သုည ကိုး ခြောက် တစ် ခြောက် ကိုး ငါး လေး လေး ရှစ် အဲဒီဖုန်းနံပါတ် မှန်ပါတယ်ရှင်။",
            "လိပ်စာက အမှတ် ၄၈၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်၊ ရန်ကုန် ပါရှင်။",
            "ဟုတ်ကဲ့၊ အဲဒီလိပ်စာအတိုင်း ပို့ပေးပါ။ လိပ်စာမှန်ပါတယ်ရှင်။",
            "ကွန်ဘို ၂ နှစ်ဘူး၊ Su Su၊ ဖုန်းနံပါတ်နဲ့ လိပ်စာ အားလုံးမှန်ပါတယ်။ အော်ဒါတင်ပေးပါရှင်။",
        ],
    },
    {
        "id": "new-number-09993905153",
        "phone": "09993905153",
        "phone_turn": 4,
        "product_name": "Venus BigOne Combo 1",
        "quantity": 1,
        "total_price": 120000,
        "address": "အမှတ် ၅၂၊ အင်းစိန်လမ်း၊ ကမာရွတ်မြို့နယ်၊ ရန်ကုန်",
        "turns": [
            "Venus BigOne တစ်ဘူးကို ဘယ်နှရက်သောက်ရလဲ၊ ဘယ်အချိန်သောက်ရလဲ၊ ဈေးဘယ်လောက်လဲရှင်။",
            "အရင်စမ်းသောက်ချင်လို့ တစ်ဘူးပဲ ယူမယ်။ ပို့ခရှိရင်လည်း ပြောပေးပါရှင်။",
            "ကွန်ဘို ၁ တစ်ဘူးမှာမယ်။ လက်ခံမယ့်နာမည်က Hnin Ei ပါရှင်။",
            "အရင်ဖုန်းနံပါတ်ကို မသုံးတော့ဘူးရှင်။ ဖုန်းနံပါတ်အသစ်က သုည ကိုး ကိုး ကိုး သုံး ကိုး သုည ငါး တစ် ငါး သုံး ပါရှင်။",
            "ဟုတ်ကဲ့၊ ဖုန်းနံပါတ်အသစ် သုည ကိုး ကိုး ကိုး သုံး ကိုး သုည ငါး တစ် ငါး သုံး က မှန်ပါတယ်ရှင်။",
            "ပို့ရမယ့်လိပ်စာက အမှတ် ၅၂၊ အင်းစိန်လမ်း၊ ကမာရွတ်မြို့နယ်၊ ရန်ကုန် ပါရှင်။",
            "အမှတ် ၅၂ အင်းစိန်လမ်း ကမာရွတ်မြို့နယ် ရန်ကုန်၊ အဲဒီလိပ်စာ မှန်ပါတယ်ရှင်။",
            "ကွန်ဘို ၁ တစ်ဘူး၊ Hnin Ei၊ ဖုန်းနံပါတ်အသစ်နဲ့ လိပ်စာ အားလုံးမှန်ပါတယ်။ အော်ဒါအတည်ပြုပေးပါရှင်။",
        ],
    },
]


async def _synthesize(text: str, path: Path, voice: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text=text, voice=voice, rate="-8%").save(str(path))


def _decode_mp3(path: Path) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout


async def _wait_for_model_turn(
    bridge: GeminiCallBridge,
    completed_before: int,
    activity_before: float,
    timeout_seconds: int,
    minimum_completed_turns: int = 1,
    allow_activity_fallback: bool = False,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last_completed = bridge.completed_turn_count
    last_change = loop.time()
    while loop.time() < deadline:
        await asyncio.sleep(0.5)
        if bridge.completed_turn_count != last_completed:
            last_completed = bridge.completed_turn_count
            last_change = loop.time()
        if (
            bridge.completed_turn_count
            >= completed_before + minimum_completed_turns
            and loop.time() - last_change >= 2.0
        ):
            return
        if (
            allow_activity_fallback
            and bridge.last_model_activity_at > activity_before
            and loop.time() - bridge.last_model_activity_at >= 5.0
        ):
            return
    raise TimeoutError("Gemini Live did not complete its response in time")


async def _stream_turn(bridge: GeminiCallBridge, pcm: bytes) -> None:
    await bridge.start_input_activity()
    frame_size = 640
    for offset in range(0, len(pcm), frame_size):
        frame = pcm[offset:offset + frame_size]
        if len(frame) < frame_size:
            frame += b"\x00" * (frame_size - len(frame))
        await bridge.send_input_audio(frame)
        await asyncio.sleep(0.02)
    await bridge.end_input_activity()


def _agent_phone_from_segment(segment: list[dict[str, str]]) -> str:
    agent_turns = [
        item["text"] for item in segment if item.get("speaker") == "agent"
    ]
    return _extract_phone_from_turns(agent_turns)


async def _run_scenario(
    scenario: dict[str, Any],
    output_dir: Path,
    voice: str,
    timeout_seconds: int,
    cached_phone_asr: str = "",
    cached_post_call_asr: dict[int, str] | None = None,
    skip_post_call_asr: bool = False,
) -> dict[str, Any]:
    transcripts: list[dict[str, str]] = []
    turn_segments: dict[int, list[dict[str, str]]] = {}
    turn_audio: list[tuple[int, bytes, int, str]] = []
    live_customer_entries: dict[int, dict[str, str]] = {}
    post_call_asr: dict[int, str] = {}
    secondary = SecondaryAsrTranscriber()

    async def discard_audio(_: bytes) -> None:
        return None

    async def clear_audio() -> None:
        return None

    async def record(speaker: str, text: str) -> None:
        clean_text = " ".join(str(text or "").split())
        if clean_text:
            transcripts.append({"speaker": speaker, "text": clean_text})

    async def transcribe_turn(
        audio: bytes,
        sample_rate: int,
        turn_number: int,
        live_candidate: str,
    ) -> str:
        if turn_number != scenario["phone_turn"] - 1:
            return live_candidate
        if cached_phone_asr:
            return cached_phone_asr
        return await secondary.transcribe(audio, sample_rate, live_candidate)

    bridge = GeminiCallBridge(
        call_id=f"long-phone-audio-{scenario['id']}",
        call_sample_rate=16000,
        send_audio=discard_audio,
        clear_audio=clear_audio,
        explicit_vad=True,
        send_initial_greeting=False,
        realtime_input=True,
        system_instruction=gemini_system_instruction("inbound"),
        on_transcript=record,
        on_audio_turn=transcribe_turn,
    )

    try:
        await bridge.start()
        await bridge.set_output_muted(True)
        for turn_number, customer_text in enumerate(scenario["turns"], start=1):
            audio_path = output_dir / scenario["id"] / f"{turn_number:02d}.mp3"
            if not audio_path.exists():
                await _synthesize(customer_text, audio_path, voice)
            pcm = _decode_mp3(audio_path)
            turn_audio.append((turn_number - 1, pcm, 16000, ""))
            segment_start = len(transcripts)
            completed_before = bridge.completed_turn_count
            activity_before = bridge.last_model_activity_at
            await _stream_turn(bridge, pcm)
            await _wait_for_model_turn(
                bridge,
                completed_before=completed_before,
                activity_before=activity_before,
                timeout_seconds=timeout_seconds,
                minimum_completed_turns=1,
                allow_activity_fallback=(
                    turn_number == scenario["phone_turn"] + 1
                ),
            )
            if turn_number == scenario["phone_turn"]:
                # The fixed server readback does not require Gemini to emit a
                # second model turn. Wait for its ASR task directly instead.
                await bridge.wait_for_audio_turns()
            segment = transcripts[segment_start:]
            turn_segments[turn_number] = segment
            live_customer_entry = next(
                (item for item in segment if item.get("speaker") == "customer"),
                None,
            )
            if live_customer_entry:
                live_customer_entries[turn_number - 1] = live_customer_entry
            print(
                f"[{scenario['id']}] turn {turn_number}/{len(scenario['turns'])} complete",
                flush=True,
            )
        await bridge.wait_for_audio_turns()
        if cached_post_call_asr:
            post_call_asr = cached_post_call_asr
        elif not skip_post_call_asr:
            post_call_asr = await secondary.transcribe_many(turn_audio)
        if post_call_asr:
            for turn_index, corrected_text in post_call_asr.items():
                entry = live_customer_entries.get(turn_index)
                if entry is not None and corrected_text:
                    entry["text"] = corrected_text
    finally:
        await bridge.close()

    expected_phone = scenario["phone"]
    phone_turn_index = scenario["phone_turn"] - 1
    secondary_phone_text = bridge.secondary_asr_results.get(phone_turn_index, "")
    secondary_phone = _extract_phone_precise(secondary_phone_text)
    readback_phone = _agent_phone_from_segment(
        turn_segments.get(scenario["phone_turn"], [])
    )
    sales_result = await asyncio.to_thread(
        analyze_call_with_gemini,
        transcripts,
        fallback_phone="",
    )
    order = sales_result.get("order") or {}
    checks = {
        "secondary_asr_phone": secondary_phone == expected_phone,
        "server_phone": bridge.delivery_state.phone == expected_phone,
        "phone_confirmed": bridge.delivery_state.phone_confirmed,
        "agent_readback_phone": readback_phone == expected_phone,
        "order_phone": order.get("customer_phone") == expected_phone,
        "order_product": order.get("product_name") == scenario["product_name"],
        "order_quantity": order.get("quantity") == scenario["quantity"],
        "order_total": order.get("total_price") == scenario["total_price"],
        "order_status": order.get("status") == "ready_to_confirm",
    }
    return {
        "scenario_id": scenario["id"],
        "expected_phone": expected_phone,
        "secondary_asr_text": secondary_phone_text,
        "secondary_asr_phone": secondary_phone,
        "secondary_asr_source": "cache" if cached_phone_asr else "gemini",
        "post_call_asr": post_call_asr,
        "server_phone": bridge.delivery_state.phone,
        "phone_confirmed": bridge.delivery_state.phone_confirmed,
        "agent_readback_phone": readback_phone,
        "order": order,
        "checks": checks,
        "passed": all(checks.values()),
        "transcript": transcripts,
    }


async def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    selected = [
        scenario
        for scenario in SCENARIOS
        if not args.scenario or scenario["id"] in args.scenario
    ]
    results = []
    cached_phone_asr = {}
    cached_post_call_asr = {}
    if args.phone_asr_cache:
        cached_report = json.loads(args.phone_asr_cache.read_text(encoding="utf-8"))
        for item in cached_report.get("results", []):
            cached_phone_asr[item.get("scenario_id", "")] = item.get(
                "secondary_asr_text",
                "",
            )
            cached_post_call_asr[item.get("scenario_id", "")] = {
                int(key): value
                for key, value in (item.get("post_call_asr") or {}).items()
            }
    for scenario in selected:
        print(f"Starting {scenario['id']}", flush=True)
        result = await _run_scenario(
            scenario,
            output_dir=args.output_dir,
            voice=args.voice,
            timeout_seconds=args.timeout_seconds,
            cached_phone_asr=cached_phone_asr.get(scenario["id"], ""),
            cached_post_call_asr=cached_post_call_asr.get(scenario["id"]),
            skip_post_call_asr=args.skip_post_call_asr,
        )
        results.append(result)
        print(
            f"Completed {scenario['id']}: {'PASS' if result['passed'] else 'FAIL'}",
            flush=True,
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(results),
        "passed_count": sum(1 for item in results if item["passed"]),
        "all_passed": all(item["passed"] for item in results),
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run long Burmese audio conversations with varied phone numbers."
    )
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--voice", default="my-MM-NilarNeural")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--phone-asr-cache", type=Path)
    parser.add_argument("--skip-post-call-asr", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_matrix(args))
    report_path = args.report or args.output_dir / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("scenario_count", "passed_count", "all_passed")}, indent=2))
    print(f"Report: {report_path}")
    if not report["all_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
