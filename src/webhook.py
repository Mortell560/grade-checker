from __future__ import annotations

from datetime import datetime, timezone
from os import getenv

import httpx


def _to_embed_payload(message: str) -> dict:
    """Convert a plain text message into a Discord embed payload."""
    message = (message or "").strip()
    if not message:
        message = "(empty message)"

    lines = message.splitlines()
    title = lines[0][:256] if lines else "Update"
    description = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    # Discord embed description limit is 4096 characters.
    if len(description) > 4096:
        description = description[:4093] + "..."

    embed: dict = {
        "title": title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if description:
        embed["description"] = description

    return {"content": "", "embeds": [embed]}


async def send_webhook(message: str) -> None:
    webhook_url = getenv("WEBHOOK_URL", "")
    if not webhook_url:
        # No webhook configured; keep behavior non-fatal.
        print(message)
        return

    payload = _to_embed_payload(message)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()