import os
from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    return float(raw)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _frames_from_ms(ms: int, frame_ms: int = 20) -> int:
    return max(1, ceil(ms / frame_ms))


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


DEFAULT_INBOUND_INITIAL_GREETING = (
    "မင်္ဂလာပါရှင်။ Venus BigOne ကပါ။ ဘာအကြောင်း အကြံပြုပေးရမလဲရှင်။"
)
DEFAULT_OUTBOUND_INITIAL_GREETING = (
    "မင်္ဂလာပါရှင်။ Venus BigOne က ဆက်သွယ်တာပါ။ အခု ခဏပြောလို့ရမလားရှင်။"
)


@dataclass(frozen=True)
class InfobipConfig:
    base_url: str | None = os.getenv("INFOBIP_BASE_URL")
    api_key: str | None = os.getenv("INFOBIP_API_KEY")
    ws_config_name: str = os.getenv("INFOBIP_WS_CONFIG_NAME", "viber-gemini-live")
    ws_sample_rate: int = _int_env("INFOBIP_WS_SAMPLE_RATE", 24000)
    ws_shared_secret: str = os.getenv("INFOBIP_WS_SHARED_SECRET", "")


@dataclass(frozen=True)
class SignalWireConfig:
    stream_bearer_token: str = os.getenv("SIGNALWIRE_STREAM_BEARER_TOKEN", "")
    stream_codec: str = os.getenv("SIGNALWIRE_STREAM_CODEC", "L16@24000h")
    stream_sample_rate: int = _int_env("SIGNALWIRE_STREAM_SAMPLE_RATE", 24000)


