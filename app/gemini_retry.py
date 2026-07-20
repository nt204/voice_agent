from __future__ import annotations

import re


def is_gemini_rate_limit_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if str(code) == "429":
        return True

    status = str(getattr(exc, "status", "") or getattr(exc, "reason", ""))
    text = f"{type(exc).__name__}: {exc} {status}"
    return "RESOURCE_EXHAUSTED" in text or bool(re.search(r"\b429\b", text))


def gemini_retry_delay_seconds(
    exc: Exception,
    *,
    fallback_seconds: float,
    max_delay_seconds: int,
) -> float:
    text = str(exc)
    delay = None
    for pattern in (
        r"retryDelay['\"]?\s*[:=]\s*['\"]?([0-9.]+)s",
        r"retry\s+in\s+([0-9.]+)s",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            delay = float(match.group(1))
            break

    if delay is None:
        delay = fallback_seconds

    max_delay = max(1.0, float(max_delay_seconds or 60))
    return max(1.0, min(delay, max_delay))
