from datetime import datetime
from pathlib import Path
import sys

LOG_PATH = Path(__file__).resolve().parent.parent / "call-debug.log"


_call_logs = {}


def register_call_log(call_id: str, log_path: Path) -> None:
    _call_logs[call_id] = Path(log_path)


def unregister_call_log(call_id: str) -> None:
    _call_logs.pop(call_id, None)


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    _safe_stdout(message)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
    
    import re
    match = re.search(r"^\[([^\]]+)\]", message)
    if match:
        cid = match.group(1)
        if cid in _call_logs:
            try:
                with _call_logs[cid].open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass


def _safe_stdout(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or "utf-8"
            safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
            print(safe_message, flush=True)
        except Exception:
            try:
                safe_message = message.encode("ascii", errors="backslashreplace").decode("ascii")
                print(safe_message, flush=True)
            except Exception:
                pass

