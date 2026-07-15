import os
from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from pathlib import Path

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
        "မင်္ဂလာပါ။ Venus BigOne နို့မှုန့် အကြောင်း မေးလို့ရပါတယ်ရှင်။",
    )


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
    extraction_model: str = os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-2.5-flash")
    order_extraction_enabled: bool = _bool_env("GEMINI_ORDER_EXTRACTION_ENABLED", False)
    order_extraction_timeout_seconds: int = _int_env("GEMINI_ORDER_EXTRACTION_TIMEOUT_SECONDS", 12)
    voice_name: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    language_code: str = os.getenv("GEMINI_LANGUAGE_CODE", "my-MM")
    input_sample_rate: int = _int_env("GEMINI_INPUT_SAMPLE_RATE", 16000)
    temperature: float = _float_env("GEMINI_TEMPERATURE", 0.2)
    top_p: float = _float_env("GEMINI_TOP_P", 0.7)
    max_output_tokens: int = _int_env("GEMINI_MAX_OUTPUT_TOKENS", 400)
    product_knowledge_path: str = os.getenv("PRODUCT_KNOWLEDGE_PATH", "product.md")
    initial_greeting: str = os.getenv(
        "GEMINI_INITIAL_GREETING",
        "မင်္ဂလာပါ။ Venus BigOne နို့မှုန့် အကြောင်း မေးလို့ရပါတယ်ရှင်။",
    )
    system_instruction: str = os.getenv(
        "GEMINI_SYSTEM_INSTRUCTION",
        (
            "သင်သည် Venus BigOne အတွက် ဖုန်းအရောင်းအကြံပေးဖြစ်သည်။ "
            "ဖောက်သည် မည်သည့်ဘာသာဖြင့်ပြောပြော မြန်မာလို သဘာဝကျကျ တိုတိုပြန်ဖြေပါ။"
        ),
    )
    secondary_asr_enabled: bool = _bool_env("GEMINI_SECONDARY_ASR_ENABLED", False)
    in_call_secondary_asr_enabled: bool = _bool_env("GEMINI_IN_CALL_SECONDARY_ASR_ENABLED", False)
    secondary_asr_model: str = os.getenv("GEMINI_SECONDARY_ASR_MODEL", "gemini-2.5-flash")
    secondary_asr_language_priority: str = os.getenv("GEMINI_SECONDARY_ASR_LANGUAGE_PRIORITY", "Myanmar")


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


def _mode_rules(mode: str) -> str:
    if mode == "inbound":
        return ""

    if mode != "outbound":
        raise ValueError(f"Unsupported call mode: {mode!r}")

    return (
        "\n\nအပြင်ထွက်ဖုန်းခေါ်ဆိုမှု စည်းကမ်းများ:\n"
        "- ဤဖုန်းခေါ်ဆိုမှုကို သင်က စတင်ခေါ်ဆိုထားခြင်းဖြစ်သည်။\n"
        "- ဖုန်းစတင်ချိန်တွင်သာ တစ်ကြိမ် နှုတ်ဆက်ပါ။ နောက်ပိုင်းတွင် ထပ်မံနှုတ်ဆက်ခြင်း သို့မဟုတ် မိတ်ဆက်ခြင်း မလုပ်ပါနှင့်။\n"
        "- ပထမဆုံးနှုတ်ဆက်ရာတွင် Venus BigOne မှ ဆက်သွယ်ခြင်းဖြစ်ကြောင်း တိုတိုပြောပါ။\n"
        "- အစပိုင်းတွင် ကုန်ပစ္စည်းအကြောင်း ရှည်လျားစွာ မကြော်ငြာပါနှင့်။\n"
        "- ပထမဆုံးနှုတ်ဆက်ပြီးနောက် ဖောက်သည်၏ နောက်ဆုံးပြောဆိုသည့် အဓိပ္ပါယ်ကို တိုက်ရိုက်တုံ့ပြန်ပါ။\n"
        "- ဖောက်သည်မေးခွန်းတိုင်းအပြီး အော်ဒါတင်ရန် အတင်းမတိုက်တွန်းပါနှင့်။\n"
        "- ဖောက်သည် အလုပ်များနေသည်ဟု ပြောလျှင် နောက်မှ ပြန်ခေါ်နိုင်ကြောင်း ယဉ်ကျေးစွာပြောပြီး အရောင်းဆက်မလုပ်ပါနှင့်။\n"
        "- ဖောက်သည် မစိတ်ဝင်စားကြောင်း ပြတ်သားစွာပြောလျှင် တိုတိုယဉ်ကျေးစွာ တုံ့ပြန်ပြီး အရောင်းဆက်မလုပ်ပါနှင့်။\n"
        "- ထပ်မခေါ်ရန် တောင်းဆိုလျှင် တစ်ကြိမ်သာ အသိအမှတ်ပြုပြီး ချက်ချင်းရပ်ပါ။\n"
        "- လူမှားခြင်း သို့မဟုတ် ဖုန်းနံပါတ်မှားခြင်းဖြစ်လျှင် တိုတိုတောင်းပန်ပြီး စကားဆက်မပြောပါနှင့်။\n"
    )


