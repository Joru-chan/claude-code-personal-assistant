from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import httpx
from fastmcp import FastMCP

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

DEFAULT_PROPERTY_MAP = {
    "name": "Item Name",
    "quantity": "Quantity",
    "unit": "Unit",
    "category": "Food Category",
    "purchase_date": "Purchase Date",
    "store": "Store",
    "expiration_date": "Expiration Date",
    "notes": "Notes",
    "receipt_number": "Receipt Number",
    "replenish": "Replenish",
    "status": "Status",
    "storage_location": "Storage Location",
    "price": "Price",
}

SKIP_KEYWORDS = {
    "total",
    "subtotal",
    "tax",
    "change",
    "cash",
    "visa",
    "mastercard",
    "amex",
    "balance",
    "payment",
    "discount",
}


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _notion_error_message(response: httpx.Response) -> str:
    retry_after = response.headers.get("retry-after")
    if response.status_code == 429:
        return f"Notion rate limited (HTTP 429). Retry after {retry_after or 'later'}."
    try:
        payload = response.json()
        return payload.get("message") or payload.get("code") or response.text
    except Exception:  # noqa: BLE001
        return response.text


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _fuzzy_match_score(name1: str, name2: str) -> float:
    """Calculate fuzzy match score between two names (0-1, higher is better)"""
    norm1 = _normalize_name(name1)
    norm2 = _normalize_name(name2)
    
    if norm1 == norm2:
        return 1.0
    
    # Check if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        return 0.8
    
    # Calculate word overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    if not words1 or not words2:
        return 0.0
    
    overlap = len(words1 & words2)
    total = len(words1 | words2)
    
    return overlap / total if total > 0 else 0.0


def _append_price_to_notes(
    existing_notes: str | None, 
    price: float, 
    date: str, 
    store: str
) -> str:
    """Append price history to notes field as JSON"""
    import json
    
    # Parse existing price history
    price_history = []
    if existing_notes:
        try:
            # Try to extract JSON array from notes
            match = re.search(r'\[.*\]', existing_notes, re.DOTALL)
            if match:
                price_history = json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Add new price entry
    price_history.append({
        "price": price,
        "date": date,
        "store": store
    })
    
    # Format as nice text with JSON
    lines = ["Price History:"]
    for entry in price_history:
        lines.append(f"  ${entry['price']} at {entry['store']} on {entry['date']}")
    
    lines.append(f"\nRaw: {json.dumps(price_history)}")
    return "\n".join(lines)


def _extract_price(line: str) -> str:
    match = re.search(r"\$?\d+(?:\.\d{2})?$", line.strip())
    return match.group(0) if match else ""


