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
    stream_token: str = os.getenv("TELNYX_STREAM_TOKEN", "")
    stream_codec: str = os.getenv("TELNYX_STREAM_CODEC", "PCMU")
    stream_sample_rate: int = _int_env("TELNYX_STREAM_SAMPLE_RATE", 8000)
    stream_track: str = os.getenv("TELNYX_STREAM_TRACK", "inbound_track")
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
    greeting_audio_path: str = os.getenv(
        "TELNYX_GREETING_AUDIO_PATH",
        "assets/telnyx-greeting.wav",
    )
    greeting: str = os.getenv(
        "TELNYX_GREETING",
        "မင်္ဂလာပါ။ ဆိုင်ရဲ့ အကြံပေးအကူအညီဖြစ်ပါတယ်။ ဘယ်လိုကူညီပေးရမလဲရှင်။",
    )


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
    voice_name: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    language_code: str = os.getenv("GEMINI_LANGUAGE_CODE", "my-MM")
    input_sample_rate: int = _int_env("GEMINI_INPUT_SAMPLE_RATE", 16000)
    temperature: float = _float_env("GEMINI_TEMPERATURE", 0.2)
    top_p: float = _float_env("GEMINI_TOP_P", 0.7)
    max_output_tokens: int = _int_env("GEMINI_MAX_OUTPUT_TOKENS", 400)
    product_knowledge_path: str = os.getenv("PRODUCT_KNOWLEDGE_PATH", "product.md")
    initial_greeting: str = os.getenv(
        "GEMINI_INITIAL_GREETING",
        "မင်္ဂလာပါ။ ဆိုင်ရဲ့ အကြံပေးအကူအညီဖြစ်ပါတယ်။ ဘယ်လိုကူညီပေးရမလဲရှင်။",
    )
    system_instruction: str = os.getenv(
        "GEMINI_SYSTEM_INSTRUCTION",
        (
            "သင်သည် ဖုန်းဖြင့် မြန်မာဘာသာသာ ပြောဆိုသော အရောင်းအကြံပေး AI ဖြစ်သည်။ "
            "ဖောက်သည် မည်သည့်ဘာသာဖြင့်မေးမေး အဓိပ္ပါယ်နားလည်ပြီး မြန်မာစာဖြင့်သာ ဖြေပါ။"
        ),
    )


@dataclass(frozen=True)
class AppConfig:
    port: int = _int_env("PORT", 3000)
    public_base_url: str | None = os.getenv("PUBLIC_BASE_URL")
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


