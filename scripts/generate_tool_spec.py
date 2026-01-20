#!/usr/bin/env python3
"""
Generate a tool spec from a complaint or a Notion Tool Request entry.

Usage:
  python scripts/generate_tool_spec.py "Annoyed by X"
  python scripts/generate_tool_spec.py --notion-id <page_id>
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

TEMPLATE_PATH = Path("templates/tool_spec_full.md")
RUN_OPTIONS = {"verbose": False, "progress": True}


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _run_codex(prompt: str, *, label: str) -> str:
    from common.progress import run_command

    try:
        returncode, output = run_command(
            ["codex", "exec", prompt],
            label=label,
            verbose=RUN_OPTIONS["verbose"],
            progress=RUN_OPTIONS["progress"],
        )
    except FileNotFoundError:
        raise RuntimeError("codex CLI not found on PATH.")

    if returncode != 0:
        raise RuntimeError(output or "codex exec failed.")
    return output.strip()


def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:60] if slug else "tool_spec"


def _read_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise RuntimeError("Missing templates/tool_spec_full.md")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _fetch_notion_entry(page_id: str) -> Dict[str, Any]:
    prompt = (
        "Using the Notion MCP, retrieve the Tool Requests entry "
        f"with page_id {page_id}. "
        "Return JSON only with fields: title, description, desired_outcome, "
        "frequency, impact, domain (array), notes, link, source, status."
    )
    output = _run_codex(prompt, label="Notion MCP: fetch tool request")
    data = _extract_json(output)
    if isinstance(data, dict):
        return data
    raise RuntimeError("Unexpected Notion response format.")


def _build_prompt(input_payload: Dict[str, Any]) -> str:
    payload = json.dumps(input_payload, ensure_ascii=True)
    return (
        "You are drafting a concise tool specification for a personal assistant "
        "OS. Use the provided input JSON and return JSON only with these keys: "
        "tool_name, tool_slug, problem_statement, assumptions, clarifying_questions "
        "(array), architecture, contract_summary, contract_result, "
        "contract_next_actions, contract_errors, safety_policy, data_sources "
        "(array), plan_steps (array of 3), test_smoke, test_edges, poke_ask, "
        "poke_confirm, notes. Keep it safe-by-default (read-only until apply). "
        f"Input JSON: {payload}"
    )


def _fallback_spec(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    complaint = input_payload.get("complaint") or "Unspecified complaint"
    return {
        "tool_name": "Tool Idea Spec",
        "tool_slug": _slugify(complaint),
        "problem_statement": f"As Jordane, I want to reduce: {complaint}.",
        "assumptions": "Assumes access to relevant MCP data sources.",
        "clarifying_questions": ["What outcome matters most for this issue?"],
        "architecture": "Local script with MCP integrations as needed.",
        "contract_summary": "Short summary of findings and proposals.",
        "contract_result": "Structured list of proposed actions.",
        "contract_next_actions": "Explicit approvals required before writes.",
        "contract_errors": "Any failures with retry guidance.",
        "safety_policy": "Read-only by default; apply requires explicit confirmation.",
        "data_sources": ["Notion", "Calendar", "Email"],
        "plan_steps": [
            "Draft the spec and confirm inputs.",
            "Prototype read-only fetch + summary.",
            "Add apply step with explicit confirmation.",
        ],
        "test_smoke": "Run against one real complaint.",
        "test_edges": "Missing fields, no data, and MCP unavailable.",
        "poke_ask": "I can draft a tool spec for this. Want me to proceed?",
        "poke_confirm": "Reply 'confirm' to apply any changes.",
        "notes": "Fallback spec generated without LLM output.",
    }


def _format_list(items: List[str]) -> str:
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


def _format_steps(items: List[str]) -> str:
    if not items:
        return "1) Define the problem.\n2) Draft a minimal plan.\n3) Confirm outputs."
    lines = []
    for index, item in enumerate(items[:3], start=1):
        lines.append(f"{index}) {item}")
    return "\n".join(lines)


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_spec(
    complaint: str,
    notion_item: Dict[str, Any] | None,
    errors: List[str],
) -> Dict[str, Any]:
    input_payload = {
        "complaint": complaint,
        "title": notion_item.get("title") if notion_item else "",
        "description": notion_item.get("description") if notion_item else "",
        "desired_outcome": notion_item.get("desired_outcome") if notion_item else "",
        "frequency": notion_item.get("frequency") if notion_item else "",
        "impact": notion_item.get("impact") if notion_item else "",
        "domain": notion_item.get("domain") if notion_item else [],
        "notes": notion_item.get("notes") if notion_item else "",
        "link": notion_item.get("link") if notion_item else "",
        "source": notion_item.get("source") if notion_item else "terminal",
    }

    try:
        response = _run_codex(
            _build_prompt(input_payload),
            label="Codex: draft tool spec",
        )
        spec = _extract_json(response)
        if not isinstance(spec, dict):
            raise RuntimeError("LLM response was not a JSON object.")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        spec = _fallback_spec(input_payload)

    if not spec.get("tool_slug"):
        spec["tool_slug"] = _slugify(spec.get("tool_name", complaint))
    if not spec.get("tool_name"):
        spec["tool_name"] = "Tool Idea Spec"

    spec["tool_slug"] = _slugify(spec["tool_slug"])
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a tool spec from a complaint or Notion item."
    )
    parser.add_argument("complaint", nargs="?", help="Free-text complaint")
    parser.add_argument("--notion-id", help="Notion page ID for Tool Request")
    parser.add_argument("--output-dir", default="memory/tool_specs")
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json", "both"],
        help="Output format",
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

    if not args.complaint and not args.notion_id:
        print("Provide a complaint string or --notion-id.", file=sys.stderr)
        return 2

    global RUN_OPTIONS
    RUN_OPTIONS = {"verbose": args.verbose, "progress": args.progress}

    errors: List[str] = []
    notion_item: Dict[str, Any] | None = None
    complaint = args.complaint or ""

    if args.notion_id:
        try:
            notion_item = _fetch_notion_entry(args.notion_id)
            complaint = (
                notion_item.get("description")
                or notion_item.get("title")
                or complaint
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Notion fetch failed: {exc}")

    if not complaint:
        complaint = f"Tool request from Notion page {args.notion_id or 'unknown'}."

    spec = _build_spec(complaint, notion_item, errors)

    tool_slug = spec.get("tool_slug") or _slugify(spec.get("tool_name", complaint))
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_base = Path(args.output_dir) / f"{date_prefix}_{tool_slug}"

    generated_at = datetime.now(timezone.utc).isoformat()
    template = _read_template()

    markdown = template.format(
        tool_name=spec.get("tool_name", "Tool Idea Spec"),
        tool_slug=tool_slug,
        source="notion" if args.notion_id else "complaint",
        generated_at=generated_at,
        problem_statement=spec.get("problem_statement", ""),
        assumptions=spec.get("assumptions", ""),
        clarifying_questions=_format_list(spec.get("clarifying_questions", [])),
        architecture=spec.get("architecture", ""),
        contract_summary=spec.get("contract_summary", ""),
        contract_result=spec.get("contract_result", ""),
        contract_next_actions=spec.get("contract_next_actions", ""),
        contract_errors=spec.get("contract_errors", ""),
        safety_policy=spec.get("safety_policy", ""),
        data_sources=_format_list(spec.get("data_sources", [])),
        plan_steps=_format_steps(spec.get("plan_steps", [])),
        test_smoke=spec.get("test_smoke", ""),
        test_edges=spec.get("test_edges", ""),
        poke_ask=spec.get("poke_ask", ""),
        poke_confirm=spec.get("poke_confirm", ""),
        notes=spec.get("notes", ""),
        errors=_format_list(errors),
    )

    json_payload = {
        "generated_at": generated_at,
        "source": "notion" if args.notion_id else "complaint",
        "input": {
            "complaint": complaint,
            "notion_id": args.notion_id,
            "notion_item": notion_item,
        },
        "spec": spec,
        "errors": errors,
    }

    if args.format in ("markdown", "both"):
        _write_file(output_base.with_suffix(".md"), markdown)
    if args.format in ("json", "both"):
        _write_file(
            output_base.with_suffix(".json"),
            json.dumps(json_payload, indent=2, ensure_ascii=True),
        )

    if args.format == "markdown":
        print(f"Tool spec saved to {output_base.with_suffix('.md')}")
    elif args.format == "json":
        print(f"Tool spec saved to {output_base.with_suffix('.json')}")
    else:
        print(
            f"Tool spec saved to {output_base.with_suffix('.md')} "
            f"and {output_base.with_suffix('.json')}"
        )

    if errors:
        print("Warnings:")
        for error in errors:
            print(f"- {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
