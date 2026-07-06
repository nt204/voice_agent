import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    return int(raw)


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
class GeminiConfig:
    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
    voice_name: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    input_sample_rate: int = _int_env("GEMINI_INPUT_SAMPLE_RATE", 16000)
    product_knowledge_path: str = os.getenv("PRODUCT_KNOWLEDGE_PATH", "product.md")
    initial_greeting: str = os.getenv(
        "GEMINI_INITIAL_GREETING",
        "Hãy chào khách bằng tiếng Việt và hỏi khách cần tư vấn sản phẩm nào. Nói ngắn gọn.",
    )
    system_instruction: str = os.getenv(
        "GEMINI_SYSTEM_INSTRUCTION",
        "Bạn là trợ lý AI trả lời cuộc gọi bằng tiếng Việt. Trả lời ngắn gọn, tự nhiên.",
    )


@dataclass(frozen=True)
class AppConfig:
    port: int = _int_env("PORT", 3000)
    public_base_url: str | None = os.getenv("PUBLIC_BASE_URL")
    infobip: InfobipConfig = InfobipConfig()
    signalwire: SignalWireConfig = SignalWireConfig()
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
    knowledge = product_knowledge()
    if not knowledge:
        return config.gemini.system_instruction

    return f"""{config.gemini.system_instruction}

QUY TẮC CHĂM SÓC KHÁCH HÀNG:
- Ưu tiên cao nhất: Luôn nói tiếng Việt tự nhiên, dễ hiểu. Không dùng tiếng Anh trong cuộc gọi, trừ khi khách yêu cầu rõ ràng.
- Nếu dữ liệu sản phẩm có câu hướng dẫn khác về ngôn ngữ, vẫn ưu tiên quy tắc tiếng Việt ở trên.
- Dùng dữ liệu sản phẩm bên dưới làm nguồn thông tin chính khi tư vấn.
- Không bịa giá, công dụng, chính sách, khuyến mãi, xuất xứ hoặc cam kết ngoài dữ liệu sản phẩm.
- Nếu khách hỏi thông tin chưa có trong dữ liệu, hãy nói chưa có thông tin chính xác và xin số điện thoại/nhu cầu để tư vấn viên xác nhận.
- Ưu tiên hỏi và ghi nhận: tên khách, số điện thoại, nhu cầu, số lượng muốn mua, địa chỉ/khu vực giao hàng, câu hỏi còn vướng.

DỮ LIỆU SẢN PHẨM:
{knowledge}
"""
