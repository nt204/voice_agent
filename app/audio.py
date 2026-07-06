import audioop
import re


class PcmFrameBuffer:
    def __init__(self, frame_bytes: int):
        self.frame_bytes = frame_bytes
        self.buffer = bytearray()

    def push(self, chunk: bytes) -> list[bytes]:
        self.buffer.extend(chunk)
        frames: list[bytes] = []

        while len(self.buffer) >= self.frame_bytes:
            frames.append(bytes(self.buffer[: self.frame_bytes]))
            del self.buffer[: self.frame_bytes]

        return frames

    def clear(self) -> None:
        self.buffer.clear()


def frame_bytes_for_pcm16(sample_rate: int, frame_ms: int = 20) -> int:
    return round(sample_rate * frame_ms / 1000) * 2


def extract_sample_rate(content_type: str | None, fallback: int) -> int:
    if not content_type:
        return fallback
    match = re.search(r"rate=(\d+)", content_type, re.IGNORECASE)
    return int(match.group(1)) if match else fallback


def resample_pcm16_mono(buffer: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate:
        return buffer
    if len(buffer) < 2:
        return b""
    converted, _ = audioop.ratecv(buffer, 2, 1, from_rate, to_rate, None)
    return converted


def signalwire_payload_to_pcm16(payload: bytes, encoding: str) -> bytes:
    if encoding == "audio/x-mulaw":
        return audioop.ulaw2lin(payload, 2)
    if encoding == "audio/x-L16":
        return audioop.byteswap(payload, 2)
    return payload


def pcm16_to_signalwire_payload(pcm: bytes, encoding: str) -> bytes:
    if encoding == "audio/x-mulaw":
        return audioop.lin2ulaw(pcm, 2)
    if encoding == "audio/x-L16":
        return audioop.byteswap(pcm, 2)
    return pcm
