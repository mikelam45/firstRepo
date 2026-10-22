"""Parse Thunderbird/local mbox messages for the review pipeline."""

from __future__ import annotations

import hashlib
import mailbox
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from typing import Any


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _body_text(msg: Message) -> str:
    if msg.is_multipart():
        parts: list[str] = []
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    parts.append(payload.decode(charset, errors="replace"))
                except Exception:  # noqa: BLE001
                    parts.append(payload.decode("utf-8", errors="replace"))
        if parts:
            return "\n".join(parts).strip()
        return ""

    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except Exception:  # noqa: BLE001
        return payload.decode("utf-8", errors="replace").strip()


def parse_mbox(mbox_path: str | Path) -> list[dict[str, Any]]:
    """Return normalized message dicts from an mbox file."""
    path = Path(mbox_path)
    if not path.is_file():
        raise FileNotFoundError(f"mbox not found: {path}")

    box = mailbox.mbox(str(path))
    messages: list[dict[str, Any]] = []
    try:
        for idx, msg in enumerate(box, start=1):
            raw = msg.as_bytes()
            email_hash = hashlib.sha256(raw).hexdigest()
            message_id = _decode_header(msg.get("Message-ID")) or f"local-{idx}"
            headers = {
                "from": _decode_header(msg.get("From")),
                "to": _decode_header(msg.get("To")),
                "subject": _decode_header(msg.get("Subject")),
                "date": _decode_header(msg.get("Date")),
                "message_id": message_id,
            }
            body = _body_text(msg)
            messages.append(
                {
                    "index": idx,
                    "message_id": message_id,
                    "email_hash": email_hash,
                    "headers": headers,
                    "subject": headers["subject"],
                    "body": body,
                }
            )
    finally:
        box.close()
    return messages