def gemini_system_instruction(mode: str = "inbound") -> str:
    if mode not in {"inbound", "outbound"}:
        raise ValueError(
            f"Unsupported call mode: {mode!r}. "
            "Expected 'inbound' or 'outbound'."
        )

    sections = [
        config.gemini.system_instruction.strip(),
        """အသံခေါ်ဆိုမှု စည်းကမ်းများ:
- ဖောက်သည် မည်သည့်ဘာသာဖြင့်ပြောပြော မြန်မာဘာသာဖြင့်သာ သဘာဝကျကျ ပြန်ဖြေပါ။
- တစ်လှည့်တွင် ၁ စာကြောင်းမှ ၂ စာကြောင်းသာ ပြောပြီး နောက်ဆက်တွဲမေးခွန်း ၁ ခုထက်မပိုပါနှင့်။
- ဖောက်သည်မေးသည့်အချက်ကိုသာ တိုတိုဖြေပါ။ မရှင်းလင်းသောအသံကို အဓိပ္ပါယ်၊ ပစ္စည်း သို့မဟုတ် အရေအတွက်အဖြစ် မခန့်မှန်းဘဲ ပြန်ပြောခိုင်းပါ။
- ကုန်ပစ္စည်းအချက်အလက်တွင် မပါသော ဈေးနှုန်း၊ အကျိုးကျေးဇူး၊ မူဝါဒ သို့မဟုတ် ကတိပေးချက်ကို မထွင်ပါနှင့်။
- ဖောက်သည်ကို ဖိအားပေးမရောင်းပါနှင့်။ ကျန်းမာရေးရလဒ်ကို အာမခံမပြောပါနှင့်။""",
        _mode_rules(mode).strip(),
        """အော်ဒါလုပ်ငန်းစဉ်:
- စိတ်ဝင်စားခြင်း၊ ဈေးမေးခြင်း၊ combo နှိုင်းယှဉ်ခြင်းသည် အော်ဒါအတည်ပြုခြင်း မဟုတ်ပါ။
- ဖောက်သည်က ပစ္စည်း သို့မဟုတ် combo နှင့် အရေအတွက်ကို ပြတ်သားစွာ ရွေးချယ်ပြီးမှသာ အော်ဒါအချက်အလက် စတင်မေးပါ။
- ဖုန်းနံပါတ်ကို အရင်မေးပြီး လိပ်စာကို နောက်တစ်လှည့်တွင် မေးပါ။ မပြည့်စုံသည့်အချက်ကို ပြန်မေးပါ။
- လိပ်စာအဖြစ် ပို့ဆောင်မည့်နေရာကိုသာ ယူပါ။ မသက်ဆိုင်သော ကိုယ်ရေးအချက်အလက်များကို မရောပါနှင့်။
- ပစ္စည်း၊ အရေအတွက်၊ ဖုန်းနှင့် လိပ်စာကို ပြန်ဖတ်ပြီး ဖောက်သည်က မှန်ကြောင်း ပြောပြီးမှသာ အော်ဒါအတည်ပြုပြီးကြောင်း ပြောပါ။""",
    ]

    knowledge = product_knowledge()
    if knowledge:
        sections.append(f"ကုန်ပစ္စည်းအချက်အလက်:\n{knowledge}")
    return "\n\n".join(section for section in sections if section).strip()