def _parse_receipt_text(text: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(keyword in lowered for keyword in SKIP_KEYWORDS):
            continue
        qty = None
        name_part = line
        qty_match = re.match(r"^\s*(\d+)\s*[xX]\s*(.+)", line)
        if qty_match:
            qty = int(qty_match.group(1))
            name_part = qty_match.group(2).strip()
        price = _extract_price(name_part)
        if price:
            name_part = name_part[: -len(price)].strip()
        name_part = re.sub(r"\s{2,}", " ", name_part).strip()
        if len(name_part) < 2:
            continue
        items.append(
            {
                "name": name_part,
                "quantity": qty,
                "unit": None,
                "category": None,
                "store": None,
                "purchase_date": None,
                "source_line": line,
                "confidence": 0.35 if qty is None else 0.45,
                "reason": "parsed_from_receipt_text",
            }
        )
    return items


def _normalize_items(items: List[Dict[str, Any]], errors: List[str]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Item {idx + 1} is not an object.")
            continue
        name = item.get("name") or item.get("title")
        if not name or not isinstance(name, str):
            errors.append(f"Item {idx + 1} missing name/title.")
            continue
        normalized.append(
            {
                "name": name.strip(),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "category": item.get("category"),
                "store": item.get("store"),
                "purchase_date": item.get("purchase_date"),
                "source_line": item.get("source_line"),
                "confidence": item.get("confidence", 0.75),
                "reason": "provided_items_input",
            }
        )
    return normalized


def _dedupe_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    deduped: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _normalize_name(item.get("name", ""))
        if not key:
            duplicates.append(item)
            continue
        if key in seen:
            duplicates.append(item)
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, duplicates


    return None, 0.0


async def _update_item_quantity(
    client: httpx.AsyncClient,
    token: str,
    page_id: str,
    existing_page: Dict[str, Any],
    new_quantity: float,
    property_map: Dict[str, str],
    item_data: Dict[str, Any],
    errors: List[str]
) -> Dict[str, Any] | None:
    """
    Update existing pantry item with new quantity and price history.
    Returns updated page or None on error.
    """
    from datetime import datetime
    
    properties = existing_page.get("properties", {})
    
    # Get existing quantity
    qty_prop = property_map.get("quantity", "Quantity")
    existing_qty = 0.0
    if qty_prop in properties:
        qty_data = properties[qty_prop]
        if qty_data.get("type") == "number":
            existing_qty = qty_data.get("number", 0.0) or 0.0
    
    # Calculate new quantity
    updated_qty = existing_qty + new_quantity
    
    # Build update payload
    update_props: Dict[str, Any] = {}
    
    # Update quantity
    update_props[qty_prop] = {"number": updated_qty}
    
    # Update price history in notes if price is provided
    price = item_data.get("price")
    if price:
        notes_prop = property_map.get("notes", "Notes")
        existing_notes = None
        if notes_prop in properties:
            notes_data = properties[notes_prop]
            if notes_data.get("type") == "rich_text":
                text_array = notes_data.get("rich_text", [])
                if text_array:
                    existing_notes = text_array[0].get("plain_text", "")
        
        # Append price to history
        store = item_data.get("store", "Unknown")
        date = item_data.get("purchase_date", datetime.utcnow().strftime("%Y-%m-%d"))
        updated_notes = _append_price_to_notes(existing_notes, price, date, store)
        
        update_props[notes_prop] = {
            "rich_text": [{"text": {"content": updated_notes}}]
        }
    
    # Send update request
    resp = await client.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=_headers(token),
        json={"properties": update_props}
    )
    
    if resp.status_code >= 400:
        errors.append(f"Failed to update item: {_notion_error_message(resp)}")
        return None
    
    return resp.json()


def _title_property_name(properties: Dict[str, Any]) -> str | None:
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    return None


def _build_property_payload(
    prop_type: str, value: Any, errors: List[str], prop_name: str
) -> Dict[str, Any] | None:
    if value is None:
        return None
    if prop_type == "title":
        return {"title": [{"text": {"content": str(value)}}]}
    if prop_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value)}}]}
    if prop_type == "select":
        return {"select": {"name": str(value)}}
    if prop_type == "multi_select":
        values = value if isinstance(value, list) else [value]
        return {"multi_select": [{"name": str(v)} for v in values if v]}
    if prop_type == "number":
        if isinstance(value, (int, float)):
            return {"number": value}
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            errors.append(f"Property '{prop_name}' expects a number.")
            return None
    if prop_type == "date":
        if isinstance(value, dict):
            return {"date": value}
        return {"date": {"start": str(value)}}
    if prop_type == "url":
        return {"url": str(value)}
    if prop_type == "checkbox":
        if isinstance(value, bool):
            return {"checkbox": value}
        errors.append(f"Property '{prop_name}' expects a boolean.")
        return None
    errors.append(f"Property '{prop_name}' type '{prop_type}' not supported.")
    return None


async def _fetch_database(
    client: httpx.AsyncClient, token: str, db_id: str
) -> Dict[str, Any]:
    resp = await client.get(f"{NOTION_API_BASE}/databases/{db_id}", headers=_headers(token))
    if resp.status_code >= 400:
        raise RuntimeError(_notion_error_message(resp))
    return resp.json()


async def _query_by_title(
    client: httpx.AsyncClient, token: str, db_id: str, title_prop: str, name: str
) -> List[Dict[str, Any]]:
    payload = {"filter": {"property": title_prop, "title": {"equals": name}}}
    resp = await client.post(
        f"{NOTION_API_BASE}/databases/{db_id}/query",
        headers=_headers(token),
        json=payload,
    )
    if resp.status_code >= 400:
        return []
    return resp.json().get("results", [])