@dataclass(frozen=True)
class TelnyxConfig:
    api_key: str | None = os.getenv("TELNYX_API_KEY")
    account_sid: str | None = os.getenv("TELNYX_ACCOUNT_SID")
    texml_app_id: str | None = os.getenv("TELNYX_TEXML_APP_ID")
    stream_token: str = os.getenv("TELNYX_STREAM_TOKEN", "")
    stream_codec: str = os.getenv("TELNYX_STREAM_CODEC", "PCMU")
    stream_sample_rate: int = _int_env("TELNYX_STREAM_SAMPLE_RATE", 8000)
    stream_track: str = os.getenv("TELNYX_STREAM_TRACK", "inbound_track")
    outbound_from_number: str | None = os.getenv("TELNYX_OUTBOUND_FROM_NUMBER")
    outbound_call_timeout_seconds: int = _int_env("TELNYX_OUTBOUND_CALL_TIMEOUT_SECONDS", 15)
    speech_threshold: int = _int_env("TELNYX_SPEECH_THRESHOLD", 50)
    speech_start_frames: int = _int_env(
        "TELNYX_SPEECH_START_FRAMES",
        _frames_from_ms(_int_env("TELNYX_MIN_VOICE_MS", 100)),
    )
    speech_end_silence_frames: int = _int_env(
        "TELNYX_SPEECH_END_SILENCE_FRAMES",
        _frames_from_ms(_int_env("TELNYX_SILENCE_MS", 1200)),
    )
    phone_speech_end_silence_frames: int = _int_env(
        "TELNYX_PHONE_SPEECH_END_SILENCE_FRAMES",
        _frames_from_ms(_int_env("TELNYX_PHONE_SILENCE_MS", 2200)),
    )
    address_speech_end_silence_frames: int = _int_env(
        "TELNYX_ADDRESS_SPEECH_END_SILENCE_FRAMES",
        _frames_from_ms(_int_env("TELNYX_ADDRESS_SILENCE_MS", 1800)),
    )
    adaptive_threshold: bool = _bool_env("TELNYX_ADAPTIVE_THRESHOLD", True)
    noise_multiplier: float = _float_env("TELNYX_NOISE_MULTIPLIER", 3.0)
    noise_margin: int = _int_env("TELNYX_NOISE_MARGIN", 80)
    barge_in_threshold: int = _int_env("TELNYX_BARGE_IN_THRESHOLD", 900)
    echo_suppression_ms: int = _int_env("TELNYX_ECHO_SUPPRESSION_MS", 700)
    pause_length_seconds: int = _int_env("TELNYX_PAUSE_LENGTH_SECONDS", 600)
    outbound_greeting_delay_seconds: int = _int_env("TELNYX_OUTBOUND_GREETING_DELAY_SECONDS", 2)
    greeting_audio_path: str = os.getenv(
        "TELNYX_GREETING_AUDIO_PATH",
        "assets/telnyx-greeting.wav",
    )
    greeting: str = os.getenv(
        "TELNYX_GREETING",
        DEFAULT_INBOUND_INITIAL_GREETING,
    )


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
    extraction_model: str = os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-2.5-flash")
    order_extraction_enabled: bool = _bool_env("GEMINI_ORDER_EXTRACTION_ENABLED", False)
    order_extraction_timeout_seconds: int = _int_env("GEMINI_ORDER_EXTRACTION_TIMEOUT_SECONDS", 12)
    rate_limit_retry_max_delay_seconds: int = _int_env("GEMINI_RATE_LIMIT_RETRY_MAX_DELAY_SECONDS", 60)
    voice_name: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    language_code: str = os.getenv("GEMINI_LANGUAGE_CODE", "my-MM")
    input_sample_rate: int = _int_env("GEMINI_INPUT_SAMPLE_RATE", 16000)
    temperature: float = _float_env("GEMINI_TEMPERATURE", 0.2)
    top_p: float = _float_env("GEMINI_TOP_P", 0.7)
    max_output_tokens: int = _int_env("GEMINI_MAX_OUTPUT_TOKENS", 400)
    product_knowledge_path: str = os.getenv("PRODUCT_KNOWLEDGE_PATH", "product.md")
    initial_greeting: str = os.getenv(
        "GEMINI_INITIAL_GREETING",
        DEFAULT_INBOUND_INITIAL_GREETING,
    )
    inbound_initial_greeting: str = os.getenv(
        "GEMINI_INBOUND_INITIAL_GREETING",
        DEFAULT_INBOUND_INITIAL_GREETING,
    )
    outbound_initial_greeting: str = os.getenv(
        "GEMINI_OUTBOUND_INITIAL_GREETING",
        DEFAULT_OUTBOUND_INITIAL_GREETING,
    )
    system_instruction: str = os.getenv(
        "GEMINI_SYSTEM_INSTRUCTION",
        (
            "You are a phone sales consultant for Venus BigOne in Myanmar. "
            "Always reply naturally and concisely in Burmese for Myanmar customers."
        ),
    )
    secondary_asr_enabled: bool = _bool_env("GEMINI_SECONDARY_ASR_ENABLED", False)
    in_call_secondary_asr_enabled: bool = _bool_env("GEMINI_IN_CALL_SECONDARY_ASR_ENABLED", False)
    secondary_asr_model: str = os.getenv("GEMINI_SECONDARY_ASR_MODEL", "gemini-2.5-flash")
    secondary_asr_language_priority: str = os.getenv("GEMINI_SECONDARY_ASR_LANGUAGE_PRIORITY", "Burmese, Myanmar English")


@dataclass(frozen=True)
class AppConfig:
    port: int = _int_env("PORT", 3000)
    public_base_url: str | None = os.getenv("PUBLIC_BASE_URL")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/call_history.db")
    call_recordings_dir: str = os.getenv("CALL_RECORDINGS_DIR", "recordings")
    infobip: InfobipConfig = InfobipConfig()
    signalwire: SignalWireConfig = SignalWireConfig()
    telnyx: TelnyxConfig = TelnyxConfig()
    gemini: GeminiConfig = GeminiConfig()


config = AppConfig()


