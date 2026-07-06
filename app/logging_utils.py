from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "call-debug.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(message, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
