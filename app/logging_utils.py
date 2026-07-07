from datetime import datetime
from pathlib import Path
import sys

LOG_PATH = Path(__file__).resolve().parent.parent / "call-debug.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    _safe_stdout(message)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def _safe_stdout(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_message = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe_message, flush=True)
