#!/usr/bin/env python3
"""
Universal router entrypoint for natural language requests.

Usage:
  python scripts/agent.py "what should we build next?"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common.prefs import load_prefs, save_prefs
from fetch_tool_requests import fetch_candidates
from llm_decider import decide as llm_decide
from tool_request_scoring import score_candidate

ROUTE_LIST = ("list wishes", "show tool requests", "list tool requests", "show wishes")
ROUTE_PICK = ("triage",)
ROUTE_SCAFFOLD = ("scaffold", "start project", "start a project", "create tool")
ROUTE_DEPLOY = ("deploy", "ship", "push to vm")
PLAN_ONLY_PHRASES = (
    "start with the plan",
    "start with plan",
    "just plan",
    "plan only",
    "outline",
    "what's the plan",
    "what is the plan",
)
PLAN_ONLY_BLOCKED_ACTIONS = [
    "write_files",
    "scaffold",
    "notion_update",
    "deploy",
    "run_commands",
]
ROUTE_SEARCH = ("search", "find", "lookup")
MUTATING_TOOL_RE = re.compile(r"(apply|deploy|write|create|set|update|delete)")
EDIT_NOTION_KEYWORDS = (
    "edit",
    "update",
    "change",
    "fix",
    "correct",
    "rename",
    "set",
    "add tag",
    "remove tag",
)
PREFS_KEYWORDS = ("auto apply", "auto-apply")
LAST_PREVIEW_PATH = Path("memory/last_preview.json")
PREVIEW_TTL_HOURS = 24
FULFIL_BEST_TRIGGERS = (
    "make a wish",
    "fulfil a wish",
    "fulfill a wish",
    "what should we build",
    "what should we build now",
    "what should we build next",
    "make one of the tools i wished for",
    "fulfil a wish",
    "fulfill a wish",
    "pick something to build",
    "choose something to build",
    "next tool to build",
    "build next",
    "build something",
)
FULFIL_VERBS = ("make", "build", "implement", "fulfil", "fulfill", "create")
WISH_CAPTURE_PHRASES = ("i wish", "wish i could", "i wish you could")
STOPWORDS = {
    "the",
    "and",
    "or",
    "to",
    "a",
    "an",
    "of",
    "in",
    "for",
    "with",
    "is",
    "are",
    "be",
    "it",
    "this",
    "that",
    "my",
    "your",
    "from",
    "on",
    "by",
    "as",
    "at",
    "like",
    "me",
    "lets",
    "let",
    "take",
    "make",
    "build",
    "implement",
    "create",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "new-tool"


def _slugify_identifier(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug:
        return "tool"
    if slug[0].isdigit():
        return f"tool_{slug}"
    return slug


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...<truncated>"


def _run_command(cmd: List[str]) -> Dict[str, Any]:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": _truncate(result.stdout.strip()),
        "stderr": _truncate(result.stderr.strip()),
    }


def _extract_quoted_phrases(text: str) -> List[str]:
    matches = re.finditer(r"(?:^|\s|:)[\"']([^\"']+)[\"']", text)
    return [match.group(1).strip() for match in matches if match.group(1).strip()]


def _extract_search_query(text: str) -> str:
    quoted = _extract_quoted_phrases(text)
    if quoted:
        return quoted[0]
    match = re.search(
        r"(?:search|find|lookup)\s+(?:wishes|tool requests|requests|for|about)?\s*(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if match and match.group(1).strip():
        return match.group(1).strip()
    return text


def _extract_fulfil_query(text: str) -> str | None:
    lower = text.lower()
    match = re.search(r"(?:closest to|closest match|closest)\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"(?:make|build|implement|fulfil|fulfill|create)\s+(?:the\s+)?(?:tool|thing|workflow|system)?\s*(?:for|to|that|which|:)?\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if match:
        candidate = match.group(1).strip()
        if candidate.lower().startswith("a wish"):
            return None
        return candidate
    if any(trigger in lower for trigger in FULFIL_BEST_TRIGGERS):
        return None
    return None


def _detect_fulfil_mode(request: str) -> Tuple[str | None, str | None]:
    lower = request.lower()
    if any(trigger in lower for trigger in FULFIL_BEST_TRIGGERS):
        return "fulfil_best", None
    if any(verb in lower for verb in FULFIL_VERBS):
        query = _extract_fulfil_query(request)
        if query:
            return "fulfil_match", query
        return "fulfil_best", None
    return None, None


def _is_wish_capture_request(request: str) -> bool:
    lower = request.lower()
    if any(phrase in lower for phrase in WISH_CAPTURE_PHRASES):
        if any(verb in lower for verb in FULFIL_VERBS):
            return False
        return True
    return False


def _is_plan_only_request(request: str) -> bool:
    lower = request.lower()
    if any(phrase in lower for phrase in PLAN_ONLY_PHRASES):
        return True
    return bool(re.search(r"\bplan\b", lower))


def _prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    response = input(prompt).strip().lower()
    if not response:
        return default_yes
    return response in ("y", "yes")


def _build_requirements_file(slug: str, requirements: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path("memory/requirements") / f"{today}_{slug}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(requirements.strip() + "\n", encoding="utf-8")
    return str(path)


def _extract_page_id(text: str) -> str | None:
    match = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(r"([0-9a-f]{32})", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _should_set_prefs(request: str) -> bool:
    lower = request.lower()
    return any(keyword in lower for keyword in PREFS_KEYWORDS)


def _should_correct_tool_request(request: str) -> bool:
    lower = request.lower()
    if "tool request" in lower or "tool requests" in lower or "friction log" in lower:
        return any(word in lower for word in ("fix", "correct", "change", "update", "edit"))
    return False


def _should_edit_notion(request: str) -> bool:
    lower = request.lower()
    if "notion" not in lower:
        return False
    return any(keyword in lower for keyword in EDIT_NOTION_KEYWORDS)


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if token and token not in STOPWORDS]




def _save_last_preview(payload: Dict[str, Any]) -> None:
    LAST_PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_PREVIEW_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_last_preview() -> Dict[str, Any] | None:
    if not LAST_PREVIEW_PATH.exists():
        return None
    return json.loads(LAST_PREVIEW_PATH.read_text(encoding="utf-8"))


def _preview_is_fresh(timestamp: str) -> bool:
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - dt
    return age.total_seconds() <= PREVIEW_TTL_HOURS * 3600


def _parse_correction_request(request: str) -> Tuple[str | None, str | None]:
    quoted = _extract_quoted_phrases(request)
    if len(quoted) >= 2:
        return quoted[0], quoted[1]
    match = re.search(
        r"(?:change|correct|fix|update)\s+(.+?)\s+to\s+(.+)",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, None


def _replace_case_insensitive(text: str, old: str, new: str) -> str:
    pattern = re.compile(re.escape(old), flags=re.IGNORECASE)
    if not pattern.search(text):
        return new
    return pattern.sub(new, text, count=1)


def _simplify_query(text: str) -> str:
    tokens = _tokenize(text)
    if "physical" in tokens and "items" in tokens:
        return "physical items"
    if len(tokens) >= 2:
        return " ".join(tokens[:2])
    return tokens[0] if tokens else ""


def _fallback_queries(query: str) -> List[str]:
    tokens = _tokenize(query)
    if not tokens:
        return []
    options = []
    if len(tokens) >= 3:
        options.append(" ".join(tokens[:3]))
    if len(tokens) >= 2:
        options.append(" ".join(tokens[:2]))
    options.append(tokens[0])
    options.append(" ".join(tokens[-2:]))
    seen = set()
    deduped = []
    for item in options:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _load_playbook_excerpt() -> str:
    path = Path("docs/AGENT_PLAYBOOK.md")
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return "\n".join(content.splitlines()[:80])


def _rank_candidates(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for item in candidates:
        scoring = score_candidate(query, item)
        ranked.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description"),
                "desired_outcome": item.get("desired_outcome"),
                "domain": item.get("domain"),
                "status": item.get("status"),
                "created_time": item.get("created_time"),
                "total_score": scoring["total_score"],
                "score_breakdown": scoring["breakdown"],
                "matches": scoring["matches"],
            }
        )
    ranked.sort(key=lambda entry: entry.get("total_score", 0.0), reverse=True)
    return ranked


def _summarize_candidates(ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summarized = []
    for cand in ranked:
        rationale = "low overlap"
        rationale_tokens = cand.get("matches", {}).get("top_tokens") or []
        if rationale_tokens:
            rationale = ", ".join(rationale_tokens[:5])
        else:
            breakdown = cand.get("breakdown") or cand.get("score_breakdown") or {}
            positive = []
            for key, value in breakdown.items():
                if isinstance(value, (int, float)) and value > 0:
                    positive.append(f"{key}={value}")
            if positive:
                rationale = ", ".join(positive[:3])
        summary = dict(cand)
        summary["rationale"] = rationale
        summarized.append(summary)
    return summarized


def _prepare_fulfilment(request_text: str, query: str | None) -> Dict[str, Any]:
    fetch = fetch_candidates(limit=15, query=query)
    candidates = fetch.get("result", {}).get("candidates", [])
    decision = llm_decide(
        request_text,
        candidates,
        profile=None,
        playbook=_load_playbook_excerpt(),
    )
    ranked = decision.get("ranked") or _rank_candidates(query or request_text, candidates)
    return {"fetch": fetch, "candidates": candidates, "decision": decision, "ranked": ranked}


def _clean_domain_tags(
    title: str, desired_outcome: str, domain: List[str]
) -> Tuple[List[str], List[str]]:
    title_lower = title.lower()
    desired_lower = desired_outcome.lower()
    if isinstance(domain, str):
        domain_list = [part.strip() for part in domain.split(",") if part.strip()]
    else:
        domain_list = [str(tag).strip() for tag in domain if str(tag).strip()]
    cleanup_needed = any(term in title_lower for term in ("physical items", "inventory"))
    mentions_text = any(term in desired_lower for term in ("ocr", "text", "article", "articles"))
    if not cleanup_needed or mentions_text:
        return domain_list, []
    cleaned = [tag for tag in domain_list if tag.lower() not in ("reading", "knowledge")]
    removed = [tag for tag in domain_list if tag.lower() in ("reading", "knowledge")]
    return cleaned, removed


def _write_v0_checklist(slug: str, title: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path("memory/plans") / f"{today}_{slug}_v0.md"
    content = (
        f"# v0 Checklist: {title}\n\n"
        "- [ ] Confirm inputs/outputs contract\n"
        "- [ ] Implement read-only path\n"
        "- [ ] Add apply/confirm path\n"
        "- [ ] Add smoke tests\n"
        "- [ ] Deploy and verify\n"
    )
    _write_text(path, content)
    return str(path)


def _scaffold_tool_only(request: str) -> Dict[str, Any]:
    slug = _slugify_identifier(request)
    tools_dir = Path("vm_server/tools")
    module_path = tools_dir / f"{slug}.py"
    registry_path = tools_dir / "registry.py"
    created: List[str] = []

    if module_path.exists():
        return {
            "slug": slug,
            "module": str(module_path),
            "files_created": created,
            "skipped": True,
        }

    tools_dir.mkdir(parents=True, exist_ok=True)
    module_content = f"""from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def {slug}(request: str | None = None) -> dict:
        \"\"\"Stub tool generated by scripts/agent.py (interactive).\"\"\"
        return {{
            "summary": "Stub tool created. Implementation pending.",
            "result": {{"request": request}},
            "next_actions": ["Implement tool logic in vm_server/tools/{slug}.py"],
            "errors": [],
        }}
