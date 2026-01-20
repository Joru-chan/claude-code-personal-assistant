#!/usr/bin/env python3
"""
Fast capture for Tool Requests / Friction Log.

Usage:
  python scripts/capture_tool_request.py "Annoyed by X"
  python scripts/capture_tool_request.py "Annoyed by X" --desired-outcome "Y"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from common.progress import print_ok, print_warn, run_command

QUEUE_PATH = Path("memory/tool_requests_queue.jsonl")
CONTEXT_PATH = Path("CONTEXT.md")


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _read_db_id() -> str | None:
    db_id = os.getenv("TOOL_REQUESTS_DB_ID")
    if db_id:
        return db_id
    if not CONTEXT_PATH.exists():
        return None
    content = CONTEXT_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"Tool Requests / Friction Log DB ID:\s*`([^`]+)`", content
    )
    return match.group(1) if match else None


def _split_domains(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _short_title(text: str, limit: int = 80) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    return " ".join(text.replace('"', "'").split())


def _infer_desired_outcome(complaint: str) -> str:
    title = _short_title(complaint)
    return f"Resolve: {title}"


def _queue_entry(entry: Dict[str, Any]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def _build_prompt(db_id: str, entry: Dict[str, Any]) -> str:
    parts = [
        f"Title='{entry['title']}'",
        f"Description='{entry['description']}'",
        f"Desired outcome='{entry['desired_outcome']}'",
        f"Frequency='{entry['frequency']}'",
        f"Impact='{entry['impact']}'",
        f"Source='{entry['source']}'",
    ]

    domains = entry.get("domain") or []
    if domains:
        parts.append(f"Domain=[{', '.join(domains)}]")
    if entry.get("link"):
        parts.append(f"Link(s)='{entry['link']}'")
    if entry.get("notes"):
        parts.append(f"Notes / constraints='{entry['notes']}'")

    properties = ", ".join(parts)
    return (
        "Create a new entry in the Notion database "
        f"{db_id} with properties: {properties}. "
        "Return the created page URL."
    )


def _send_to_notion(prompt: str, verbose: bool, progress: bool) -> tuple[int, str]:
    return run_command(
        ["codex", "exec", prompt],
        label="Notion MCP: create tool request",
        verbose=verbose,
        progress=progress,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a Tool Request into Notion with offline fallback."
    )
    parser.add_argument("complaint", help="Short complaint or friction note")
    parser.add_argument("--desired-outcome")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output.")
    parser.add_argument(
        "--progress",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable progress spinners.",
    )
    parser.add_argument(
        "--frequency",
        default="once",
        choices=["once", "weekly", "daily", "many-times-per-day"],
    )
    parser.add_argument("--impact", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--domain", help="Comma-separated domains")
    parser.add_argument(
        "--source", default="terminal", choices=["poke", "terminal", "other"]
    )
    parser.add_argument("--link")
    parser.add_argument("--notes")

    args = parser.parse_args()
    _load_env()
    if not os.getenv("NOTION_TOKEN"):
        print(
            "NOTION_TOKEN not set; relying on existing Codex MCP config.",
            file=sys.stderr,
        )

    db_id = _read_db_id()
    if not db_id:
        print(
            "Missing TOOL_REQUESTS_DB_ID. Set the env var or update CONTEXT.md.",
            file=sys.stderr,
        )
        return 2

    complaint = _normalize_text(args.complaint) or ""
    if not complaint:
        print("Complaint cannot be empty.", file=sys.stderr)
        return 2

    desired_outcome = _normalize_text(args.desired_outcome) or _infer_desired_outcome(
        complaint
    )

    entry = {
        "title": _short_title(complaint),
        "description": complaint,
        "desired_outcome": desired_outcome,
        "frequency": args.frequency,
        "impact": args.impact,
        "domain": _split_domains(args.domain),
        "source": args.source,
        "link": _normalize_text(args.link),
        "notes": _normalize_text(args.notes),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
    }

    prompt = _build_prompt(db_id, entry)

    try:
        returncode, output = _send_to_notion(
            prompt, verbose=args.verbose, progress=args.progress
        )
    except FileNotFoundError:
        _queue_entry(entry)
        print("codex CLI not found; queued entry locally.")
        return 1

    if returncode == 0:
        output = (output or "").strip()
        print_ok(output or "Captured tool request in Notion.")
        return 0

    _queue_entry(entry)
    if output:
        print_warn(f"Notion capture failed; queued entry. Error: {output.strip()}")
    else:
        print_warn("Notion capture failed; queued entry.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
