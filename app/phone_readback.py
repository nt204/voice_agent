import audioop
import wave
from functools import lru_cache
from pathlib import Path

from app.audio import frame_bytes_for_pcm16
from app.config import BASE_DIR


PHONE_READBACK_DIR = BASE_DIR / "assets" / "phone_readback"
DIGIT_GAP_MS = 110
PHRASE_GAP_MS = 160


@lru_cache(maxsize=64)
def _asset_pcm(name: str, sample_rate: int) -> bytes:
    path = PHONE_READBACK_DIR / f"{name}.wav"
    with wave.open(str(path), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError(f"Phone readback asset must be mono PCM16: {path}")
        source_rate = audio.getframerate()
        pcm = audio.readframes(audio.getnframes())
    if source_rate == sample_rate:
        return pcm
    converted, _ = audioop.ratecv(
        pcm,
        2,
        1,
        source_rate,
        sample_rate,
        None,
    )
    return converted


def phone_readback_pcm(phone: str, sample_rate: int) -> bytes:
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    if not digits:
        return b""
    digit_gap = b"\x00" * (sample_rate * DIGIT_GAP_MS // 1000 * 2)
    phrase_gap = b"\x00" * (sample_rate * PHRASE_GAP_MS // 1000 * 2)
    parts = [_asset_pcm("prefix", sample_rate), phrase_gap]
    for digit in digits:
        parts.extend((_asset_pcm(digit, sample_rate), digit_gap))
    parts.extend((phrase_gap, _asset_pcm("confirm", sample_rate)))
    return b"".join(parts)


def phone_readback_frames(phone: str, sample_rate: int) -> list[bytes]:
    pcm = phone_readback_pcm(phone, sample_rate)
    if not pcm:
        return []
    frame_size = frame_bytes_for_pcm16(sample_rate)
    frames = []
    for offset in range(0, len(pcm), frame_size):
        frame = pcm[offset:offset + frame_size]
        if len(frame) < frame_size:
            frame += b"\x00" * (frame_size - len(frame))
        frames.append(frame)
    return frames