async def _query_all_items(
    client: httpx.AsyncClient, token: str, db_id: str
) -> List[Dict[str, Any]]:
    """Query all items from pantry database for fuzzy matching"""
    resp = await client.post(
        f"{NOTION_API_BASE}/databases/{db_id}/query",
        headers=_headers(token),
        json={"page_size": 100}  # Get up to 100 items
    )
    if resp.status_code >= 400:
        return []
    return resp.json().get("results", [])


async def _find_fuzzy_match(
    client: httpx.AsyncClient,
    token: str,
    db_id: str,
    title_prop: str,
    item_name: str,
    threshold: float = 0.7
) -> tuple[Dict[str, Any] | None, float]:
    """
    Find best fuzzy match for item_name in database.
    Returns (matched_page, score) or (None, 0.0) if no good match.
    """
    all_items = await _query_all_items(client, token, db_id)
    
    best_match = None
    best_score = 0.0
    
    for page in all_items:
        # Extract title from page
        title_data = page.get("properties", {}).get(title_prop, {})
        if title_data.get("type") == "title":
            title_array = title_data.get("title", [])
            if title_array:
                existing_name = title_array[0].get("plain_text", "")
                score = _fuzzy_match_score(item_name, existing_name)
                
                if score > best_score:
                    best_score = score
                    best_match = page
    
    if best_score >= threshold:
        return best_match, best_score
    
    return None, 0.0


