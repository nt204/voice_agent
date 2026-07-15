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


DEFAULT_INBOUND_INITIAL_GREETING = (
    "Xin chào, đây là Venus BigOne. Anh/chị cần tư vấn nội dung nào ạ?"
)
DEFAULT_OUTBOUND_INITIAL_GREETING = (
    "Xin chào, em gọi từ Venus BigOne. Hiện tại anh/chị có tiện trao đổi ngắn không ạ?"
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
    voice_name: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    language_code: str = os.getenv("GEMINI_LANGUAGE_CODE", "vi-VN")
    input_sample_rate: int = _int_env("GEMINI_INPUT_SAMPLE_RATE", 16000)
    temperature: float = _float_env("GEMINI_TEMPERATURE", 0.2)
    top_p: float = _float_env("GEMINI_TOP_P", 0.7)
    max_output_tokens: int = _int_env("GEMINI_MAX_OUTPUT_TOKENS", 400)
    product_knowledge_path: str = os.getenv("PRODUCT_KNOWLEDGE_PATH", "product_vi.md")
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
            "Bạn là tư vấn bán hàng qua điện thoại cho Venus BigOne. "
            "Dù khách nói ngôn ngữ nào, hãy trả lời tự nhiên, ngắn gọn bằng tiếng Việt."
        ),
    )
    secondary_asr_enabled: bool = _bool_env("GEMINI_SECONDARY_ASR_ENABLED", False)
    in_call_secondary_asr_enabled: bool = _bool_env("GEMINI_IN_CALL_SECONDARY_ASR_ENABLED", False)
    secondary_asr_model: str = os.getenv("GEMINI_SECONDARY_ASR_MODEL", "gemini-2.5-flash")
    secondary_asr_language_priority: str = os.getenv("GEMINI_SECONDARY_ASR_LANGUAGE_PRIORITY", "Vietnamese")


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


ORDER_CONFIRMATION_TEMPLATE_RULES = """Template xác nhận thông tin đơn hàng:
- Chỉ dùng template này khi đã đủ và rõ các thông tin chính: sản phẩm/combo, số lượng, số điện thoại, địa chỉ giao hàng. Tên người nhận nên có nếu khách cung cấp.
- Nếu có tên người nhận thì đọc cả tên. Nếu chưa có tên thì không tự đoán và không chặn xác nhận đơn.
- Thứ tự đọc lại: sản phẩm/combo -> số lượng -> tên người nhận (nếu có) -> số điện thoại -> địa chỉ giao hàng -> tổng tiền (nếu chắc chắn).
- Mẫu câu: "Em xác nhận lại thông tin đơn hàng: sản phẩm {product_name}, số lượng {quantity} hộp, [người nhận {customer_name},] số điện thoại {customer_phone}, địa chỉ giao hàng {shipping_address}. Thông tin này đã đúng chưa ạ?"
- Chỉ nói "em xác nhận đơn hàng" sau khi khách nói rõ là đúng hoặc đồng ý rõ ràng.
- Nếu khách sửa thông tin, cập nhật theo thông tin mới nhất rồi đọc lại toàn bộ template.
- Nếu còn thiếu thông tin, không đọc template; chỉ hỏi ngắn gọn 1 thông tin còn thiếu."""


def _mode_rules(mode: str) -> str:
    if mode == "inbound":
        return ""

    if mode != "outbound":
        raise ValueError(f"Unsupported call mode: {mode!r}")

    return (
        "\n\nQuy tắc gọi ra:\n"
        "- Đây là cuộc gọi do bạn chủ động gọi cho khách.\n"
        "- Chỉ chào một lần ở đầu cuộc gọi. Sau đó không chào lại hoặc giới thiệu lại.\n"
        "- Lời chào đầu tiên phải nói ngắn gọn rằng Venus BigOne đang liên hệ.\n"
        "- Nếu sau câu hỏi có tiện nghe không, khách chỉ nói \"dạ\", \"vâng\", \"ừ\", \"ok\" hoặc lời xác nhận ngắn tương tự, hiểu là khách đồng ý nghe tiếp; không được tự hiểu là khách bận.\n"
        "- Không quảng cáo dài ở đầu cuộc gọi.\n"
        "- Sau lời chào đầu tiên, phản hồi trực tiếp theo ý cuối cùng khách vừa nói.\n"
        "- Không thúc ép đặt hàng sau mọi câu hỏi của khách.\n"
        "- Nếu khách nói đang bận, lịch sự nói có thể gọi lại sau và không tiếp tục bán hàng.\n"
        "- Nếu khách nói rõ là không quan tâm, trả lời ngắn gọn lịch sự và không tiếp tục bán hàng.\n"
        "- Nếu khách yêu cầu không gọi lại, chỉ ghi nhận một lần rồi dừng ngay.\n"
        "- Nếu gọi nhầm người hoặc nhầm số, xin lỗi ngắn gọn và không tiếp tục cuộc trò chuyện.\n"
    )