def gemini_system_instruction() -> str:
    voice_rules = (
        "\n\nအသံခေါ်ဆိုမှု စည်းကမ်းများ:\n"
        "- မဖြစ်မနေ မြန်မာဘာသာဖြင့်သာ ပြောပါ။ အင်္ဂလိပ်၊ ဗီယက်နမ် သို့မဟုတ် အခြားဘာသာဖြင့် မဖြေပါနှင့်။\n"
        "- ဖုန်းဆက်ပြောနေသလို သဘာဝကျ၊ နူးညံ့၊ အလွန်တိုသော အဖြေများပဲ ပြောပါ။\n"
        "- တစ်လှည့်တွင် ၁ စာကြောင်းမှ ၂ စာကြောင်းအထိသာ ပြောပါ။ ပုံမှန်အားဖြင့် ၅-၈ စက္ကန့်အတွင်း ရပ်ပါ။\n"
        "- ဖောက်သည်မေးသည့်အချက်ကို အတိုချုံးအသိအမှတ်ပြုပြီးမှ ဖြေပါ။ မလိုအပ်ဘဲ စာရင်းရှည် မဖတ်ပါနှင့်။\n"
        "- နောက်ဆက်တွဲမေးခွန်းကို ၁ ခုသာ မေးပါ။ အော်ဒါပိတ်ရန် သို့မဟုတ် အချက်အလက်လိုအပ်သောအခါမှသာ မေးပါ။\n"
        "- မရှင်းလင်းလျှင် \"အသံလေး မရှင်းလို့ပါရှင်။ တစ်ခါလောက် ထပ်ပြောပေးနိုင်မလားရှင်။\" ဟုသာ ပြောပါ။\n"
        "- စကားလုံးကျပန်း၊ အဓိပ္ပါယ်မပြည့်သော မြန်မာစာ၊ မသိသောဘာသာစကားရောနှောမှု၊ product/order အဓိပ္ပါယ်မရှိသော စကားတိုတိုများကို intent မခန့်မှန်းပါနှင့်။\n"
        "- If the caller asks a vague demonstrative question such as 'what is that', 'what do you call that', 'this one', or Burmese equivalents like 'အဲဒါက ဘာလဲ' / 'အဲဒါကို ဘယ်လိုခေါ်လဲ', never stay silent. Ask one short Burmese clarification question.\n"
        "- \"Momo Kawaii\" ကဲ့သို့ ဆိုင်/ပစ္စည်း/အော်ဒါနှင့် မရှင်းလင်းသော စကားစုများကို ဝယ်ယူလိုကြောင်း သို့မဟုတ် အရေအတွက်အဖြစ် မယူဆပါနှင့်။ ပြန်ပြောခိုင်းပါ။\n"
        "- စာကြောင်းတစ်ကြောင်းပြောပြီးတိုင်း ဖောက်သည်ပြန်ပြောနိုင်ရန် ရပ်ပါ။\n"
    )
    knowledge = product_knowledge()
    if not knowledge:
        return f"{config.gemini.system_instruction}{voice_rules}"

    return f"""{config.gemini.system_instruction}{voice_rules}

ဖောက်သည်စောင့်ရှောက်မှု စည်းကမ်းများ:
- အမြင့်ဆုံးဦးစားပေး: အဖြေတိုင်းကို မြန်မာဘာသာဖြင့်သာ ဖြေပါ။ ဖောက်သည်က အခြားဘာသာဖြင့်မေးလျှင်လည်း အဓိပ္ပါယ်ကို မြန်မာလို ပြန်ဖြေပါ။
- အောက်ပါကုန်ပစ္စည်းအချက်အလက်ကိုသာ အဓိကအရင်းအမြစ်အဖြစ် အသုံးပြုပါ။
- ဈေးနှုန်း၊ အကျိုးကျေးဇူး၊ မူဝါဒ၊ promotion၊ ဇာစ်မြစ် သို့မဟုတ် ကတိပေးချက်များကို ကိုယ်တိုင်မထွင်ပါနှင့်။
- မပါရှိသောအချက်အလက်ကို မေးလျှင် မသိသေးကြောင်း ရိုးသားစွာပြောပြီး စစ်ပေးမည်ဟု ပြောပါ။
- ဈေးနှုန်းသာမေးလျှင် ဈေးနှုန်းကိုသာ ဖြေပါ။ အရေအတွက်၊ ဖုန်း၊ လိပ်စာ မမေးပါနှင့်။
- သုံးနည်း၊ ကြာချိန်၊ အကျိုးကျေးဇူး၊ လုံခြုံမှုသာမေးလျှင် ထိုမေးခွန်းကိုသာ ဖြေပါ။
- အကျိုးကျေးဇူးမေးလျှင် အများဆုံး အကျိုးကျေးဇူး ၃ ခုသာ ပြောပါ။ ဖောက်သည်မမေးလျှင် အသေးစိတ်မရှင်းပါနှင့်။
- ဝယ်ယူလိုကြောင်းနှင့် အရေအတွက်ကို ဖောက်သည်က ပြတ်သားစွာ အတည်ပြုပြီးမှသာ ဖုန်းနံပါတ်ကို မေးပါ။
- မရှင်းလင်းသောအသံ၊ စကားတို၊ transcription error ဖြစ်နိုင်သောစာသားများမှ အရေအတွက် သို့မဟုတ် ဝယ်ယူလိုကြောင်းကို မခန့်မှန်းပါနှင့်။
- အရေအတွက်ပြတ်သားပြီး ဝယ်ယူမည်ဟု ပြောပြီးမှ ဖုန်းနံပါတ်ကို အရင်မေးပါ။ ဖုန်းနံပါတ်ရပြီးမှ လိပ်စာကို မေးပါ။
- တစ်လှည့်တည်းတွင် ဖုန်းနံပါတ်နှင့် လိပ်စာ နှစ်ခုစလုံးကို တပြိုင်နက် မမေးပါနှင့်။
- တစ်ကြိမ်တွင် သင့်တော်သော ပစ္စည်း ၁ မျိုးမှ ၂ မျိုးအထိသာ အကြံပြုပါ။
- ကျန်းမာရေး/အလှအပရလဒ်ကို အာမခံမပြောပါနှင့်။ ရလဒ်သည် လူတစ်ဦးချင်းစီအပေါ် မူတည်နိုင်သည်ဟု ပြောပါ။
- ကိုယ်ဝန်ဆောင်၊ နို့တိုက်၊ အခံရောဂါရှိသူ၊ hormone/treatment ဆေးသောက်နေသူများကို ဆရာဝန် သို့မဟုတ် ဆေးဝါးကျွမ်းကျင်သူနှင့် အရင်တိုင်ပင်ရန် ပြောပါ။
- ဖောက်သည်နှင့် ငြင်းခုံခြင်း၊ ဖိအားပေးရောင်းခြင်း မလုပ်ပါနှင့်။

ကုန်ပစ္စည်းအချက်အလက်:
{knowledge}

နောက်ဆုံးအသံဖြေကြားစည်းကမ်း:
- အဖြေတိုင်းကို မြန်မာဘာသာဖြင့်သာ ပြောပါ။
- တိုတို၊ သဘာဝကျ၊ sales tư vấn ပုံစံဖြင့် ၁ စာကြောင်းမှ ၂ စာကြောင်းအထိသာ ဖြေပါ။
- Product benefit မေးခွန်းများတွင် အကျိုးကျေးဇူး ၃ ခုထက်ပို မပြောပါနှင့်။
- နောက်ဆက်တွဲမေးခွန်း ၁ ခုထက်ပို မမေးပါနှင့်။
- အဖြေပြီးသည်နှင့် ချက်ချင်းရပ်ပါ။
"""
