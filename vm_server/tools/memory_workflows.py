from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from fastmcp import FastMCP

# Distiller ingestion endpoint (supports old env var for compatibility).
MEMORY_DISTILLER_WEBHOOK_URL = (
    os.getenv("MEMORY_DISTILLER_WEBHOOK_URL")
    or os.getenv("MEMORY_SIGNAL_WEBHOOK_URL")
)

# Recall endpoint.
MEMORY_RECALL_WEBHOOK_URL = os.getenv("MEMORY_RECALL_WEBHOOK_URL")

# Optional shared webhook auth header.
N8N_WEBHOOK_AUTH_HEADER = os.getenv("N8N_WEBHOOK_AUTH_HEADER", "Authorization")
N8N_WEBHOOK_AUTH_VALUE = os.getenv("N8N_WEBHOOK_AUTH_VALUE")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_AUTH_VALUE:
        headers[N8N_WEBHOOK_AUTH_HEADER] = N8N_WEBHOOK_AUTH_VALUE
    return headers


async def _post_json(url: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=_build_headers())
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Failed to reach webhook: {exc!r}",
        }

    return {
        "ok": resp.status_code < 400,
        "status_code": resp.status_code,
        "response_preview": (resp.text or "")[:500],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def call_memory_distiller_daily(
        event_text: str,
        source: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        timestamp: str | None = None,
    ) -> dict:
        """
        Send a memory signal into the Memory Distiller Daily workflow queue.
        """
        if not MEMORY_DISTILLER_WEBHOOK_URL:
            return {
                "ok": False,
                "error": (
                    "MEMORY_DISTILLER_WEBHOOK_URL is not set "
                    "(MEMORY_SIGNAL_WEBHOOK_URL is also accepted)."
                ),
            }

        text = (event_text or "").strip()
        if not text:
            return {"ok": False, "error": "event_text is required."}

        score = 0.72 if confidence is None else float(confidence)
        payload = {
            "event_text": text,
            "source": (source or "poke-mcp").strip(),
            "timestamp": timestamp or _now_iso(),
            "confidence": max(0.0, min(1.0, score)),
            "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        }

        result = await _post_json(MEMORY_DISTILLER_WEBHOOK_URL, payload)
        return {
            "ok": result.get("ok", False),
            "webhook": "memory-distiller-daily",
            "payload": payload,
            "result": result,
        }

    @mcp.tool
    async def call_memory_recall_brief_to_poke(
        query: str | None = None,
        topic: str | None = None,
        limit: int = 8,
    ) -> dict:
        """
        Trigger the Memory Recall Brief to Poke workflow.
        """
        if not MEMORY_RECALL_WEBHOOK_URL:
            return {
                "ok": False,
                "error": "MEMORY_RECALL_WEBHOOK_URL is not set.",
            }

        safe_limit = max(1, min(int(limit), 20))
        effective_query = (query or topic or "").strip()
        payload = {
            "query": effective_query,
            "topic": effective_query,
            "limit": safe_limit,
            "timestamp": _now_iso(),
        }

        result = await _post_json(MEMORY_RECALL_WEBHOOK_URL, payload)
        return {
            "ok": result.get("ok", False),
            "webhook": "memory-recall-brief-to-poke",
            "payload": payload,
            "result": result,
        }
