#!/usr/bin/env python3
"""
Flush queued Tool Requests into Notion via Codex MCP.

Usage:
  python scripts/flush_tool_requests_queue.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def _build_prompt(db_id: str, entry: Dict[str, Any]) -> str:
    parts = [
        f"Title='{entry['title']}'",
        f"Description='{entry['description']}'",
        f"Desired outcome='{entry['desired_outcome']}'",
        f"Frequency='{entry['frequency']}'",
        f"Impact='{entry['impact']}'",
        f"Source='{entry.get('source', 'terminal')}'",
    ]

    domains = entry.get("domain") or []
    if isinstance(domains, str):
        domains = [item.strip() for item in domains.split(",") if item.strip()]
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


def _load_queue() -> List[Dict[str, Any]]:
    if not QUEUE_PATH.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with QUEUE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _write_queue(entries: List[Dict[str, Any]]) -> None:
    if not entries:
        if QUEUE_PATH.exists():
            QUEUE_PATH.unlink()
        return
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flush queued Tool Requests into Notion via Codex MCP."
    )
    parser.add_argument("--verbose", action="store_true", help="Show verbose output.")
    parser.add_argument(
        "--progress",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable progress spinners.",
    )
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

    entries = _load_queue()
    if not entries:
        print("Queue is empty.")
        return 0

    remaining: List[Dict[str, Any]] = []
    failures = 0

    for entry in entries:
        prompt = _build_prompt(db_id, entry)
        try:
            returncode, output = _send_to_notion(
                prompt, verbose=args.verbose, progress=args.progress
            )
        except FileNotFoundError:
            print(
                "codex CLI not found; queue retained. Install Codex or add it to PATH.",
                file=sys.stderr,
            )
            return 1
        if returncode == 0:
            continue
        failures += 1
        remaining.append(entry)

    _write_queue(remaining)

    if failures:
        print_warn(
            f"Flushed with {failures} failure(s); remaining items kept in queue."
        )
        return 1

    print_ok("Flushed all queued entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
