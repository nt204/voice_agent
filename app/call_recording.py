import re
import wave
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, config
from app.database import CallRecordingRow, db_session
from app.logging_utils import register_call_log, unregister_call_log


class CallRecorder:
    def __init__(
        self,
        call_id: str,
        sample_rate: int,
        phone_number: str | None = None,
        to_number: str | None = None,
        stream_id: str | None = None,
        codec: str | None = None,
        direction: str = "inbound",
    ):
        self.call_id = call_id
        self.sample_rate = sample_rate
        self.phone_number = phone_number or call_id
        self.to_number = to_number
        self.stream_id = stream_id
        self.codec = codec
        self.direction = direction
        self.base_name = f"{_safe_name(self.phone_number)}_{_timestamp()}"
        root = _recording_root()
        self.inbound_path = root / "inbound" / f"{self.base_name}.wav"
        self.outbound_path = root / "outbound" / f"{self.base_name}.wav"
        self.log_path = root / "logs" / f"{self.base_name}.log"
        self.inbound_path.parent.mkdir(parents=True, exist_ok=True)
        self.outbound_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._inbound = _open_pcm16_wav(self.inbound_path, sample_rate)
        self._outbound = _open_pcm16_wav(self.outbound_path, sample_rate)
        self.closed = False
        register_call_log(call_id, self.log_path)
        self._insert_db_row()

    def write_inbound(self, pcm: bytes) -> None:
        if not self.closed and pcm:
            self._inbound.writeframes(pcm)

    def write_outbound(self, pcm: bytes) -> None:
        if not self.closed and pcm:
            self._outbound.writeframes(pcm)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._inbound.close()
        self._outbound.close()
        self._finish_db_row()
        unregister_call_log(self.call_id)

    def _insert_db_row(self) -> None:
        with db_session() as session:
            session.merge(
                CallRecordingRow(
                    id=self.base_name,
                    call_id=self.call_id,
                    stream_id=self.stream_id,
                    from_number=self.phone_number,
                    to_number=self.to_number,
                    direction=self.direction,
                    sales_status="open",
                    status="active",
                    codec=self.codec,
                    sample_rate=self.sample_rate,
                    inbound_path=str(self.inbound_path),
                    outbound_path=str(self.outbound_path),
                    log_path=str(self.log_path),
                )
            )

    def _finish_db_row(self) -> None:
        with db_session() as session:
            row = session.get(CallRecordingRow, self.base_name)
            if not row:
                return
            row.status = "completed"
            row.ended_at = datetime.utcnow()
            row.inbound_bytes = _path_size(self.inbound_path)
            row.outbound_bytes = _path_size(self.outbound_path)
            row.log_bytes = _path_size(self.log_path)


def _recording_root() -> Path:
    root = Path(config.call_recordings_dir)
    if not root.is_absolute():
        root = BASE_DIR / root
    return root


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _open_pcm16_wav(path: Path, sample_rate: int) -> wave.Wave_write:
    wav = wave.open(str(path), "wb")
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    return wav


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "unknown-call"


def _path_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0