def _preview_payloads(
    items: List[Dict[str, Any]],
    property_map: Dict[str, str],
    properties: Dict[str, Any],
    errors: List[str],
) -> List[Dict[str, Any]]:
    preview: List[Dict[str, Any]] = []
    title_prop = _title_property_name(properties) or property_map.get("name")
    for item in items:
        props_payload: Dict[str, Any] = {}
        if title_prop in properties:
            prop_type = properties[title_prop].get("type")
            payload = _build_property_payload(prop_type, item.get("name"), errors, title_prop)
            if payload:
                props_payload[title_prop] = payload
        for key, prop_name in property_map.items():
            if key == "name":
                continue
            if prop_name not in properties:
                continue
            prop_type = properties[prop_name].get("type")
            payload = _build_property_payload(prop_type, item.get(key), errors, prop_name)
            if payload:
                props_payload[prop_name] = payload
        preview.append({"item": item, "properties": props_payload})
    return preview


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def receipt_photo_pantry_inventory(
        receipt_text: str | None = None,
        items: List[Dict[str, Any]] | None = None,
        store: str | None = None,
        purchase_date: str | None = None,
        dry_run: bool = True,
        confirm: bool = False,
        pantry_db_id: str | None = None,
        property_map: Dict[str, str] | None = None,
        check_existing: bool = True,
    ) -> dict:
        """
        Parse a receipt text (or structured items) into pantry inventory entries.
        Read-only by default; set dry_run=false and confirm=true to write.
        """
        errors: List[str] = []
        if not receipt_text and not items:
            errors.append("Provide receipt_text or items.")
        if not dry_run and not confirm:
            errors.append("Writes require confirm=true.")
        if errors:
            return {
                "summary": "Missing required inputs.",
                "result": {"items": []},
                "next_actions": ["Provide receipt_text or items."],
                "errors": errors,
            }

        parsed_items: List[Dict[str, Any]] = []
        if items:
            parsed_items.extend(_normalize_items(items, errors))
        if receipt_text:
            parsed_items.extend(_parse_receipt_text(receipt_text))

        for item in parsed_items:
            if store and not item.get("store"):
                item["store"] = store
            if purchase_date and not item.get("purchase_date"):
                item["purchase_date"] = purchase_date

        deduped, duplicates = _dedupe_items(parsed_items)
        summary_parts = [f"Parsed {len(parsed_items)} item(s)."]
        if duplicates:
            summary_parts.append(f"Skipped {len(duplicates)} duplicate line(s).")

        token = os.getenv("NOTION_TOKEN")
        db_id = pantry_db_id or os.getenv("PANTRY_DB_ID")
        property_map = property_map or {
            key: os.getenv(f"PANTRY_PROP_{key.upper()}", default)
            for key, default in DEFAULT_PROPERTY_MAP.items()
        }

        if dry_run or not db_id or not token:
            if not token:
                errors.append("NOTION_TOKEN not set; cannot write to Notion.")
            if not db_id:
                errors.append("PANTRY_DB_ID not set; cannot write to Notion.")
            return {
                "summary": " ".join(summary_parts) + " Dry-run preview.",
                "result": {
                    "items": deduped,
                    "duplicates": duplicates,
                    "apply_ready": False,
                    "property_map": property_map,
                },
                "next_actions": [
                    "Set PANTRY_DB_ID and NOTION_TOKEN to enable apply.",
                    "Re-run with dry_run=false and confirm=true to create items.",
                ],
                "errors": errors,
            }

        created: List[Dict[str, Any]] = []
        updated: List[Dict[str, Any]] = []
        skipped_existing: List[Dict[str, Any]] = []
        missing_properties: List[str] = []
        preview_errors: List[str] = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                database = await _fetch_database(client, token, db_id)
            except RuntimeError as exc:
                return {
                    "summary": "Failed to load pantry database.",
                    "result": {"items": deduped},
                    "next_actions": ["Verify PANTRY_DB_ID and permissions."],
                    "errors": [str(exc)],
                }

            properties = database.get("properties", {})
            title_prop = _title_property_name(properties)
            if not title_prop:
                return {
                    "summary": "Pantry database missing title property.",
                    "result": {"items": deduped},
                    "next_actions": ["Ensure the pantry database has a title property."],
                    "errors": ["No title property found."],
                }

            for key, prop_name in property_map.items():
                if prop_name and prop_name not in properties:
                    missing_properties.append(prop_name)

            preview = _preview_payloads(deduped, property_map, properties, preview_errors)
            if preview_errors:
                errors.extend(preview_errors)

            for entry in preview:
                item = entry["item"]
                name = item.get("name", "")
                quantity = item.get("quantity", 1) or 1
                
                if check_existing:
                    # Try fuzzy matching first
                    matched_page, score = await _find_fuzzy_match(
                        client, token, db_id, title_prop, name, threshold=0.7
                    )
                    
                    if matched_page:
                        # Found a match - update quantity instead of creating
                        page_id = matched_page["id"]
                        updated_page = await _update_item_quantity(
                            client, token, page_id, matched_page, 
                            quantity, property_map, item, errors
                        )
                        
                        if updated_page:
                            matched_name = ""
                            title_data = matched_page.get("properties", {}).get(title_prop, {})
                            if title_data.get("title"):
                                matched_name = title_data["title"][0].get("plain_text", "")
                            
                            updated.append({
                                "id": page_id,
                                "url": matched_page.get("url"),
                                "name": name,
                                "matched_with": matched_name,
                                "match_score": round(score, 2),
                                "quantity_added": quantity
                            })
                            continue

                # No match found - create new item
                payload = {
                    "parent": {"database_id": db_id},
                    "properties": entry["properties"],
                }
                resp = await client.post(
                    f"{NOTION_API_BASE}/pages",
                    headers=_headers(token),
                    json=payload,
                )
                if resp.status_code >= 400:
                    errors.append(_notion_error_message(resp))
                    continue
                page = resp.json()
                created.append(
                    {"id": page.get("id"), "url": page.get("url"), "name": name}
                )

        summary_parts.append(f"Created {len(created)} item(s) in Notion.")
        if updated:
            summary_parts.append(f"Updated {len(updated)} existing item(s).")
        if skipped_existing:
            summary_parts.append(
                f"Skipped {len(skipped_existing)} existing item(s) by title."
            )
        if missing_properties:
            errors.append(
                "Missing pantry properties: " + ", ".join(sorted(set(missing_properties)))
            )

        return {
            "summary": " ".join(summary_parts),
            "result": {
                "items": deduped,
                "duplicates": duplicates,
                "created": created,
                "updated": updated,
                "skipped_existing": skipped_existing,
                "property_map": property_map,
                "apply_ready": True,
                "checked_existing": check_existing,
                "ran_at": datetime.utcnow().isoformat() + "Z",
            },
            "next_actions": [
                "Review created/updated items in Notion.",
                "Adjust property map via PANTRY_PROP_* env vars if needed.",
            ],
            "errors": errors,
        }
