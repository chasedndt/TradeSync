"""Fleet job errors, made safe to store and plain to read.

A Hermes job's last error is whatever its script printed: a traceback, a
shell complaint, a delivery failure, sometimes the job's own report. Before
it leaves the host it is redacted (anything shaped like a token, key or
webhook) and cut to length. On the dashboard it is reduced to one sentence
naming the cause when the cause is recognisable.
"""

from __future__ import annotations

import re

MAX_ERROR_CHARS = 1500

_DISCORD_TOKEN = re.compile(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,40}")
_PREFIXED_KEY = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}")
_LABELLED = re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password)(\s*[:=]\s*|\s+)([^\s\"',;]{8,})")
_WEBHOOK = re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+")
_HEX_KEY = re.compile(r"\b0x[a-fA-F0-9]{64}\b")
_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Timeout)\b")


def redact(text: object) -> str | None:
    """The text with secret-shaped substrings replaced, cut to ``MAX_ERROR_CHARS``; None when empty."""
    if text is None or text == "":
        return None
    out = str(text)
    out = _WEBHOOK.sub("https://discord.com/api/webhooks/[redacted]", out)
    out = _DISCORD_TOKEN.sub("[redacted]", out)
    out = _PREFIXED_KEY.sub("[redacted]", out)
    out = _LABELLED.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", out)
    out = _HEX_KEY.sub("[redacted]", out)
    return out[:MAX_ERROR_CHARS]


def diagnose(error: object) -> str | None:
    """One plain sentence on why a job failed, or the first meaningful line when the cause is unknown."""
    if error is None or error == "":
        return None
    text = str(error)
    if "\r" in text or "\\r'" in text or re.search(r"pipefail\s*:\s*invalid option", text):
        return "The script has Windows (CRLF) line endings, so bash cannot run it; it needs LF line endings."
    if "Temporary failure in name resolution" in text or "Name or service not known" in text:
        host = re.search(r"connect to host ([\w.-]+)", text)
        where = f" for {host.group(1)}" if host else ""
        return f"A network name lookup failed inside WSL{where}, so the job could not reach it."
    if "Quant Integrity Hold" in text:
        codes = re.findall(r"- `([a-z_]+)`", text)
        listed = ", ".join(codes) if codes else "see the health report"
        return f"Integrity hold ({listed}). The watchdog exits non-zero while any integrity issue stands."
    start = text.rfind("Traceback (most recent call last)")
    if start >= 0:
        lines = [line.strip() for line in text[start:].splitlines() if line.strip()]
        exception = next((line for line in reversed(lines) if _EXCEPTION_LINE.match(line)), None)
        if exception:
            return f"Python error: {exception[:200]}"
        files = re.findall(r'File "([^"]+)"', text)
        where = f" in {files[-1].rsplit('/', 1)[-1]}" if files else ""
        return f"Python error{where}; the recorded error was cut off before the exception line."
    code = re.search(r"exited with code (\d+)", text)
    if code and re.search(r'"ok"\s*:\s*true', text):
        return f"The script reported ok but exited with code {code.group(1)}."
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.lower().startswith(("script exited", "stdout:", "stderr:")):
            return stripped[:200]
    return text.strip()[:200] or None