"""
    module_path.write_text(module_content, encoding="utf-8")
    created.append(str(module_path))

    if not registry_path.exists():
        raise RuntimeError(f"Missing registry: {registry_path}")
    _update_registry(slug, registry_path)
    created.append(str(registry_path))

    return {
        "slug": slug,
        "module": str(module_path),
        "files_created": created,
    }


def _compute_confidence(
    request: str,
    candidate: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    old_phrase: str | None,
) -> Tuple[float, List[Dict[str, Any]]]:
    score = 0.0
    breakdown: List[Dict[str, Any]] = []
    title = str(candidate.get("title") or "")
    lower = request.lower()

    if old_phrase and old_phrase.lower() in title.lower():
        score += 0.45
        breakdown.append(
            {
                "rule": "quoted_phrase_match",
                "score": 0.45,
                "details": f"Matched '{old_phrase}' in title.",
            }
        )

    candidate_index = next(
        (idx for idx, item in enumerate(candidates) if item is candidate),
        None,
    )
    if candidate_index is not None and candidate_index <= 1:
        score += 0.20
        breakdown.append(
            {
                "rule": "recency_bonus",
                "score": 0.20,
                "details": "Candidate is among the two newest results.",
            }
        )

    if ("not " in lower and " but " in lower) or ("instead of" in lower) or ("misinterpreted" in lower):
        score += 0.20
        breakdown.append(
            {
                "rule": "negation_pattern",
                "score": 0.20,
                "details": "Detected correction/negation phrasing.",
            }
        )

    request_tokens = set(_tokenize(request))
    candidate_tokens = set(_tokenize(title))
    overlap = request_tokens.intersection(candidate_tokens)
    if len(overlap) >= 2:
        score += 0.15
        breakdown.append(
            {
                "rule": "keyword_overlap",
                "score": 0.15,
                "details": f"Overlapping tokens: {', '.join(sorted(overlap))}.",
            }
        )

    score = max(0.0, min(score, 1.0))
    return score, breakdown


def _route(request: str, force_scaffold: bool, accept_id: str | None) -> Tuple[str, Dict[str, Any]]:
    lower = request.lower()
    if force_scaffold:
        return "scaffold", {}
    if accept_id:
        return "fulfil_accept", {}
    if lower.strip() in ("apply that", "apply last preview", "apply last correction"):
        return "apply_last", {}
    if _should_set_prefs(request):
        return "prefs", {}
    if _should_correct_tool_request(request):
        return "correct_tool_request", {}
    call_match = re.match(
        r"^\s*call\s+([a-z0-9_-]+)\s*(\{.*\})?\s*$",
        request,
        flags=re.IGNORECASE,
    )
    if call_match:
        return "call", {
            "tool": call_match.group(1).lower(),
            "args": call_match.group(2),
        }
    fulfil_mode, fulfil_query = _detect_fulfil_mode(request)
    if fulfil_mode:
        return fulfil_mode, {"query": fulfil_query}
    if _is_wish_capture_request(request):
        return "wish_hint", {}
    if any(word in lower for word in ROUTE_DEPLOY):
        return "deploy", {}
    if _should_edit_notion(request):
        return "edit_notion", {}
    if any(word in lower for word in ROUTE_SCAFFOLD):
        return "scaffold", {}
    if any(word in lower for word in ROUTE_PICK):
        return "fetch", {}
    if any(word in lower for word in ROUTE_SEARCH):
        return "search", {"query": _extract_search_query(request)}
    if any(word in lower for word in ROUTE_LIST):
        return "list", {}
    return "unknown", {}


def _parse_mcp_response(raw: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid MCP JSON output: {exc}") from exc
    result = payload.get("result") or {}
    structured = result.get("structuredContent")
    if structured:
        return structured
    content = result.get("content") or []
    for block in content:
        text = block.get("text")
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("Missing structuredContent in MCP response")


def _run_mcp_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    cmd = ["./vm/mcp_curl.sh", tool, json.dumps(args)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "MCP tool call failed")
    return _parse_mcp_response(result.stdout)


def _extract_edit_query(request: str) -> str:
    query = _extract_search_query(request)
    query = re.sub(r"\b(in\s+notion|notion)\b", "", query, flags=re.IGNORECASE).strip()
    return query


def _strip_quotes(text: str) -> str:
    return text.strip().strip("\"'").strip()


def _parse_edit_intent(request: str) -> Tuple[Dict[str, Any], List[str]]:
    updates: Dict[str, Any] = {"properties": {}}
    notes: List[str] = []
    lower = request.lower()

    title_match = re.search(
        r"(?:rename|change|update|set)\s+title(?:\s+from)?\s+(.+?)\s+to\s+(.+)",
        request,
        flags=re.IGNORECASE,
    )
    if title_match:
        updates["title"] = _strip_quotes(title_match.group(2))

    status_match = re.search(r"set\s+status\s+(.+)", request, flags=re.IGNORECASE)
    if status_match:
        updates["properties"]["Status"] = _strip_quotes(status_match.group(1))

    desc_match = re.search(r"set\s+description\s+(.+)", request, flags=re.IGNORECASE)
    if desc_match:
        updates["properties"]["Description"] = _strip_quotes(desc_match.group(1))

    tag_match = re.search(
        r"(?:add|set)\s+tag[s]?\s+(.+)",
        request,
        flags=re.IGNORECASE,
    )
    if tag_match:
        raw_tags = _strip_quotes(tag_match.group(1))
        tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        if tags:
            updates["properties"]["Domain"] = tags

    if not updates.get("title") and not updates["properties"]:
        notes.append("No update intent detected; specify title/status/description/tag.")

    return updates, notes


def _parse_prefs_request(request: str, prefs: Dict[str, object]) -> Dict[str, object]:
    lower = request.lower()
    updated = dict(prefs)
    if "enable auto apply" in lower or "enable auto-apply" in lower:
        updated["auto_apply_enabled"] = True
    if "disable auto apply" in lower or "disable auto-apply" in lower:
        updated["auto_apply_enabled"] = False
    match = re.search(r"auto apply threshold to\s*([0-9.]+)", lower)
    if match:
        try:
            value = float(match.group(1))
        except ValueError:
            value = prefs.get("auto_apply_threshold", 0.92)
        updated["auto_apply_threshold"] = max(0.0, min(value, 1.0))
    return updated


def _build_correction_updates(
    candidate: Dict[str, Any], old_text: str | None, new_text: str | None
) -> Dict[str, Any]:
    title = str(candidate.get("title") or "")
    if new_text:
        if old_text:
            new_title = _replace_case_insensitive(title, old_text, new_text)
        else:
            new_title = new_text
        return {"title": new_title, "properties": {}}
    return {"properties": {}}


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_fulfil_spec(
    item: Dict[str, Any],
    source_text: str | None,
    requirements: str | None,
    inputs_and_capture: Dict[str, Any] | None,
    tool_name: str,
) -> str:
    title = item.get("title") or "Tool Request"
    desired = item.get("desired_outcome") or "TBD"
    url = item.get("url") or ""
    requirements_text = requirements or "None"
    source_note = source_text or ""
    inputs_and_capture = inputs_and_capture or {}
    inputs = inputs_and_capture.get("supported_inputs") or ["TBD"]
    user_inputs = inputs_and_capture.get("what_user_provides_v0") or ["TBD"]
    unsupported = inputs_and_capture.get("unsupported_yet") or []
    examples = [
        f"./vm/mcp_curl.sh {tool_name} '{{\"input\":\"example\"}}'",
        f"./vm/mcp_curl.sh {tool_name} '{{\"input\":\"example\",\"dry_run\":true}}'",
        f"./vm/mcp_curl.sh {tool_name} '{{}}'",
    ]
    how_to_use = (
        "## How to use\n"
        "Inputs:\n"
        + "".join(f"- {item}\n" for item in inputs)
        + "\nWhat the user provides (v0):\n"
        + "".join(f"- {item}\n" for item in user_inputs)
        + ("\nNot supported yet:\n" + "".join(f"- {item}\n" for item in unsupported) if unsupported else "")
        + "\nExamples:\n"
        + "".join(f"- `{example}`\n" for example in examples)
    )
    return (
        f"# Tool Spec: {title}\n\n"
        "## Source\n"
        f"- Tool request URL: {url}\n"
        f"- Original request: {source_note}\n\n"
        "## Problem\n"
        f"{title}\n\n"
        "## Desired outcome\n"
        f"{desired}\n\n"
        "## Requirements\n"
        f"{requirements_text}\n\n"
        f"{how_to_use}\n\n"
        "## v0 proposal\n"
        "- Build the smallest useful workflow first.\n"
        "- Read-only by default; require explicit apply for writes.\n"
    )


def _build_fulfil_plan(
    item: Dict[str, Any],
    requirements: str | None,
    plan_outline: List[str] | None,
    inputs_and_capture: Dict[str, Any] | None,
) -> str:
    title = item.get("title") or "Tool Request"
    url = item.get("url") or ""
    requirements_text = requirements or "None"
    if not plan_outline:
        plan_outline = [
            "Confirm inputs/outputs contract.",
            "Implement read-only path first.",
            "Add explicit apply/confirm path for writes.",
        ]
    inputs_and_capture = inputs_and_capture or {}
    inputs = inputs_and_capture.get("supported_inputs") or ["TBD"]
    capture = inputs_and_capture.get("what_user_provides_v0") or ["TBD"]
    return (
        f"# Plan: {title}\n\n"
        f"- Source URL: {url}\n"
        f"- Requirements: {requirements_text}\n\n"
        "## Inputs / UX / Capture\n"
        "Supported inputs:\n"
        + "".join(f"- {item}\n" for item in inputs)
        + "\nUser provides (v0):\n"
        + "".join(f"- {item}\n" for item in capture)
        + "\n## Steps (v0)\n"
        + "".join(f"{idx + 1}) {step}\n" for idx, step in enumerate(plan_outline))
    )


def _write_fulfilment_files(
    item: Dict[str, Any],
    source_text: str | None,
    requirements: str | None,
    plan_outline: List[str] | None,
    inputs_and_capture: Dict[str, Any] | None,
) -> Tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(str(item.get("title") or "tool-request"))
    tool_name = _slugify_identifier(str(item.get("title") or "tool_request"))
    spec_path = Path("memory/specs") / f"{today}_{slug}.md"
    plan_path = Path("memory/plans") / f"{today}_{slug}.md"
    _write_text(
        spec_path,
        _build_fulfil_spec(item, source_text, requirements, inputs_and_capture, tool_name),
    )
    _write_text(
        plan_path,
        _build_fulfil_plan(item, requirements, plan_outline, inputs_and_capture),
    )
    return str(spec_path), str(plan_path)


def _pick_request_by_id(items: List[Dict[str, Any]], page_id: str) -> Dict[str, Any] | None:
    for item in items:
        if str(item.get("id")) == page_id:
            return item
    return None


def _extract_summary_value(summary: Dict[str, Any], key: str) -> Any:
    for prop, value in summary.items():
        if prop.strip().lower() == key.strip().lower():
            if isinstance(value, dict) and "value" in value:
                return value.get("value")
            return value
    return None


def _resolve_tool_request(page_id: str, source_text: str | None) -> Dict[str, Any]:
    if source_text:
        search = _run_mcp_tool("tool_requests_search", {"query": source_text, "limit": 10})
        items = search.get("result", {}).get("items", [])
        candidate = _pick_request_by_id(items, page_id)
        if candidate:
            return candidate
    page = _run_mcp_tool("notion_get_page", {"page_id": page_id})
    summary = page.get("result", {}).get("page", {}).get("properties", {})
    title = page.get("result", {}).get("page", {}).get("title") or ""
    url = page.get("result", {}).get("page", {}).get("url") or ""
    desired = _extract_summary_value(summary, "Desired outcome") or ""
    description = _extract_summary_value(summary, "Description") or ""
    domain = _extract_summary_value(summary, "Domain") or []
    status = _extract_summary_value(summary, "Status") or ""
    impact = _extract_summary_value(summary, "Impact") or ""
    frequency = _extract_summary_value(summary, "Frequency") or ""
    return {
        "id": page_id,
        "title": title,
        "url": url,
        "description": description,
        "desired_outcome": desired,
        "domain": domain,
        "status": status,
        "impact": impact,
        "frequency": frequency,
    }


def _update_registry(slug: str, registry_path: Path) -> bool:
    lines = registry_path.read_text(encoding="utf-8").splitlines()
    updated = False

    def insert_in_block(start_predicate, end_predicate) -> None:
        nonlocal updated
        start = next((i for i, line in enumerate(lines) if start_predicate(line)), None)
        if start is None:
            raise RuntimeError("Registry import block not found.")
        end = next((i for i in range(start + 1, len(lines)) if end_predicate(lines[i])), None)
        if end is None:
            raise RuntimeError("Registry block end not found.")
        if any(re.search(rf"\\b{re.escape(slug)}\\b", line) for line in lines[start + 1 : end]):
            return
        lines.insert(end, f"    {slug},")
        updated = True

    insert_in_block(lambda line: line.strip() == "from tools import (", lambda line: line.strip() == ")")
    insert_in_block(lambda line: line.strip() == "for module in (", lambda line: line.strip() == "):")

    if updated:
        registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return updated


def _scaffold_tool(request: str) -> Dict[str, Any]:
    slug = _slugify(request)
    module_slug = _slugify_identifier(request)
    tools_dir = Path("vm_server/tools")
    module_path = tools_dir / f"{module_slug}.py"
    registry_path = tools_dir / "registry.py"
    created: List[str] = []

    if module_path.exists():
        raise RuntimeError(f"Tool already exists: {module_path}")

    tools_dir.mkdir(parents=True, exist_ok=True)
    module_content = f"""from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def {module_slug}(request: str | None = None) -> dict:
        \"\"\"Stub tool generated by scripts/agent.py.\"\"\"
        return {{
            "summary": "Stub tool created. Implementation pending.",
            "result": {{"request": request}},
            "next_actions": ["Implement tool logic in vm_server/tools/{module_slug}.py"],
            "errors": [],
        }}