def gemini_initial_greeting(mode: str = "inbound") -> str:
    if mode == "inbound":
        return config.gemini.inbound_initial_greeting.strip()
    if mode == "outbound":
        return config.gemini.outbound_initial_greeting.strip()
    raise ValueError(
        f"Unsupported call mode: {mode!r}. "
        "Expected 'inbound' or 'outbound'."
    )


def gemini_system_instruction(mode: str = "inbound") -> str:
    if mode not in {"inbound", "outbound"}:
        raise ValueError(
            f"Unsupported call mode: {mode!r}. "
            "Expected 'inbound' or 'outbound'."
        )

    sections = [
        config.gemini.system_instruction.strip(),
        """Quy tắc cuộc gọi thoại:
- Dù khách nói ngôn ngữ nào, chỉ trả lời tự nhiên bằng tiếng Việt.
- Mỗi lượt chỉ nói 1 đến 2 câu và không hỏi quá 1 câu hỏi tiếp theo.
- Chỉ trả lời ngắn gọn đúng điều khách hỏi. Nếu âm thanh không rõ, không đoán ý, sản phẩm hoặc số lượng; hãy yêu cầu khách nói lại.
- Những câu ngắn như "dạ", "vâng", "ừ", "ok" thường là xác nhận hoặc cho phép tiếp tục, không phải từ chối hoặc báo bận nếu khách không nói rõ là bận.
- Không tự bịa giá, lợi ích, chính sách hoặc cam kết ngoài thông tin sản phẩm.
- Không bán hàng gây áp lực. Không cam kết chắc chắn về kết quả sức khỏe.""",
        _mode_rules(mode).strip(),
        """Quy tắc tư vấn giá và combo:
- Nếu khách hỏi chung "giá bao nhiêu" khi chưa nói combo nào, trả lời giá 1 hộp và thời gian dùng; không hỏi chốt đơn ngay. Có thể hỏi nhẹ: "Anh/chị muốn em gửi thêm giá combo không ạ?"
- Nếu khách hỏi "có combo gì" hoặc "không có combo gì", liệt kê ngắn combo 2, combo 3, combo 5 và miễn phí vận chuyển từ 2 hộp; không nói "lên đơn" khi khách chỉ đang hỏi.
- Nếu khách đã nhắc hoặc chọn một combo rồi hỏi giá, chỉ trả lời giá của combo đó; không liệt kê lại toàn bộ combo trừ khi khách hỏi so sánh.
- Nếu khách hỏi "nên mua combo nào", tư vấn theo nhu cầu: dùng thử thì combo 2, muốn quà/tiết kiệm hơn thì combo 3, mua nhiều thì combo 5. Chỉ hỏi khách chọn combo nào, không nói "lên đơn" khi khách chưa chọn.
- Nếu khách chỉ nói một từ chưa rõ như "nên", hãy hỏi lại ngắn gọn ý khách muốn tư vấn nên chọn combo nào hay muốn hỏi thông tin khác.""",
        """Quy trình đặt hàng:
- Quan tâm, hỏi giá hoặc so sánh combo không phải là xác nhận đặt hàng.
- Chỉ bắt đầu hỏi thông tin đơn hàng sau khi khách chọn rõ sản phẩm hoặc combo và số lượng.
- Sau khi khách chọn mua, hỏi tên người nhận trước nếu chưa biết. Nếu khách không muốn cung cấp tên, vẫn tiếp tục lấy số điện thoại và địa chỉ.
- Hỏi số điện thoại sau tên, hỏi địa chỉ ở lượt sau. Nếu thiếu thông tin nào thì hỏi lại thông tin đó.
- Địa chỉ chỉ lấy nơi giao hàng; không trộn thông tin cá nhân không liên quan.
- Phải đọc lại sản phẩm/combo, số lượng, tên người nhận nếu có, số điện thoại và địa chỉ; chỉ nói đã xác nhận đơn sau khi khách nói thông tin đúng.""",
        ORDER_CONFIRMATION_TEMPLATE_RULES,
    ]

    knowledge = product_knowledge()
    if knowledge:
        sections.append(f"Thông tin sản phẩm:\n{knowledge}")
    return "\n\n".join(section for section in sections if section).strip()
