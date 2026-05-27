from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


MAX_TEXT_CHARS = int(os.getenv("LOG_MAX_TEXT_CHARS", "500"))
USE_COLOR = os.getenv("NO_COLOR") is None

COLORS = {
    "CHAT": "\033[96m",
    "ORCH": "\033[95m",
    "AGENT": "\033[94m",
    "TOOL": "\033[92m",
    "STAGE": "\033[93m",
    "BUILD": "\033[36m",
    "RETRY": "\033[33m",
    "ERROR": "\033[91m",
    "OK": "\033[32m",
    "RESET": "\033[0m",
}


def _color(label: str, text: str) -> str:
    """Apply ANSI color codes to log text based on category.
    
    Args:
        label: Log category (CHAT, AGENT, TOOL, etc.)
        text: Text to colorize
        
    Returns:
        Colored text if color enabled, otherwise plain text
    """
    if not USE_COLOR:
        return text
    return f"{COLORS.get(label, '')}{text}{COLORS['RESET']}"


def _shorten(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Truncate long text and replace newlines for logging.
    
    Args:
        text: Text to shorten
        limit: Maximum characters to keep
        
    Returns:
        Shortened text with indication of truncation
    """
    text = text.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated {len(text) - limit} chars>"


def _summarize(value: Any) -> Any:
    """Recursively summarize log payload values, hiding sensitive data.
    
    Args:
        value: Value to summarize
        
    Returns:
        Summarized value with char counts and file lists for sensitive fields
    """
    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return _shorten(value)

    if isinstance(value, list):
        if len(value) <= 12 and all(isinstance(item, str) for item in value):
            return value
        return {"count": len(value), "sample": [_summarize(item) for item in value[:5]]}

    if isinstance(value, dict):
        sensitive_keys = {"content", "new_content", "raw_reply", "angular_code_files", "java_code_files"}
        summarized: dict[str, Any] = {}
        for key, item in value.items():
            if key in sensitive_keys:
                if isinstance(item, str):
                    summarized[f"{key}_chars"] = len(item)
                elif isinstance(item, dict):
                    summarized[f"{key}_count"] = len(item)
                    summarized[f"{key}_files"] = list(item.keys())[:20]
                else:
                    summarized[key] = _summarize(item)
            else:
                summarized[key] = _summarize(item)
        return summarized

    return _shorten(str(value))


def log_event(category: str, event: str, payload: dict[str, Any] | None = None, status: str | None = None) -> None:
    """Log structured event with category, timestamp, and colored output.
    
    Args:
        category: Event category (CHAT, AGENT, TOOL, BUILD, ERROR, etc.)
        event: Event name/description
        payload: Optional dict of event metadata (summarized for logging)
        status: Optional status (ok, fail, retry) to include in output
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    status_text = f" {status.upper()}" if status else ""
    prefix = _color(category, f"[{timestamp}] [{category}]{status_text} {event}")
    if not payload:
        print(prefix)
        return

    safe_payload = _summarize(payload)
    print(f"{prefix} {json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)}")