"""
    module_path.write_text(module_content, encoding="utf-8")
    created.append(str(module_path))

    if not registry_path.exists():
        raise RuntimeError(f"Missing registry: {registry_path}")
    _update_registry(module_slug, registry_path)
    created.append(str(registry_path))

    today = datetime.now().strftime("%Y-%m-%d")
    spec_path = Path("memory/specs") / f"{today}_{slug}.md"
    plan_path = Path("memory/plans") / f"{today}_{slug}.md"
    spec_content = (
        f"# Tool Spec: {request}\n\n"
        "## Problem\n"
        f"{request}\n\n"
        "## v0 proposal\n"
        "- Create a minimal read-only tool.\n"
        "- Add an explicit apply/confirm step before any writes.\n"
    )
    plan_content = (
        f"# Plan: {request}\n\n"
        "1) Confirm inputs/outputs contract.\n"
        "2) Implement read-only path first.\n"
        "3) Add tests + apply path with confirmation.\n"
    )
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec_content, encoding="utf-8")
    plan_path.write_text(plan_content, encoding="utf-8")
    created.append(str(spec_path))
    created.append(str(plan_path))

    return {
        "slug": module_slug,
        "module": str(module_path),
        "spec_path": str(spec_path),
        "plan_path": str(plan_path),
        "files_created": created,
    }


def _run_interactive(
    request_text: str,
    args: argparse.Namespace,
    prefs: Dict[str, object],
    plan_only: bool,
) -> int:
    fulfil_mode, fulfil_query = _detect_fulfil_mode(request_text)
    if not fulfil_mode:
        print("Interactive mode only supports fulfilment requests (make/build/implement...).")
        return 1

    auto_confirm = bool(args.auto_confirm) or bool(prefs.get("interactive_auto_confirm"))
    query = fulfil_query if fulfil_mode == "fulfil_match" else None

    prepared = _prepare_fulfilment(request_text, query)
    candidates = prepared["ranked"][:5]
    decision = prepared["decision"]
    selected_id = decision.get("selected_id")
    selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
    confidence = float(decision.get("confidence") or 0.0)

    if not selected and candidates:
        selected = _pick_request_by_id(prepared["candidates"], candidates[0].get("id"))

    if not selected:
        print("No matching tool requests found.")
        return 1

    def _rationale(candidate: Dict[str, Any]) -> str:
        tokens = candidate.get("matches", {}).get("top_tokens") or candidate.get("top_tokens") or []
        if tokens:
            return ", ".join(tokens[:5])
        breakdown = candidate.get("breakdown") or candidate.get("score_breakdown") or {}
        positive = []
        for key, value in breakdown.items():
            if isinstance(value, (int, float)) and value > 0:
                positive.append(f"{key}={value}")
        return ", ".join(positive[:3]) if positive else "low overlap"

    def print_selection() -> None:
        print("\nSelected tool request:")
        print(f"- Title: {selected.get('title')}")
        print(f"- URL: {selected.get('url')}")
        desired_text = selected.get("desired_outcome") or ""
        desired_snippet = desired_text[:160] + ("..." if len(desired_text) > 160 else "")
        print(f"- Desired outcome: {desired_snippet}")
        print(f"- Confidence: {confidence:.2f}")
        if candidates:
            print("\nTop candidates:")
            for idx, cand in enumerate(candidates[:3], start=1):
                score = cand.get("total_score") or cand.get("score") or 0
                print(f"  {idx}) {cand.get('title')} (score {score:.2f}) — {_rationale(cand)}")

    print_selection()
    if not plan_only:
        attempts = 0
        while not auto_confirm and not _prompt_yes_no("\nUse selected tool request? [Y/n] "):
            attempts += 1
            choice = input("Pick 1/2/3 or type a new search phrase: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                picked = candidates[idx]
                selected = _pick_request_by_id(prepared["candidates"], picked.get("id")) or picked
                print_selection()
                break
        elif choice:
            request_text = choice
            prepared = _prepare_fulfilment(request_text, choice)
            candidates = prepared["ranked"][:5]
            decision = prepared["decision"]
            selected_id = decision.get("selected_id")
            selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
            confidence = float(decision.get("confidence") or 0.0)
            if selected:
                print_selection()
                continue
        if attempts >= 2:
            print("Selection still ambiguous. Exiting safely.")
            summary = {
                "summary": "Interactive fulfilment cancelled.",
                "result": {"selected": None, "candidates": candidates[:3]},
                "next_actions": ["Re-run with a more specific description."],
                "errors": [],
            }
            print("\n" + json.dumps(summary, indent=2))
            return 1

    if args.requirements:
        requirements = args.requirements.strip()
    elif plan_only:
        requirements = ""
    else:
        if auto_confirm and not sys.stdin.isatty():
            requirements = ""
        else:
            try:
                requirements = input(
                    "Any extra requirements/constraints? (press enter for none) "
                ).strip()
            except EOFError:
                requirements = ""

    plan_outline = decision.get("plan_outline") or []
    inputs_and_capture = decision.get("inputs_and_capture") or {}

    print("\nDraft plan:")
    for idx, step in enumerate(plan_outline, start=1):
        print(f"{idx}) {step}")
    questions = decision.get("questions") or []
    if questions:
        print("\nQuestions:")
        for question in questions:
            print(f"- {question}")
    if inputs_and_capture:
        print("\nInputs / capture contract:")
        for label, value in inputs_and_capture.items():
            if isinstance(value, list):
                for item in value:
                    print(f"- {label}: {item}")
            else:
                print(f"- {label}: {value}")

    if plan_only:
        summary = {
            "summary": "PLAN_ONLY: plan-only request. No files written.",
            "result": {
                "selected": selected,
                "requirements": requirements,
                "plan_outline": plan_outline,
                "inputs_and_capture": inputs_and_capture,
                "questions": questions,
                "plan_only": True,
                "blocked_actions": PLAN_ONLY_BLOCKED_ACTIONS,
            },
            "next_actions": ["Re-run with --execute to write spec/plan files."],
            "errors": [],
        }
        print("\n" + json.dumps(summary, indent=2))
        return 0

    proceed = _prompt_yes_no("Proceed to write spec/plan files now? [y/N] ", default_yes=False)
    if not proceed:
        summary = {
            "summary": "Selection confirmed. Plan drafted; no files written.",
            "result": {
                "selected": selected,
                "requirements": requirements,
                "plan_outline": plan_outline,
                "inputs_and_capture": inputs_and_capture,
            },
            "next_actions": ["Re-run with --execute to write spec/plan files."],
            "errors": [],
        }
        print("\n" + json.dumps(summary, indent=2))
        return 0

    slug = _slugify(selected.get("title") or "tool-request")
    requirements_path = _build_requirements_file(slug, requirements)
    spec_path, plan_path = _write_fulfilment_files(
        selected,
        request_text,
        requirements,
        plan_outline,
        inputs_and_capture,
    )

    summary = {
        "summary": "Interactive fulfilment complete.",
        "result": {
            "selected": selected,
            "spec_path": spec_path,
            "plan_path": plan_path,
            "requirements_path": requirements_path,
        },
        "next_actions": ["Review spec/plan, then implement when ready."],
        "errors": [],
    }
    print("\n" + json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Route natural language requests.")
    parser.add_argument("request", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--scaffold", action="store_true")
    parser.add_argument("--auto-apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--auto-confirm", action="store_true")
    parser.add_argument("--accept", dest="accept_id")
    parser.add_argument("--from", dest="from_text", default="")
    parser.add_argument("--requirements", default="")
    args = parser.parse_args()

    request_text = " ".join(args.request).strip()
    if args.from_text:
        request_text = args.from_text.strip()
    dry_run = True
    if args.execute:
        dry_run = False
    if args.dry_run:
        dry_run = True

    prefs = load_prefs()

    plan_only = _is_plan_only_request(request_text)
    if plan_only:
        dry_run = True

    route, route_meta = _route(request_text, args.scaffold, args.accept_id)
    if route in ("fulfil_best", "fulfil_match") and args.interactive:
        return _run_interactive(request_text, args, prefs, plan_only)
    errors: List[str] = []
    next_actions: List[str] = []
    result: Dict[str, Any] = {
        "route": route,
        "request": request_text,
        "commands": [],
        "files_created": [],
    }

    plan_allowed_routes = {
        "list",
        "search",
        "fetch",
        "fulfil_best",
        "fulfil_match",
    }
    plan_only_mode = plan_only and route not in plan_allowed_routes

    if plan_only_mode:
        result["plan_only"] = True
        result["blocked_actions"] = PLAN_ONLY_BLOCKED_ACTIONS
        next_actions.append("PLAN_ONLY: no writes performed.")
        summary = f"PLAN_ONLY route: {route}. Dry-run: {dry_run}."
        output = {
            "summary": summary,
            "result": result,
            "next_actions": next_actions,
            "errors": errors,
        }
        print(json.dumps(output, indent=2))
        return 0

    try:

                dt = datetime.fromisoformat(timestamp)
            except ValueError:
                return False
            age = datetime.now(timezone.utc) - dt
            return age.total_seconds() <= PREVIEW_TTL_HOURS * 3600


        def _parse_correction_request(request: str) -> Tuple[str | None, str | None]:
            quoted = _extract_quoted_phrases(request)
            if len(quoted) >= 2:
                return quoted[0], quoted[1]
            match = re.search(
                r"(?:change|correct|fix|update)\s+(.+?)\s+to\s+(.+)",
                request,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1).strip(), match.group(2).strip()
            return None, None


        def _replace_case_insensitive(text: str, old: str, new: str) -> str:
            pattern = re.compile(re.escape(old), flags=re.IGNORECASE)
            if not pattern.search(text):
                return new
            return pattern.sub(new, text, count=1)


        def _simplify_query(text: str) -> str:
            tokens = _tokenize(text)
            if "physical" in tokens and "items" in tokens:
                return "physical items"
            if len(tokens) >= 2:
                return " ".join(tokens[:2])
            return tokens[0] if tokens else ""


        def _fallback_queries(query: str) -> List[str]:
            tokens = _tokenize(query)
            if not tokens:
                return []
            options = []
            if len(tokens) >= 3:
                options.append(" ".join(tokens[:3]))
            if len(tokens) >= 2:
                options.append(" ".join(tokens[:2]))
            options.append(tokens[0])
            options.append(" ".join(tokens[-2:]))
            seen = set()
            deduped = []
            for item in options:
                if item and item not in seen:
                    seen.add(item)
                    deduped.append(item)
            return deduped


        def _load_playbook_excerpt() -> str:
            path = Path("docs/AGENT_PLAYBOOK.md")
            if not path.exists():
                return ""
            content = path.read_text(encoding="utf-8")
            return "\n".join(content.splitlines()[:80])


        def _rank_candidates(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            ranked = []
            for item in candidates:
                scoring = score_candidate(query, item)
                ranked.append(
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "description": item.get("description"),
                        "desired_outcome": item.get("desired_outcome"),
                        "domain": item.get("domain"),
                        "status": item.get("status"),
                        "created_time": item.get("created_time"),
                        "total_score": scoring["total_score"],
                        "score_breakdown": scoring["breakdown"],
                        "matches": scoring["matches"],
                    }
                )
            ranked.sort(key=lambda entry: entry.get("total_score", 0.0), reverse=True)
            return ranked


        def _summarize_candidates(ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            summarized = []
            for cand in ranked:
                rationale = "low overlap"
                rationale_tokens = cand.get("matches", {}).get("top_tokens") or []
                if rationale_tokens:
                    rationale = ", ".join(rationale_tokens[:5])
                else:
                    breakdown = cand.get("breakdown") or cand.get("score_breakdown") or {}
                    positive = []
                    for key, value in breakdown.items():
                        if isinstance(value, (int, float)) and value > 0:
                            positive.append(f"{key}={value}")
                    if positive:
                        rationale = ", ".join(positive[:3])
                summary = dict(cand)
                summary["rationale"] = rationale
                summarized.append(summary)
            return summarized


        def _prepare_fulfilment(request_text: str, query: str | None) -> Dict[str, Any]:
            fetch = fetch_candidates(limit=15, query=query)
            candidates = fetch.get("result", {}).get("candidates", [])
            decision = llm_decide(
                request_text,
                candidates,
                profile=None,
                playbook=_load_playbook_excerpt(),
            )
            ranked = decision.get("ranked") or _rank_candidates(query or request_text, candidates)
            return {"fetch": fetch, "candidates": candidates, "decision": decision, "ranked": ranked}


        def _clean_domain_tags(
            title: str, desired_outcome: str, domain: List[str]
        ) -> Tuple[List[str], List[str]]:
            title_lower = title.lower()
            desired_lower = desired_outcome.lower()
            if isinstance(domain, str):
                domain_list = [part.strip() for part in domain.split(",") if part.strip()]
            else:
                domain_list = [str(tag).strip() for tag in domain if str(tag).strip()]
            cleanup_needed = any(term in title_lower for term in ("physical items", "inventory"))
            mentions_text = any(term in desired_lower for term in ("ocr", "text", "article", "articles"))
            if not cleanup_needed or mentions_text:
                return domain_list, []
            cleaned = [tag for tag in domain_list if tag.lower() not in ("reading", "knowledge")]
            removed = [tag for tag in domain_list if tag.lower() in ("reading", "knowledge")]
            return cleaned, removed


        def _write_v0_checklist(slug: str, title: str) -> str:
            today = datetime.now().strftime("%Y-%m-%d")
            path = Path("memory/plans") / f"{today}_{slug}_v0.md"
            content = (
                f"# v0 Checklist: {title}\n\n"
                "- [ ] Confirm inputs/outputs contract\n"
                "- [ ] Implement read-only path\n"
                "- [ ] Add apply/confirm path\n"
                "- [ ] Add smoke tests\n"
                "- [ ] Deploy and verify\n"
            )
            _write_text(path, content)
            return str(path)


        def _scaffold_tool_only(request: str) -> Dict[str, Any]:
            slug = _slugify_identifier(request)
            tools_dir = Path("vm_server/tools")
            module_path = tools_dir / f"{slug}.py"
            registry_path = tools_dir / "registry.py"
            created: List[str] = []

            if module_path.exists():
                return {
                    "slug": slug,
                    "module": str(module_path),
                    "files_created": created,
                    "skipped": True,
                }

            tools_dir.mkdir(parents=True, exist_ok=True)
            module_content = f"""from __future__ import annotations

        from fastmcp import FastMCP


        def register(mcp: FastMCP) -> None:
            @mcp.tool
            async def {slug}(request: str | None = None) -> dict:
                \"\"\"Stub tool generated by scripts/agent.py (interactive).\"\"\"
                return {{
                    "summary": "Stub tool created. Implementation pending.",
                    "result": {{"request": request}},
                    "next_actions": ["Implement tool logic in vm_server/tools/{slug}.py"],
                    "errors": [],
                }}
        """
            module_path.write_text(module_content, encoding="utf-8")
            created.append(str(module_path))

            if not registry_path.exists():
                raise RuntimeError(f"Missing registry: {registry_path}")
            _update_registry(slug, registry_path)
            created.append(str(registry_path))

            return {
                "slug": slug,
                "module": str(module_path),
                "files_created": created,
            }


        def _compute_confidence(
            request: str,
            candidate: Dict[str, Any],
            candidates: List[Dict[str, Any]],
            old_phrase: str | None,
        ) -> Tuple[float, List[Dict[str, Any]]]:
            score = 0.0
            breakdown: List[Dict[str, Any]] = []
            title = str(candidate.get("title") or "")
            lower = request.lower()

            if old_phrase and old_phrase.lower() in title.lower():
                score += 0.45
                breakdown.append(
                    {
                        "rule": "quoted_phrase_match",
                        "score": 0.45,
                        "details": f"Matched '{old_phrase}' in title.",
                    }
                )

            candidate_index = next(
                (idx for idx, item in enumerate(candidates) if item is candidate),
                None,
            )
            if candidate_index is not None and candidate_index <= 1:
                score += 0.20
                breakdown.append(
                    {
                        "rule": "recency_bonus",
                        "score": 0.20,
                        "details": "Candidate is among the two newest results.",
                    }
                )

            if ("not " in lower and " but " in lower) or ("instead of" in lower) or ("misinterpreted" in lower):
                score += 0.20
                breakdown.append(
                    {
                        "rule": "negation_pattern",
                        "score": 0.20,
                        "details": "Detected correction/negation phrasing.",
                    }
                )

            request_tokens = set(_tokenize(request))
            candidate_tokens = set(_tokenize(title))
            overlap = request_tokens.intersection(candidate_tokens)
            if len(overlap) >= 2:
                score += 0.15
                breakdown.append(
                    {
                        "rule": "keyword_overlap",
                        "score": 0.15,
                        "details": f"Overlapping tokens: {', '.join(sorted(overlap))}.",
                    }
                )

            score = max(0.0, min(score, 1.0))
            return score, breakdown


        def _route(request: str, force_scaffold: bool, accept_id: str | None) -> Tuple[str, Dict[str, Any]]:
            lower = request.lower()
            if force_scaffold:
                return "scaffold", {}
            if accept_id:
                return "fulfil_accept", {}
            if lower.strip() in ("apply that", "apply last preview", "apply last correction"):
                return "apply_last", {}
            if _should_set_prefs(request):
                return "prefs", {}
            if _should_correct_tool_request(request):
                return "correct_tool_request", {}
            call_match = re.match(
                r"^\s*call\s+([a-z0-9_-]+)\s*(\{.*\})?\s*$",
                request,
                flags=re.IGNORECASE,
            )
            if call_match:
                return "call", {
                    "tool": call_match.group(1).lower(),
                    "args": call_match.group(2),
                }
            fulfil_mode, fulfil_query = _detect_fulfil_mode(request)
            if fulfil_mode:
                return fulfil_mode, {"query": fulfil_query}
            if _is_wish_capture_request(request):
                return "wish_hint", {}
            if any(word in lower for word in ROUTE_DEPLOY):
                return "deploy", {}
            if _should_edit_notion(request):
                return "edit_notion", {}
            if any(word in lower for word in ROUTE_SCAFFOLD):
                return "scaffold", {}
            if any(word in lower for word in ROUTE_PICK):
                return "fetch", {}
            if any(word in lower for word in ROUTE_SEARCH):
                return "search", {"query": _extract_search_query(request)}
            if any(word in lower for word in ROUTE_LIST):
                return "list", {}
            return "unknown", {}


        def _parse_mcp_response(raw: str) -> Dict[str, Any]:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid MCP JSON output: {exc}") from exc
            result = payload.get("result") or {}
            structured = result.get("structuredContent")
            if structured:
                return structured
            content = result.get("content") or []
            for block in content:
                text = block.get("text")
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        continue
            raise RuntimeError("Missing structuredContent in MCP response")


        def _run_mcp_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
            cmd = ["./vm/mcp_curl.sh", tool, json.dumps(args)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "MCP tool call failed")
            return _parse_mcp_response(result.stdout)


        def _extract_edit_query(request: str) -> str:
            query = _extract_search_query(request)
            query = re.sub(r"\b(in\s+notion|notion)\b", "", query, flags=re.IGNORECASE).strip()
            return query


        def _strip_quotes(text: str) -> str:
            return text.strip().strip("\"'").strip()


        def _parse_edit_intent(request: str) -> Tuple[Dict[str, Any], List[str]]:
            updates: Dict[str, Any] = {"properties": {}}
            notes: List[str] = []
            lower = request.lower()

            title_match = re.search(
                r"(?:rename|change|update|set)\s+title(?:\s+from)?\s+(.+?)\s+to\s+(.+)",
                request,
                flags=re.IGNORECASE,
            )
            if title_match:
                updates["title"] = _strip_quotes(title_match.group(2))

            status_match = re.search(r"set\s+status\s+(.+)", request, flags=re.IGNORECASE)
            if status_match:
                updates["properties"]["Status"] = _strip_quotes(status_match.group(1))

            desc_match = re.search(r"set\s+description\s+(.+)", request, flags=re.IGNORECASE)
            if desc_match:
                updates["properties"]["Description"] = _strip_quotes(desc_match.group(1))

            tag_match = re.search(
                r"(?:add|set)\s+tag[s]?\s+(.+)",
                request,
                flags=re.IGNORECASE,
            )
            if tag_match:
                raw_tags = _strip_quotes(tag_match.group(1))
                tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
                if tags:
                    updates["properties"]["Domain"] = tags

            if not updates.get("title") and not updates["properties"]:
                notes.append("No update intent detected; specify title/status/description/tag.")

            return updates, notes


        def _parse_prefs_request(request: str, prefs: Dict[str, object]) -> Dict[str, object]:
            lower = request.lower()
            updated = dict(prefs)
            if "enable auto apply" in lower or "enable auto-apply" in lower:
                updated["auto_apply_enabled"] = True
            if "disable auto apply" in lower or "disable auto-apply" in lower:
                updated["auto_apply_enabled"] = False
            match = re.search(r"auto apply threshold to\s*([0-9.]+)", lower)
            if match:
                try:
                    value = float(match.group(1))
                except ValueError:
                    value = prefs.get("auto_apply_threshold", 0.92)
                updated["auto_apply_threshold"] = max(0.0, min(value, 1.0))
            return updated


        def _build_correction_updates(
            candidate: Dict[str, Any], old_text: str | None, new_text: str | None
        ) -> Dict[str, Any]:
            title = str(candidate.get("title") or "")
            if new_text:
                if old_text:
                    new_title = _replace_case_insensitive(title, old_text, new_text)
                else:
                    new_title = new_text
                return {"title": new_title, "properties": {}}
            return {"properties": {}}


        def _write_text(path: Path, content: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


        def _build_fulfil_spec(
            item: Dict[str, Any],
            source_text: str | None,
            requirements: str | None,
            inputs_and_capture: Dict[str, Any] | None,
            tool_name: str,
        ) -> str:
            title = item.get("title") or "Tool Request"
            desired = item.get("desired_outcome") or "TBD"
            url = item.get("url") or ""
            requirements_text = requirements or "None"
            source_note = source_text or ""
            inputs_and_capture = inputs_and_capture or {}
            inputs = inputs_and_capture.get("supported_inputs") or ["TBD"]
            user_inputs = inputs_and_capture.get("what_user_provides_v0") or ["TBD"]
            unsupported = inputs_and_capture.get("unsupported_yet") or []
            examples = [
                f"./vm/mcp_curl.sh {tool_name} '{{\"input\":\"example\"}}'",
                f"./vm/mcp_curl.sh {tool_name} '{{\"input\":\"example\",\"dry_run\":true}}'",
                f"./vm/mcp_curl.sh {tool_name} '{{}}'",
            ]
            how_to_use = (
                "## How to use\n"
                "Inputs:\n"
                + "".join(f"- {item}\n" for item in inputs)
                + "\nWhat the user provides (v0):\n"
                + "".join(f"- {item}\n" for item in user_inputs)
                + ("\nNot supported yet:\n" + "".join(f"- {item}\n" for item in unsupported) if unsupported else "")
                + "\nExamples:\n"
                + "".join(f"- `{example}`\n" for example in examples)
            )
            return (
                f"# Tool Spec: {title}\n\n"
                "## Source\n"
                f"- Tool request URL: {url}\n"
                f"- Original request: {source_note}\n\n"
                "## Problem\n"
                f"{title}\n\n"
                "## Desired outcome\n"
                f"{desired}\n\n"
                "## Requirements\n"
                f"{requirements_text}\n\n"
                f"{how_to_use}\n\n"
                "## v0 proposal\n"
                "- Build the smallest useful workflow first.\n"
                "- Read-only by default; require explicit apply for writes.\n"
            )


        def _build_fulfil_plan(
            item: Dict[str, Any],
            requirements: str | None,
            plan_outline: List[str] | None,
            inputs_and_capture: Dict[str, Any] | None,
        ) -> str:
            title = item.get("title") or "Tool Request"
            url = item.get("url") or ""
            requirements_text = requirements or "None"
            if not plan_outline:
                plan_outline = [
                    "Confirm inputs/outputs contract.",
                    "Implement read-only path first.",
                    "Add explicit apply/confirm path for writes.",
                ]
            inputs_and_capture = inputs_and_capture or {}
            inputs = inputs_and_capture.get("supported_inputs") or ["TBD"]
            capture = inputs_and_capture.get("what_user_provides_v0") or ["TBD"]
            return (
                f"# Plan: {title}\n\n"
                f"- Source URL: {url}\n"
                f"- Requirements: {requirements_text}\n\n"
                "## Inputs / UX / Capture\n"
                "Supported inputs:\n"
                + "".join(f"- {item}\n" for item in inputs)
                + "\nUser provides (v0):\n"
                + "".join(f"- {item}\n" for item in capture)
                + "\n## Steps (v0)\n"
                + "".join(f"{idx + 1}) {step}\n" for idx, step in enumerate(plan_outline))
            )


        def _write_fulfilment_files(
            item: Dict[str, Any],
            source_text: str | None,
            requirements: str | None,
            plan_outline: List[str] | None,
            inputs_and_capture: Dict[str, Any] | None,
        ) -> Tuple[str, str]:
            today = datetime.now().strftime("%Y-%m-%d")
            slug = _slugify(str(item.get("title") or "tool-request"))
            tool_name = _slugify_identifier(str(item.get("title") or "tool_request"))
            spec_path = Path("memory/specs") / f"{today}_{slug}.md"
            plan_path = Path("memory/plans") / f"{today}_{slug}.md"
            _write_text(
                spec_path,
                _build_fulfil_spec(item, source_text, requirements, inputs_and_capture, tool_name),
            )
            _write_text(
                plan_path,
                _build_fulfil_plan(item, requirements, plan_outline, inputs_and_capture),
            )
            return str(spec_path), str(plan_path)


        def _pick_request_by_id(items: List[Dict[str, Any]], page_id: str) -> Dict[str, Any] | None:
            for item in items:
                if str(item.get("id")) == page_id:
                    return item
            return None


        def _extract_summary_value(summary: Dict[str, Any], key: str) -> Any:
            for prop, value in summary.items():
                if prop.strip().lower() == key.strip().lower():
                    if isinstance(value, dict) and "value" in value:
                        return value.get("value")
                    return value
            return None


        def _resolve_tool_request(page_id: str, source_text: str | None) -> Dict[str, Any]:
            if source_text:
                search = _run_mcp_tool("tool_requests_search", {"query": source_text, "limit": 10})
                items = search.get("result", {}).get("items", [])
                candidate = _pick_request_by_id(items, page_id)
                if candidate:
                    return candidate
            page = _run_mcp_tool("notion_get_page", {"page_id": page_id})
            summary = page.get("result", {}).get("page", {}).get("properties", {})
            title = page.get("result", {}).get("page", {}).get("title") or ""
            url = page.get("result", {}).get("page", {}).get("url") or ""
            desired = _extract_summary_value(summary, "Desired outcome") or ""
            description = _extract_summary_value(summary, "Description") or ""
            domain = _extract_summary_value(summary, "Domain") or []
            status = _extract_summary_value(summary, "Status") or ""
            impact = _extract_summary_value(summary, "Impact") or ""
            frequency = _extract_summary_value(summary, "Frequency") or ""
            return {
                "id": page_id,
                "title": title,
                "url": url,
                "description": description,
                "desired_outcome": desired,
                "domain": domain,
                "status": status,
                "impact": impact,
                "frequency": frequency,
            }


        def _update_registry(slug: str, registry_path: Path) -> bool:
            lines = registry_path.read_text(encoding="utf-8").splitlines()
            updated = False

            def insert_in_block(start_predicate, end_predicate) -> None:
                nonlocal updated
                start = next((i for i, line in enumerate(lines) if start_predicate(line)), None)
                if start is None:
                    raise RuntimeError("Registry import block not found.")
                end = next((i for i in range(start + 1, len(lines)) if end_predicate(lines[i])), None)
                if end is None:
                    raise RuntimeError("Registry block end not found.")
                if any(re.search(rf"\\b{re.escape(slug)}\\b", line) for line in lines[start + 1 : end]):
                    return
                lines.insert(end, f"    {slug},")
                updated = True

            insert_in_block(lambda line: line.strip() == "from tools import (", lambda line: line.strip() == ")")
            insert_in_block(lambda line: line.strip() == "for module in (", lambda line: line.strip() == "):")

            if updated:
                registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return updated


        def _scaffold_tool(request: str) -> Dict[str, Any]:
            slug = _slugify(request)
            module_slug = _slugify_identifier(request)
            tools_dir = Path("vm_server/tools")
            module_path = tools_dir / f"{module_slug}.py"
            registry_path = tools_dir / "registry.py"
            created: List[str] = []

            if module_path.exists():
                raise RuntimeError(f"Tool already exists: {module_path}")

            tools_dir.mkdir(parents=True, exist_ok=True)
            module_content = f"""from __future__ import annotations

        from fastmcp import FastMCP


        def register(mcp: FastMCP) -> None:
            @mcp.tool
            async def {module_slug}(request: str | None = None) -> dict:
                \"\"\"Stub tool generated by scripts/agent.py.\"\"\"
                return {{
                    "summary": "Stub tool created. Implementation pending.",
                    "result": {{"request": request}},
                    "next_actions": ["Implement tool logic in vm_server/tools/{module_slug}.py"],
                    "errors": [],
                }}
        """
            module_path.write_text(module_content, encoding="utf-8")
            created.append(str(module_path))

            if not registry_path.exists():
                raise RuntimeError(f"Missing registry: {registry_path}")
            _update_registry(module_slug, registry_path)
            created.append(str(registry_path))

            today = datetime.now().strftime("%Y-%m-%d")
            spec_path = Path("memory/specs") / f"{today}_{slug}.md"
            plan_path = Path("memory/plans") / f"{today}_{slug}.md"
            spec_content = (
                f"# Tool Spec: {request}\n\n"
                "## Problem\n"
                f"{request}\n\n"
                "## v0 proposal\n"
                "- Create a minimal read-only tool.\n"
                "- Add an explicit apply/confirm step before any writes.\n"
            )
            plan_content = (
                f"# Plan: {request}\n\n"
                "1) Confirm inputs/outputs contract.\n"
                "2) Implement read-only path first.\n"
                "3) Add tests + apply path with confirmation.\n"
            )
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(spec_content, encoding="utf-8")
            plan_path.write_text(plan_content, encoding="utf-8")
            created.append(str(spec_path))
            created.append(str(plan_path))

            return {
                "slug": module_slug,
                "module": str(module_path),
                "spec_path": str(spec_path),
                "plan_path": str(plan_path),
                "files_created": created,
            }


        def _run_interactive(
            request_text: str,
            args: argparse.Namespace,
            prefs: Dict[str, object],
            plan_only: bool,
        ) -> int:
            fulfil_mode, fulfil_query = _detect_fulfil_mode(request_text)
            if not fulfil_mode:
                print("Interactive mode only supports fulfilment requests (make/build/implement...).")
                return 1

            auto_confirm = bool(args.auto_confirm) or bool(prefs.get("interactive_auto_confirm"))
            query = fulfil_query if fulfil_mode == "fulfil_match" else None

            prepared = _prepare_fulfilment(request_text, query)
            candidates = prepared["ranked"][:5]
            decision = prepared["decision"]
            selected_id = decision.get("selected_id")
            selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
            confidence = float(decision.get("confidence") or 0.0)

            if not selected and candidates:
                selected = _pick_request_by_id(prepared["candidates"], candidates[0].get("id"))

            if not selected:
                print("No matching tool requests found.")
                return 1

            def _rationale(candidate: Dict[str, Any]) -> str:
                tokens = candidate.get("matches", {}).get("top_tokens") or candidate.get("top_tokens") or []
                if tokens:
                    return ", ".join(tokens[:5])
                breakdown = candidate.get("breakdown") or candidate.get("score_breakdown") or {}
                positive = []
                for key, value in breakdown.items():
                    if isinstance(value, (int, float)) and value > 0:
                        positive.append(f"{key}={value}")
                return ", ".join(positive[:3]) if positive else "low overlap"

            def print_selection() -> None:
                print("\nSelected tool request:")
                print(f"- Title: {selected.get('title')}")
                print(f"- URL: {selected.get('url')}")
                desired_text = selected.get("desired_outcome") or ""
                desired_snippet = desired_text[:160] + ("..." if len(desired_text) > 160 else "")
                print(f"- Desired outcome: {desired_snippet}")
                print(f"- Confidence: {confidence:.2f}")
                if candidates:
                    print("\nTop candidates:")
                    for idx, cand in enumerate(candidates[:3], start=1):
                        score = cand.get("total_score") or cand.get("score") or 0
                        print(f"  {idx}) {cand.get('title')} (score {score:.2f}) — {_rationale(cand)}")

            print_selection()
            if not plan_only:
                attempts = 0
                while not auto_confirm and not _prompt_yes_no("\nUse selected tool request? [Y/n] "):
                    attempts += 1
                    choice = input("Pick 1/2/3 or type a new search phrase: ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(candidates):
                        picked = candidates[idx]
                        selected = _pick_request_by_id(prepared["candidates"], picked.get("id")) or picked
                        print_selection()
                        break
                elif choice:
                    request_text = choice
                    prepared = _prepare_fulfilment(request_text, choice)
                    candidates = prepared["ranked"][:5]
                    decision = prepared["decision"]
                    selected_id = decision.get("selected_id")
                    selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
                    confidence = float(decision.get("confidence") or 0.0)
                    if selected:
                        print_selection()
                        continue
                if attempts >= 2:
                    print("Selection still ambiguous. Exiting safely.")
                    summary = {
                        "summary": "Interactive fulfilment cancelled.",
                        "result": {"selected": None, "candidates": candidates[:3]},
                        "next_actions": ["Re-run with a more specific description."],
                        "errors": [],
                    }
                    print("\n" + json.dumps(summary, indent=2))
                    return 1

            if args.requirements:
                requirements = args.requirements.strip()
            elif plan_only:
                requirements = ""
            else:
                if auto_confirm and not sys.stdin.isatty():
                    requirements = ""
                else:
                    try:
                        requirements = input(
                            "Any extra requirements/constraints? (press enter for none) "
                        ).strip()
                    except EOFError:
                        requirements = ""

            plan_outline = decision.get("plan_outline") or []
            inputs_and_capture = decision.get("inputs_and_capture") or {}

            print("\nDraft plan:")
            for idx, step in enumerate(plan_outline, start=1):
                print(f"{idx}) {step}")
            questions = decision.get("questions") or []
            if questions:
                print("\nQuestions:")
                for question in questions:
                    print(f"- {question}")
            if inputs_and_capture:
                print("\nInputs / capture contract:")
                for label, value in inputs_and_capture.items():
                    if isinstance(value, list):
                        for item in value:
                            print(f"- {label}: {item}")
                    else:
                        print(f"- {label}: {value}")

            if plan_only:
                summary = {
                    "summary": "PLAN_ONLY: plan-only request. No files written.",
                    "result": {
                        "selected": selected,
                        "requirements": requirements,
                        "plan_outline": plan_outline,
                        "inputs_and_capture": inputs_and_capture,
                        "questions": questions,
                        "plan_only": True,
                        "blocked_actions": PLAN_ONLY_BLOCKED_ACTIONS,
                    },
                    "next_actions": ["Re-run with --execute to write spec/plan files."],
                    "errors": [],
                }
                print("\n" + json.dumps(summary, indent=2))
                return 0

            proceed = _prompt_yes_no("Proceed to write spec/plan files now? [y/N] ", default_yes=False)
            if not proceed:
                summary = {
                    "summary": "Selection confirmed. Plan drafted; no files written.",
                    "result": {
                        "selected": selected,
                        "requirements": requirements,
                        "plan_outline": plan_outline,
                        "inputs_and_capture": inputs_and_capture,
                    },
                    "next_actions": ["Re-run with --execute to write spec/plan files."],
                    "errors": [],
                }
                print("\n" + json.dumps(summary, indent=2))
                return 0

            slug = _slugify(selected.get("title") or "tool-request")
            requirements_path = _build_requirements_file(slug, requirements)
            spec_path, plan_path = _write_fulfilment_files(
                selected,
                request_text,
                requirements,
                plan_outline,
                inputs_and_capture,
            )

            summary = {
                "summary": "Interactive fulfilment complete.",
                "result": {
                    "selected": selected,
                    "spec_path": spec_path,
                    "plan_path": plan_path,
                    "requirements_path": requirements_path,
                },
                "next_actions": ["Review spec/plan, then implement when ready."],
                "errors": [],
            }
            print("\n" + json.dumps(summary, indent=2))
            return 0


        def main() -> int:
            parser = argparse.ArgumentParser(description="Route natural language requests.")
            parser.add_argument("request", nargs="*")
            parser.add_argument("--dry-run", action="store_true")
            parser.add_argument("--execute", action="store_true")
            parser.add_argument("--scaffold", action="store_true")
            parser.add_argument("--auto-apply", action="store_true")
            parser.add_argument("--force", action="store_true")
            parser.add_argument("--interactive", action="store_true")
            parser.add_argument("--auto-confirm", action="store_true")
            parser.add_argument("--accept", dest="accept_id")
            parser.add_argument("--from", dest="from_text", default="")
            parser.add_argument("--requirements", default="")
            args = parser.parse_args()

            request_text = " ".join(args.request).strip()
            if args.from_text:
                request_text = args.from_text.strip()
            dry_run = True
            if args.execute:
                dry_run = False
            if args.dry_run:
                dry_run = True

            prefs = load_prefs()

            plan_only = _is_plan_only_request(request_text)
            if plan_only:
                dry_run = True

            route, route_meta = _route(request_text, args.scaffold, args.accept_id)
            if route in ("fulfil_best", "fulfil_match") and args.interactive:
                return _run_interactive(request_text, args, prefs, plan_only)
            errors: List[str] = []
            next_actions: List[str] = []
            result: Dict[str, Any] = {
                "route": route,
                "request": request_text,
                "commands": [],
                "files_created": [],
            }

            plan_allowed_routes = {
                "list",
                "search",
                "fetch",
                "fulfil_best",
                "fulfil_match",
            }
            plan_only_mode = plan_only and route not in plan_allowed_routes

            if plan_only_mode:
                result["plan_only"] = True
                result["blocked_actions"] = PLAN_ONLY_BLOCKED_ACTIONS
                next_actions.append("PLAN_ONLY: no writes performed.")
                summary = f"PLAN_ONLY route: {route}. Dry-run: {dry_run}."
                output = {
                    "summary": summary,
                    "result": result,
                    "next_actions": next_actions,
                    "errors": errors,
                }
                print(json.dumps(output, indent=2))
                return 0

            try:
                        if route == "list":
                            cmd = [
                                "./vm/mcp_curl.sh",
                                "tool_requests_latest",
                                json.dumps({"limit": 10, "statuses": ["new", "triaging"]}),
                            ]
                            result["commands"].append(" ".join(cmd))
                            result["output"] = _run_command(cmd)
                        elif route == "fulfil_match":
                        query = route_meta.get("query") or request_text
                        if not query:
                            raise RuntimeError("Missing fulfilment description.")
                        prepared = _prepare_fulfilment(request_text, query)
                        ranked = _summarize_candidates(prepared["ranked"][:5])
                        decision = prepared["decision"]
                        selected_id = decision.get("selected_id")
                        selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
                        result["candidates"] = ranked
                        result["decision"] = decision
                        result["questions"] = decision.get("questions") or []
                        result["plan_outline"] = decision.get("plan_outline") or []
                        result["inputs_and_capture"] = decision.get("inputs_and_capture") or {}
                        result["selected"] = selected
                        if not ranked:
                            next_actions.append("No matches found. Try a shorter or quoted description.")
                        else:
                            if selected:
                                next_actions.append(
                                    f"Confirm selection: python scripts/agent.py --accept {selected.get('id')} "
                                    f'--from "{request_text}" --execute'
                                )
                            next_actions.append("Answer the questions, then re-run with --execute to write spec/plan.")
                        elif route == "fulfil_best":
                        prepared = _prepare_fulfilment(request_text, None)
                        ranked = _summarize_candidates(prepared["ranked"][:5])
                        decision = prepared["decision"]
                        selected_id = decision.get("selected_id")
                        selected = _pick_request_by_id(prepared["candidates"], selected_id) if selected_id else None
                        result["candidates"] = ranked
                        result["decision"] = decision
                        result["questions"] = decision.get("questions") or []
                        result["plan_outline"] = decision.get("plan_outline") or []
                        result["inputs_and_capture"] = decision.get("inputs_and_capture") or {}
                        result["selected"] = selected
                        if not selected:
                            next_actions.append("No tool requests found to fulfill.")
                        else:
                            next_actions.append(
                                f"Confirm selection: python scripts/agent.py --accept {selected.get('id')} "
                                f'--from "{request_text}" --execute'
                            )
                            next_actions.append("Answer the questions, then re-run with --execute to write spec/plan.")
                        elif route == "fulfil_accept":
                        if not args.accept_id:
                            raise RuntimeError("Missing --accept <page_id> for fulfilment.")
                        source_text = request_text or args.from_text or ""
                        result["accept_id"] = args.accept_id
                        prepared = _prepare_fulfilment(source_text or args.accept_id, source_text or None)
                        candidate = _pick_request_by_id(prepared["candidates"], args.accept_id)
                        if not candidate:
                            candidate = _resolve_tool_request(args.accept_id, source_text or None)
                        result["selected"] = candidate
                        decision = prepared["decision"]
                        plan_outline = decision.get("plan_outline") or []
                        inputs_and_capture = decision.get("inputs_and_capture") or {}
                        result["decision"] = decision
                        result["plan_outline"] = plan_outline
                        result["inputs_and_capture"] = inputs_and_capture
                        if dry_run or _is_plan_only_request(request_text):
                            next_actions.append("Re-run with --execute to write spec/plan files.")
                        else:
                            requirements = args.requirements or ""
                            slug = _slugify(candidate.get("title") or "tool-request")
                            requirements_path = _build_requirements_file(slug, requirements)
                            spec_path, plan_path = _write_fulfilment_files(
                                candidate,
                                source_text,
                                requirements,
                                plan_outline,
                                inputs_and_capture,
                            )
                            result["spec_path"] = spec_path
                            result["plan_path"] = plan_path
                            result["requirements_path"] = requirements_path
                            result["files_created"].extend([spec_path, plan_path, requirements_path])
                        elif route == "wish_hint":
                        result["message"] = (
                            "This looks like a wish capture. Use Poke to log the wish in Notion."
                        )
                        next_actions.append(
                            "If you meant to build it now, say: make/build/implement <description>."
                        )
                        elif route == "search":
                        query = route_meta.get("query") or request_text
                        cmd = ["./vm/mcp_curl.sh", "tool_requests_search", json.dumps({"query": query, "limit": 10})]
                        result["commands"].append(" ".join(cmd))
                        result["output"] = _run_command(cmd)
                        elif route == "fetch":
                        payload = fetch_candidates(limit=15, query=None)
                        result["candidates"] = payload.get("result", {}).get("candidates", [])
                        result["fetch"] = payload
                        elif route == "prefs":
                        updated_prefs = _parse_prefs_request(request_text, prefs)
                        save_prefs(updated_prefs)
                        result["prefs"] = updated_prefs
                        next_actions.append("Prefs saved. Re-run with your request.")
                        elif route == "apply_last":
                        if dry_run:
                            next_actions.append("Re-run with --execute to apply the last preview.")
                        else:
                            preview = _load_last_preview()
                            if not preview:
                                raise RuntimeError("No last preview found.")
                            if preview.get("type") != "notion_correction":
                                raise RuntimeError("Last preview is not a Notion correction.")
                            timestamp = str(preview.get("timestamp") or "")
                            if not _preview_is_fresh(timestamp) and not args.force:
                                raise RuntimeError("Last preview is older than 24h. Re-run with --force.")
                            payload = {
                                "page_id": preview.get("page_id"),
                                "updates": preview.get("updates"),
                                "dry_run": False,
                            }
                            result["commands"].append(
                                "./vm/mcp_curl.sh notion_update_page " + json.dumps(payload)
                            )
                            result["notion_update"] = _run_mcp_tool("notion_update_page", payload)
                        elif route == "correct_tool_request":
                        old_text, new_text = _parse_correction_request(request_text)
                        if not new_text:
                            raise RuntimeError("No correction target found. Use: change 'X' to 'Y'.")

                        page_id = _extract_page_id(request_text)
                        items: List[Dict[str, Any]] = []
                        if page_id:
                            result["commands"].append(
                                "./vm/mcp_curl.sh notion_get_page " + json.dumps({"page_id": page_id})
                            )
                            page = _run_mcp_tool("notion_get_page", {"page_id": page_id})
                            summary = page.get("result", {}).get("page", {})
                            items = [
                                {
                                    "id": summary.get("id"),
                                    "title": summary.get("title"),
                                    "url": summary.get("url"),
                                    "created_time": "",
                                }
                            ]
                        else:
                            query = old_text or _extract_search_query(request_text)
                            search = _run_mcp_tool("tool_requests_search", {"query": query, "limit": 10})
                            result["commands"].append(
                                "./vm/mcp_curl.sh tool_requests_search " + json.dumps({"query": query, "limit": 10})
                            )
                            items = search.get("result", {}).get("items", [])
                            if not items and new_text:
                                fallback_query = new_text
                                search = _run_mcp_tool(
                                    "tool_requests_search", {"query": fallback_query, "limit": 10}
                                )
                                result["commands"].append(
                                    "./vm/mcp_curl.sh tool_requests_search "
                                    + json.dumps({"query": fallback_query, "limit": 10})
                                )
                                items = search.get("result", {}).get("items", [])
                            if not items and new_text:
                                simplified = _simplify_query(new_text)
                                if simplified and simplified != new_text:
                                    search = _run_mcp_tool(
                                        "tool_requests_search", {"query": simplified, "limit": 10}
                                    )
                                    result["commands"].append(
                                        "./vm/mcp_curl.sh tool_requests_search "
                                        + json.dumps({"query": simplified, "limit": 10})
                                    )
                                    items = search.get("result", {}).get("items", [])
                        if not items:
                            result["candidates"] = []
                            next_actions.append("No matches. Try quoting the exact title.")
                        elif len(items) > 1 and not page_id:
                            candidates = []
                            for item in items:
                                confidence, breakdown = _compute_confidence(
                                    request_text, item, items, old_text
                                )
                                candidates.append(
                                    {
                                        "id": item.get("id"),
                                        "title": item.get("title"),
                                        "url": item.get("url"),
                                        "confidence": confidence,
                                    }
                                )
                            result["candidates"] = candidates
                            next_actions.append("Multiple matches found. Re-run with a page URL or id.")
                        else:
                            candidate = items[0]
                            confidence, breakdown = _compute_confidence(
                                request_text, candidate, items, old_text
                            )
                            updates = _build_correction_updates(candidate, old_text, new_text)
                            correction_payload = {
                                "page_id": candidate.get("id"),
                                "updates": updates,
                            }
                            result["correction"] = {
                                "target": {
                                    "id": candidate.get("id"),
                                    "title": candidate.get("title"),
                                    "url": candidate.get("url"),
                                },
                                "confidence": confidence,
                                "confidence_breakdown": breakdown,
                            }
                            result["confidence"] = confidence
                            result["confidence_breakdown"] = breakdown

                            auto_apply_enabled = bool(prefs.get("auto_apply_enabled"))
                            threshold = float(prefs.get("auto_apply_threshold") or 0.92)
                            scope = prefs.get("auto_apply_scope") or []
                            allow_auto = (
                                auto_apply_enabled
                                and args.auto_apply
                                and "notion_corrections" in scope
                            )

                            if dry_run:
                                payload = dict(correction_payload, dry_run=True)
                                result["commands"].append(
                                    "./vm/mcp_curl.sh notion_update_page " + json.dumps(payload)
                                )
                                result["notion_update"] = _run_mcp_tool("notion_update_page", payload)
                                _save_last_preview(
                                    {
                                        "type": "notion_correction",
                                        "page_id": candidate.get("id"),
                                        "updates": updates,
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                        "confidence": confidence,
                                    }
                                )
                                if confidence >= threshold:
                                    next_actions.append(
                                        f"High confidence ({confidence:.2f}). To apply: "
                                        "python scripts/agent.py \"apply that\" --execute"
                                    )
                                    next_actions.append(
                                        "Or rerun with --execute --auto-apply."
                                    )
                                else:
                                    next_actions.append(
                                        f"Confidence ({confidence:.2f}) below threshold. "
                                        "Re-run with --execute --force to apply."
                                    )
                            else:
                                payload = dict(correction_payload, dry_run=False)
                                if allow_auto and confidence < threshold and not args.force:
                                    preview_payload = dict(correction_payload, dry_run=True)
                                    result["commands"].append(
                                        "./vm/mcp_curl.sh notion_update_page " + json.dumps(preview_payload)
                                    )
                                    result["notion_update"] = _run_mcp_tool(
                                        "notion_update_page", preview_payload
                                    )
                                    next_actions.append(
                                        f"Confidence ({confidence:.2f}) below threshold. "
                                        "Re-run with --execute --force to apply."
                                    )
                                else:
                                    result["commands"].append(
                                        "./vm/mcp_curl.sh notion_update_page " + json.dumps(payload)
                                    )
                                    result["notion_update"] = _run_mcp_tool("notion_update_page", payload)
                    elif route == "edit_notion":
                        page_id = _extract_page_id(request_text)
                        updates, intent_notes = _parse_edit_intent(request_text)

                        if not page_id:
                            query = _extract_edit_query(request_text)
                            if not query:
                                raise RuntimeError("No Notion target found. Provide a page title or URL.")
                            search = _run_mcp_tool("notion_search", {"query": query, "limit": 5})
                            result["commands"].append(
                                "./vm/mcp_curl.sh notion_search "
                                + json.dumps({"query": query, "limit": 5})
                            )
                            items = search.get("result", {}).get("items", [])
                            if not items:
                                result["candidates"] = []
                                next_actions.append("No matches. Try quoting the page title or paste the URL.")
                            elif len(items) > 1:
                                result["candidates"] = items
                                next_actions.append("Multiple matches found. Re-run with a page URL or id.")
                            else:
                                page_id = items[0].get("id")

                        if not page_id:
                            result["intent_notes"] = intent_notes
                        else:
                            if intent_notes:
                                result["intent_notes"] = intent_notes
                            if intent_notes and dry_run:
                                result["commands"].append(
                                    "./vm/mcp_curl.sh notion_get_page "
                                    + json.dumps({"page_id": page_id})
                                )
                                page = _run_mcp_tool("notion_get_page", {"page_id": page_id})
                                result["preview"] = page
                                next_actions.append("Specify a target field (title/status/description/tag) to update.")
                            else:
                                payload = {"page_id": page_id, "updates": updates, "dry_run": dry_run}
                                result["commands"].append(
                                    "./vm/mcp_curl.sh notion_update_page "
                                    + json.dumps(payload)
                                )
                                result["notion_update"] = _run_mcp_tool("notion_update_page", payload)
                                if dry_run:
                                    next_actions.append("Re-run with --execute to apply the update.")
                        elif route == "deploy":
                        cmd = ["./vm/deploy.sh"]
                        result["commands"].append(" ".join(cmd))
                        if dry_run:
                            next_actions.append("Re-run with --execute to deploy.")
                        else:
                            result["output"] = _run_command(cmd)
                        elif route == "scaffold":
                        if not request_text:
                            raise RuntimeError("Provide a tool name to scaffold.")
                        result["scaffold_source"] = request_text
                        if dry_run:
                            next_actions.append("Re-run with --execute to scaffold the tool.")
                        else:
                            scaffold = _scaffold_tool(request_text)
                            result["files_created"] = scaffold.pop("files_created", [])
                            result["scaffold"] = scaffold
                        elif route == "call":
                        tool = route_meta.get("tool")
                        args_json = route_meta.get("args") or "{}"
                        if not tool:
                            raise RuntimeError("Missing tool name for call route.")
                        cmd = ["./vm/mcp_curl.sh", tool, args_json]
                        result["commands"].append(" ".join(cmd))
                        if MUTATING_TOOL_RE.search(tool):
                            if dry_run:
                                next_actions.append("Re-run with --execute to call mutating tool.")
                            else:
                                result["output"] = _run_command(cmd)
                        else:
                            result["output"] = _run_command(cmd)
                        else:
                        next_actions.append("Try: python scripts/agent.py \"what should we build next?\"")
                        next_actions.append("Or: python scripts/agent.py \"show tool requests\"")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    if plan_only:
        result["plan_only"] = True
        result["blocked_actions"] = PLAN_ONLY_BLOCKED_ACTIONS
    if result.get("commands"):
        last_cmd = result["commands"][-1]
        next_actions.append(f"Reproduce: {last_cmd}")
    prefix = "PLAN_ONLY: " if plan_only else ""
    summary = f"{prefix}Route: {route}. Dry-run: {dry_run}."
    output = {
        "summary": summary,
        "result": result,
        "next_actions": next_actions,
        "errors": errors,
    }
    print(json.dumps(output, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
