from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from fastmcp import FastMCP

# Env var for your n8n "create mood" webhook
# This should be set to: https://mcp-lina.duckdns.org/n8n/webhook/mood-pulse (or your actual URL)
MOOD_WEBHOOK = os.getenv("MOOD_MEMORY_WEBHOOK_URL")

# Env var for the new n8n memory signal webhook
# Example: https://mcp-lina.duckdns.org/n8n/webhook/memory-signal
MEMORY_SIGNAL_WEBHOOK = os.getenv("MEMORY_SIGNAL_WEBHOOK_URL")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_memory_signal_event_text(
    mood: str,
    poke_reaction: str | None,
    poke_action: str | None,
    poke_reason: str | None,
) -> str:
    parts = [f"Mood snapshot: {mood.strip()}"]
    if poke_reaction:
        parts.append(f"reaction={poke_reaction.strip()}")
    if poke_action:
        parts.append(f"action={poke_action.strip()}")
    if poke_reason:
        parts.append(f"reason={poke_reason.strip()}")
    return "; ".join(parts)


async def _post_json(
    client: httpx.AsyncClient,
    label: str,
    url: str,
    payload: dict,
) -> dict:
    try:
        resp = await client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001
        return {
            "target": label,
            "ok": False,
            "error": f"Failed to reach {label}: {exc!r}",
        }

    return {
        "target": label,
        "ok": resp.status_code < 400,
        "status_code": resp.status_code,
        "response_preview": (resp.text or "")[:500],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def create_mood_memory(
        mood: str,
        source: str | None = None,
        timestamp: str | None = None,
        poke_reaction: str | None = None,
        poke_action: str | None = None,
        poke_reason: str | None = None,
    ) -> dict:
        """
        Forward a mood snapshot and Poke's decision into Lina's n8n pipelines.

        This keeps backward compatibility with the legacy mood webhook and also
        writes into the new memory signal pipeline when configured.
        """

        if not MOOD_WEBHOOK and not MEMORY_SIGNAL_WEBHOOK:
            return {
                "ok": False,
                "error": (
                    "Neither MOOD_MEMORY_WEBHOOK_URL nor MEMORY_SIGNAL_WEBHOOK_URL "
                    "is set on the MCP server"
                ),
            }

        effective_timestamp = timestamp or _now_iso()
        effective_source = source or "poke-mcp"

        legacy_payload = {
            "timestamp": effective_timestamp,     # n8n -> sheet: timestamp
            "mood": mood,                         # n8n -> sheet: mood_input
            "poke_reaction": poke_reaction,       # n8n -> sheet: poke_reaction
            "source": effective_source,           # n8n -> sheet: source
            "poke_action": poke_action,           # n8n -> sheet: poke_action
            "poke_reason": poke_reason,           # n8n -> sheet: poke_reason
        }

        mood_tag = mood.strip().lower().replace(" ", "_")[:48]
        signal_payload = {
            "timestamp": effective_timestamp,
            "source": effective_source,
            "event_text": _build_memory_signal_event_text(
                mood=mood,
                poke_reaction=poke_reaction,
                poke_action=poke_action,
                poke_reason=poke_reason,
            ),
            "confidence": 0.82 if poke_reason else 0.72,
            "tags": [tag for tag in ["mood", "poke", mood_tag] if tag],
        }

        results: list[dict] = []
        async with httpx.AsyncClient(timeout=10) as client:
            if MOOD_WEBHOOK:
                results.append(
                    await _post_json(
                        client=client,
                        label="legacy_mood_webhook",
                        url=MOOD_WEBHOOK,
                        payload=legacy_payload,
                    )
                )

            if MEMORY_SIGNAL_WEBHOOK:
                results.append(
                    await _post_json(
                        client=client,
                        label="memory_signal_webhook",
                        url=MEMORY_SIGNAL_WEBHOOK,
                        payload=signal_payload,
                    )
                )

        ok = bool(results) and all(item.get("ok") for item in results)

        return {
            "ok": ok,
            "timestamp": effective_timestamp,
            "source": effective_source,
            "results": results,
        }
