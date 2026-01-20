#!/usr/bin/env python3
"""
Weekly triage for Tool Requests / Friction Log.

Usage:
  python scripts/triage_tool_requests.py
  python scripts/triage_tool_requests.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

CONTEXT_PATH = Path("CONTEXT.md")
TEMPLATE_PATH = Path("templates/tool_spec_template.md")
OUTPUT_DIR = Path("memory/triage")

DEFAULT_LIMIT = 15

IMPACT_SCORE = {"low": 1, "medium": 2, "high": 3}
FREQUENCY_SCORE = {
    "once": 1,
    "weekly": 2,
    "daily": 3,
    "many-times-per-day": 4,
}

THEME_MAP = {
    "calendar": "calendar hygiene",
    "email": "email triage",
    "notion": "notion hygiene",
    "health": "health admin",
    "errands": "errands",
    "planning": "planning",
    "admin": "admin",
    "relationships": "relationships",
    "home": "home operations",
    "finance": "finance admin",
    "other": "other",
}

KEYWORD_MAP = {
    "calendar": "calendar hygiene",
    "invite": "calendar hygiene",
    "meeting": "calendar hygiene",
    "email": "email triage",
    "inbox": "email triage",
    "notion": "notion hygiene",
    "note": "notion hygiene",
    "health": "health admin",
    "doctor": "health admin",
    "appointment": "health admin",
    "plan": "planning",
    "schedule": "planning",
    "bill": "finance admin",
    "finance": "finance admin",
    "home": "home operations",
    "relationship": "relationships",
}


@dataclass
class TriageItem:
    page_id: str
    url: str
    title: str
    description: str
    desired_outcome: str
    frequency: str
    impact: str
    domain: List[str]
    status: str
    last_edited_time: str
    created_time: str
    score: float = 0.0
    theme: str = "other"


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


def _run_codex(prompt: str, *, label: str, verbose: bool, progress: bool) -> str:
    from common.progress import run_command

    try:
        returncode, output = run_command(
            ["codex", "exec", prompt],
            label=label,
            verbose=verbose,
            progress=progress,
        )
    except FileNotFoundError:
        raise SystemExit("codex CLI not found on PATH.")
    if returncode != 0:
        raise SystemExit(f"codex exec failed: {output or 'unknown error'}")
    return output.strip()


def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _query_items(db_id: str, verbose: bool, progress: bool) -> List[Dict[str, Any]]:
    prompt = (
        "Using the Notion MCP, query the database "
        f"{db_id} where Status is 'new' or 'triaging'. "
        "Sort by Last updated time descending. "
        "Return up to 50 results. "
        "Return JSON only (no markdown) as an array of objects with fields: "
        "id, url, title, description, desired_outcome, frequency, impact, "
        "domain (array), status, last_edited_time, created_time."
    )
    output = _run_codex(
        prompt,
        label="Notion MCP: query tool requests",
        verbose=verbose,
        progress=progress,
    )
    data = _extract_json(output)
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    raise SystemExit("Unexpected response format from codex exec.")


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _recency_score(value: str) -> int:
    dt = _parse_time(value)
    if not dt:
        return 0
    now = datetime.now(timezone.utc)
    delta_days = (now - dt).days
    if delta_days <= 7:
        return 2
    if delta_days <= 30:
        return 1
    return 0


def _normalize_item(raw: Dict[str, Any]) -> TriageItem:
    return TriageItem(
        page_id=str(raw.get("id", "")).strip(),
        url=str(raw.get("url", "")).strip(),
        title=str(raw.get("title", "") or "").strip(),
        description=str(raw.get("description", "") or "").strip(),
        desired_outcome=str(raw.get("desired_outcome", "") or "").strip(),
        frequency=str(raw.get("frequency", "") or "once").strip(),
        impact=str(raw.get("impact", "") or "low").strip(),
        domain=list(raw.get("domain") or []),
        status=str(raw.get("status", "") or "").strip(),
        last_edited_time=str(raw.get("last_edited_time", "") or "").strip(),
        created_time=str(raw.get("created_time", "") or "").strip(),
    )


def _score_item(
    item: TriageItem, impact_w: float, freq_w: float, recency_w: float
) -> float:
    impact = IMPACT_SCORE.get(item.impact, 1)
    frequency = FREQUENCY_SCORE.get(item.frequency, 1)
    recency = _recency_score(item.last_edited_time or item.created_time)
    return impact * impact_w + frequency * freq_w + recency * recency_w


def _assign_theme(item: TriageItem) -> str:
    for domain in item.domain:
        key = domain.lower()
        if key in THEME_MAP:
            return THEME_MAP[key]
    text = f"{item.title} {item.description}".lower()
    for keyword, theme in KEYWORD_MAP.items():
        if keyword in text:
            return theme
    return "other"


def _select_items(items: Iterable[TriageItem], limit: int) -> List[TriageItem]:
    sorted_items = sorted(items, key=lambda item: item.score, reverse=True)
    return sorted_items[:limit]


def _cluster_items(items: Iterable[TriageItem]) -> Dict[str, List[TriageItem]]:
    clusters: Dict[str, List[TriageItem]] = defaultdict(list)
    for item in items:
        clusters[item.theme].append(item)
    return clusters


def _theme_score(items: Iterable[TriageItem]) -> float:
    return sum(item.score for item in items)


def _load_template() -> str:
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    raise SystemExit("Missing templates/tool_spec_template.md")


def _tool_recommendations(
    clusters: Dict[str, List[TriageItem]]
) -> List[Dict[str, str]]:
    ordered = sorted(
        clusters.items(), key=lambda pair: _theme_score(pair[1]), reverse=True
    )
    recommendations = []
    for theme, items in ordered[:3]:
        sample = items[0] if items else None
        problem = _theme_problem_statement(theme, sample)
        rec = _theme_recommendation(theme)
        rec["problem_statement"] = problem
        recommendations.append(rec)
    return recommendations


def _theme_problem_statement(theme: str, item: TriageItem | None) -> str:
    seed = item.title if item and item.title else theme
    return (
        f"As Jordane, I want to reduce friction around {theme} "
        f"so that '{seed}' is handled automatically."
    )


def _theme_recommendation(theme: str) -> Dict[str, str]:
    defaults = {
        "tool_name": "Tool Requests Triage Helper",
        "proposed_tools": "Notion MCP",
        "contract_summary": "Short summary of what was reviewed and suggested.",
        "contract_result": "Structured list of actions or changes to apply.",
        "contract_next_actions": "Explicit steps requiring manual approval.",
        "contract_errors": "Any failures, with recommended retry steps.",
        "safety_rules": "Read-only by default; explicit apply step required for writes.",
        "implementation_step_1": "Draft the tool spec and confirm required inputs.",
        "implementation_step_2": "Prototype read-only data fetches and summaries.",
        "implementation_step_3": "Add optional write actions behind an apply flag.",
        "test_smoke": "Run against 3 recent items and verify outputs.",
        "test_edges": "Missing fields, empty domains, and stale items.",
        "rollout_plan": "Run weekly in read-only mode for two weeks before enabling writes.",
    }

    mapping = {
        "calendar hygiene": {
            "tool_name": "Calendar Hygiene Assistant",
            "proposed_tools": "mcp-gsuite-enhanced (Calendar), Notion MCP",
            "contract_summary": "Summary of calendar conflicts and cleanup suggestions.",
            "contract_result": "List of recommended reschedules, taggings, or blocks.",
            "contract_next_actions": "Actions to apply updates to events.",
        },
        "email triage": {
            "tool_name": "Inbox Triage Assistant",
            "proposed_tools": "mcp-gsuite-enhanced (Gmail), Notion MCP",
            "contract_summary": "Summary of inbox noise and cleanup candidates.",
            "contract_result": "Batch rules or labels to apply.",
            "contract_next_actions": "Actions to apply labels or archive.",
        },
        "notion hygiene": {
            "tool_name": "Notion Hygiene Sweep",
            "proposed_tools": "Notion MCP",
            "contract_summary": "Summary of Notion cleanups and re-org suggestions.",
            "contract_result": "List of updates to structure or tags.",
            "contract_next_actions": "Actions to apply Notion updates.",
        },
        "health admin": {
            "tool_name": "Health Admin Coordinator",
            "proposed_tools": "Notion MCP + mcp-gsuite-enhanced (Calendar)",
            "contract_summary": "Summary of health follow-ups and scheduling needs.",
            "contract_result": "Suggested reminders and appointment actions.",
            "contract_next_actions": "Actions to create or move events.",
        },
        "planning": {
            "tool_name": "Planning Support Assistant",
            "proposed_tools": "Notion MCP + mcp-gsuite-enhanced (Calendar)",
            "contract_summary": "Summary of planning gaps and conflicts.",
            "contract_result": "Suggested plan updates or time blocks.",
            "contract_next_actions": "Actions to update plan or calendar.",
        },
        "finance admin": {
            "tool_name": "Finance Admin Helper",
            "proposed_tools": "Notion MCP",
            "contract_summary": "Summary of finance-related friction points.",
            "contract_result": "Suggested bill reminders or tracking updates.",
            "contract_next_actions": "Actions to add reminders or logs.",
        },
        "home operations": {
            "tool_name": "Home Ops Runner",
            "proposed_tools": "Notion MCP",
            "contract_summary": "Summary of home-related friction items.",
            "contract_result": "Suggested checklists or reminders.",
            "contract_next_actions": "Actions to add tasks or reminders.",
        },
    }

    selection = defaults.copy()
    selection.update(mapping.get(theme, {}))
    return selection


def _render_recommendations(recommendations: List[Dict[str, str]]) -> str:
    template = _load_template()
    blocks = []
    for rec in recommendations:
        blocks.append(template.format(**rec))
    return "\n\n".join(blocks)


def _format_items(items: Iterable[TriageItem]) -> str:
    lines = [
        "| Score | Status | Impact | Frequency | Domain | Title | Last Edited |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        domain = ", ".join(item.domain) if item.domain else "other"
        title = item.title or "Untitled"
        last_edit = item.last_edited_time or item.created_time
        lines.append(
            f"| {item.score:.1f} | {item.status} | {item.impact} | "
            f"{item.frequency} | {domain} | {title} | {last_edit} |"
        )
    return "\n".join(lines)


def _format_clusters(clusters: Dict[str, List[TriageItem]]) -> str:
    sections = []
    for theme, items in sorted(
        clusters.items(), key=lambda pair: _theme_score(pair[1]), reverse=True
    ):
        sections.append(f"### {theme} ({len(items)})")
        for item in items:
            title = item.title or "Untitled"
            summary = item.description or item.title
            sections.append(f"- {title}: {summary}")
        sections.append("")
    return "\n".join(sections).strip()


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _apply_triage_updates(
    items: Iterable[TriageItem], verbose: bool, progress: bool
) -> None:
    for item in items:
        if item.status != "new":
            continue
        prompt = (
            "Using the Notion MCP, set Status to 'triaging' "
            f"for the page {item.page_id}."
        )
        _run_codex(
            prompt,
            label="Notion MCP: update status",
            verbose=verbose,
            progress=progress,
        )


def _build_report(
    items: List[TriageItem],
    clusters: Dict[str, List[TriageItem]],
    recommendations: List[Dict[str, str]],
    weights: Dict[str, float],
    total_count: int,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary_lines = [
        f"# Tool Requests Triage - {now}",
        "",
        "## Summary",
        f"- Items reviewed: {total_count}",
        f"- Items selected: {len(items[:DEFAULT_LIMIT])}",
        "",
        "## Scoring weights",
        f"- impact: {weights['impact']}",
        f"- frequency: {weights['frequency']}",
        f"- recency: {weights['recency']}",
        "",
        "## Top items",
        _format_items(items),
        "",
        "## Themes",
        _format_clusters(clusters),
        "",
        "## Recommendations",
        _render_recommendations(recommendations),
        "",
    ]
    return "\n".join(summary_lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Weekly triage for Tool Requests / Friction Log."
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--impact-weight", type=float, default=1.0)
    parser.add_argument("--frequency-weight", type=float, default=1.0)
    parser.add_argument("--recency-weight", type=float, default=1.0)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update Status from new -> triaging in Notion.",
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

    db_id = _read_db_id()
    if not db_id:
        print(
            "Missing TOOL_REQUESTS_DB_ID. Set the env var or update CONTEXT.md.",
            file=sys.stderr,
        )
        return 2

    raw_items = _query_items(db_id, verbose=args.verbose, progress=args.progress)
    items = [_normalize_item(item) for item in raw_items]

    for item in items:
        item.score = _score_item(
            item, args.impact_weight, args.frequency_weight, args.recency_weight
        )
        item.theme = _assign_theme(item)

    selected = _select_items(items, args.limit)
    clusters = _cluster_items(selected)
    recommendations = _tool_recommendations(clusters)

    report = _build_report(
        selected,
        clusters,
        recommendations,
        {
            "impact": args.impact_weight,
            "frequency": args.frequency_weight,
            "recency": args.recency_weight,
        },
        total_count=len(items),
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = OUTPUT_DIR / f"{date_str}.md"
    _write_report(report_path, report)

    if args.apply:
        _apply_triage_updates(selected, verbose=args.verbose, progress=args.progress)

    themes = ", ".join(
        theme
        for theme, _ in sorted(
            clusters.items(), key=lambda pair: _theme_score(pair[1]), reverse=True
        )
    )[:200]
    rec_names = ", ".join([rec["tool_name"] for rec in recommendations])
    print(
        f"Triage saved to {report_path}. "
        f"Items: {len(selected)}. Themes: {themes}. "
        f"Recommendations: {rec_names}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
