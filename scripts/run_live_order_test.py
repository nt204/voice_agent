import argparse
import asyncio
import json
from datetime import datetime, timezone

from google.genai import types

from app.config import gemini_system_instruction
from app.gemini_bridge import GeminiCallBridge
from app.main import call_history


EXPECTED_ORDER = {
    "customer_name": "May Thinzar",
    "customer_phone": "09784433556",
    "shipping_address": "အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန်",
    "product_name": "Venus BigOne Combo 3",
}

CUSTOMER_TURNS = [
    "Venus BigOne Combo 3 ကို မှာယူချင်ပါတယ်ရှင်။",
    "လက်ခံမယ့်နာမည်က May Thinzar ပါရှင်။",
    "ဖုန်းနံပါတ်က သုည ကိုး ခုနစ် ရှစ် လေး လေး သုံး သုံး ငါး ငါး ခြောက် ပါရှင်။",
    "ပို့ရမယ့်လိပ်စာက အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန် ပါရှင်။",
    (
        "ဟုတ်ကဲ့၊ Combo 3၊ May Thinzar၊ ဖုန်း 09784433556 နဲ့ "
        "အဲဒီလိပ်စာအားလုံးမှန်ပါတယ်။ အော်ဒါအတည်ပြုပေးပါရှင်။"
    ),
]


async def run_live_order_test(call_id: str, timeout_seconds: int) -> dict:
    async def discard_audio(_: bytes) -> None:
        return None

    async def record(speaker: str, text: str) -> None:
        clean_text = " ".join(text.split())
        if clean_text:
            call_history.add_transcript(call_id, speaker, clean_text)

    call_history.start_call(
        call_id=call_id,
        direction="inbound",
        provider="gemini-live-order-test",
        customer_phone="",
    )
    bridge = GeminiCallBridge(
        call_id=call_id,
        call_sample_rate=16000,
        send_audio=discard_audio,
        send_initial_greeting=False,
        system_instruction=gemini_system_instruction("inbound"),
        on_transcript=record,
    )

    try:
        await bridge.start()
        for customer_text in CUSTOMER_TURNS:
            await record("customer", customer_text)
            bridge.turn_complete.clear()
            await bridge.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=customer_text)],
                ),
                turn_complete=True,
            )
            await asyncio.wait_for(
                bridge.turn_complete.wait(),
                timeout=timeout_seconds,
            )
            await asyncio.sleep(0.4)
    finally:
        await bridge.close()

    await asyncio.to_thread(call_history.finish_call, call_id)
    call = call_history.get_call(call_id)
    if not call:
        raise RuntimeError(f"Call was not persisted: {call_id}")

    order = call.get("order") or {}
    checks = {
        field: order.get(field) == expected
        for field, expected in EXPECTED_ORDER.items()
    }
    checks["quantity"] = order.get("quantity") == 3
    checks["total_price"] = order.get("total_price") == 390000
    checks["status"] = order.get("status") == "ready_to_confirm"

    return {
        "call_id": call_id,
        "status": call.get("status"),
        "customer": call.get("customer"),
        "order": call.get("order"),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "transcript": call.get("transcript"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and verify a real test order through Gemini Live."
    )
    parser.add_argument("--call-id")
    parser.add_argument("--timeout-seconds", type=int, default=35)
    args = parser.parse_args()
    call_id = args.call_id or (
        "live-order-test-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    )
    result = asyncio.run(run_live_order_test(call_id, args.timeout_seconds))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if not result["all_checks_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