@lru_cache(maxsize=1)
def product_knowledge() -> str:
    path = Path(config.gemini.product_knowledge_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


ORDER_CONFIRMATION_TEMPLATE_RULES = """Order confirmation template:
- Use this template only when product/combo, quantity, phone number, and shipping address are clear. Recipient name is optional but should be included when the customer provides it.
- If the recipient name is missing, do not invent it and do not block order confirmation.
- Read back in this order: product/combo -> quantity -> recipient name when available -> say the phone is confirmed without speaking its digits -> shipping address.
- Never repeat phone digits in the final order summary. The server already played and confirmed the exact number using fixed audio.
- Do not repeat or recalculate the total price in the final summary. The order backend computes it from the selected product and quantity.
- Burmese sample: "{product_name} {quantity} ဘူး၊ [လက်ခံမယ့်နာမည် {customer_name}၊] ဖုန်းနံပါတ် အတည်ပြုပြီး၊ ပို့ရန်လိပ်စာ {shipping_address} ဖြစ်ပါတယ်။ အချက်အလက်တွေ မှန်ပါသလားရှင်။"
- Say the order is confirmed only after the customer clearly says the information is correct or explicitly agrees.
- If the customer corrects any field, use the latest correction and read back the full template again.
- If any required field is still missing, do not read the template; ask for only one missing field at a time."""


PHONE_NUMBER_LISTENING_GUIDE = """Phone number listening guide:
- When asking for a phone number, politely ask in Burmese: "ဖုန်းနံပါတ်ကို တစ်လုံးချင်း ဖြည်းဖြည်း ပြောပေးပါရှင်။"
- Listen for one digit at a time. Burmese digit words are: 0 = သုည or ဝ; 1 = တစ်; 2 = နှစ်; 3 = သုံး; 4 = လေး; 5 = ငါး; 6 = ခြောက်; 7 = ခုနစ် or ခုနှစ်; 8 = ရှစ်; 9 = ကိုး.
- Keep every digit in the exact order spoken. Never interpret a phone-number sequence as a quantity, price, age, or combo number.
- Use the delivery-state tool as the source of truth for phone digits. Never reconstruct or remember phone digits yourself.
- Never speak phone digits. After a complete number is stored, the server automatically plays a fixed digit-by-digit readback and asks the customer to confirm it. Stay silent while that fixed readback plays.
- After the phone is confirmed, do not repeat its digits in later summaries; say only that the phone number is confirmed.
- If the customer says the readback is wrong, reject the phone in the tool and do not reuse the old digits.
- If the tool next_action is collect_phone_by_keypad, ask the customer to enter the complete phone number on the keypad and press #.
- If any digit is unclear or the number is incomplete, do not guess. Ask the customer to repeat the phone number one digit at a time."""


def _mode_rules(mode: str, product_name: str = "Venus BigOne") -> str:
    if mode == "inbound":
        return ""

    if mode != "outbound":
        raise ValueError(f"Unsupported call mode: {mode!r}")

    return (
        "\n\nOutbound call rules:\n"
        "- This is a proactive outbound call to a Myanmar customer.\n"
        "- Greet only once at the start. Do not greet or introduce yourself again later.\n"
        f"- The first greeting must briefly say {product_name} is calling.\n"
        "- If the customer answers the availability question with \"ဟုတ်ကဲ့\", \"အင်း\", \"ရပါတယ်\", \"ok\", or a similar short acknowledgement, treat it as permission to continue unless they clearly say they are busy.\n"
        "- Do not start with a long advertisement.\n"
        "- After the first greeting, respond directly to the customer's latest point.\n"
        "- Do not pressure the customer to order after every question.\n"
        "- If the customer says they are busy, politely offer to call back later and stop selling.\n"
        "- If the customer clearly says they are not interested, reply briefly and politely, then stop selling.\n"
        "- If the customer asks not to be called again, acknowledge it once and stop immediately.\n"
        "- If this is the wrong person or wrong number, apologize briefly and stop the conversation.\n"
    )


def gemini_initial_greeting(
    mode: str = "inbound", product: Mapping[str, Any] | None = None
) -> str:
    if mode == "inbound":
        if product and str(product.get("inbound_greeting") or "").strip():
            return str(product["inbound_greeting"]).strip()
        return config.gemini.inbound_initial_greeting.strip()
    if mode == "outbound":
        if product and str(product.get("outbound_greeting") or "").strip():
            return str(product["outbound_greeting"]).strip()
        return config.gemini.outbound_initial_greeting.strip()
    raise ValueError(
        f"Unsupported call mode: {mode!r}. "
        "Expected 'inbound' or 'outbound'."
    )


def gemini_system_instruction(
    mode: str = "inbound", product: Mapping[str, Any] | None = None
) -> str:
    if mode not in {"inbound", "outbound"}:
        raise ValueError(
            f"Unsupported call mode: {mode!r}. "
            "Expected 'inbound' or 'outbound'."
        )

    active_product_name = (
        str(product.get("name") or "Product") if product else "Venus BigOne"
    )
    english_examples = (
        active_product_name if product else f"{active_product_name} and Combo 2"
    )
    price_rules = (
        """Price and offer consultation rules:
- Use only the active product offers in product knowledge. Never mention offers from another product.
- If the customer asks a general price question, answer the lowest-quantity active offer first; do not ask to close the order immediately.
- If the customer asks what offers are available, briefly list only the active offers and their exact total prices.
- If the customer has already mentioned or chosen one offer and asks its price, answer only that offer unless they ask for comparison.
- If the customer asks which offer is suitable, compare the active offers by quantity and stated policy only. Do not invent benefits for a larger offer.
- If the customer says something ambiguous, ask a short clarification question."""
        if product
        else """Price and combo consultation rules:
- If the customer asks a general price question before naming a combo, answer the 1-box price and usage duration; do not ask to close the order immediately. You may gently ask whether they want to hear combo prices.
- If the customer asks what combos are available, briefly list Combo 2, Combo 3, Combo 5, and free delivery from 2 boxes; do not say you will create an order when they are only asking.
- If the customer has already mentioned or chosen one combo and asks its price, answer only that combo's price unless they ask for comparison.
- If the customer asks which combo is suitable, advise by need: Combo 2 for trial, Combo 3 for gift/savings, Combo 5 for larger purchase. Ask which combo they prefer; do not claim an order is created before they choose.
- If the customer says something ambiguous, ask a short clarification question."""
    )
    sections = [
        (
            str(product.get("system_prompt") or "").strip()
            if product
            else config.gemini.system_instruction.strip()
        ),
        f"""Voice call rules:
- Always answer in natural Burmese. English product names such as {english_examples} may stay in English.
- Each turn should be only 1 to 2 short sentences and ask at most 1 next question.
- Answer exactly what the customer asked. If audio is unclear, do not guess intent, product, quantity, phone, or address; ask the customer to repeat.
- Short acknowledgements such as "ဟုတ်ကဲ့", "အင်း", "ရပါတယ်", "ok" usually mean confirmation or permission to continue, not rejection or being busy unless the customer clearly says so.
- Do not invent prices, benefits, policies, or promises outside the product knowledge.
- Do not use pressure selling. Do not guarantee health or beauty results.""",
        _mode_rules(
            mode,
            active_product_name,
        ).strip(),
        price_rules,
        """Order workflow:
- Interest, price questions, or combo comparison are not order confirmation.
- Start collecting order details only after the customer clearly chooses a product or combo and quantity.
- After the customer chooses to buy, ask for recipient name first if unknown. If they do not want to give a name, continue with phone number and address.
- Ask for phone after name, then address in the next turn. If a field is missing, ask only for that field.
- Address must be a Myanmar delivery location only; do not mix in demographics or unrelated personal details. If the customer gives an address clearly outside Myanmar, ask for a Myanmar delivery address.
- Read back product/combo, quantity, recipient name if available, phone number, and shipping address. Say the order is confirmed only after the customer says the information is correct.""",
        PHONE_NUMBER_LISTENING_GUIDE,
        ORDER_CONFIRMATION_TEMPLATE_RULES,
    ]

    if product:
        from app.products import product_knowledge_text

        knowledge = product_knowledge_text(product)
    else:
        knowledge = product_knowledge()
    if knowledge:
        sections.append(f"Product knowledge for Myanmar market:\n{knowledge}")
    return "\n\n".join(section for section in sections if section).strip()
