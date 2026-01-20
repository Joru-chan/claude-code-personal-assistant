#!/usr/bin/env python3
"""
Sync tool requests from Notion to local JSON file.

Usage:
    python3 scripts/sync_tool_requests.py
    
Downloads all tool requests from the Notion database and saves them
to memory/tool_requests.json, overwriting any previous version.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not installed. Run: pip install notion-client")
    sys.exit(1)


def get_db_id() -> str:
    """Get tool requests database ID from environment"""
    db_id = os.getenv("TOOL_REQUESTS_DB_ID")
    if not db_id:
        print("ERROR: TOOL_REQUESTS_DB_ID not set in .env")
        sys.exit(1)
    return db_id


def get_notion_token() -> str:
    """Get Notion token from environment"""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("ERROR: NOTION_TOKEN not set in .env")
        sys.exit(1)
    return token


def extract_text(rich_text_array):
    """Extract plain text from Notion rich_text array"""
    if not rich_text_array:
        return None
    return "".join([item.get("plain_text", "") for item in rich_text_array])


def extract_select(select_obj):
    """Extract name from Notion select object"""
    if not select_obj:
        return None
    return select_obj.get("name")


def extract_multi_select(multi_select_array):
    """Extract names from Notion multi_select array"""
    if not multi_select_array:
        return []
    return [item.get("name") for item in multi_select_array]


def parse_page(page) -> dict:
    """Parse a Notion page into a simple dict"""
    props = page.get("properties", {})
    
    return {
        "page_id": page.get("id"),
        "url": page.get("url"),
        "title": extract_text(props.get("Title", {}).get("title", [])),
        "description": extract_text(props.get("Description", {}).get("rich_text", [])),
        "desired_outcome": extract_text(props.get("Desired outcome", {}).get("rich_text", [])),
        "frequency": extract_select(props.get("Frequency", {}).get("select")),
        "impact": extract_select(props.get("Impact", {}).get("select")),
        "domain": extract_multi_select(props.get("Domain", {}).get("multi_select", [])),
        "status": extract_select(props.get("Status", {}).get("select")),
        "source": extract_select(props.get("Source", {}).get("select")),
        "link": props.get("Link(s)", {}).get("url"),
        "notes": extract_text(props.get("Notes / constraints", {}).get("rich_text", [])),
        "created_time": props.get("Created time", {}).get("created_time"),
        "last_edited_time": props.get("Last updated time", {}).get("last_edited_time"),
    }


def fetch_all_pages(notion: Client, db_id: str) -> list:
    """Fetch all pages from the database"""
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        response = notion.databases.query(
            database_id=db_id,
            start_cursor=start_cursor,
            page_size=100
        )
        results.extend(response.get("results", []))
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
    
    return results


def main() -> int:
    print("🔄 Syncing tool requests from Notion...")
    
    token = get_notion_token()
    db_id = get_db_id()
    
    notion = Client(auth=token)
    
    # Fetch all pages
    print(f"📥 Fetching from database {db_id[:8]}...")
    pages = fetch_all_pages(notion, db_id)
    
    # Parse pages
    tool_requests = [parse_page(page) for page in pages]
    
    # Save to JSON
    output_path = Path("memory/tool_requests.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "count": len(tool_requests),
        "tool_requests": tool_requests
    }
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Synced {len(tool_requests)} tool requests to {output_path}")
    print(f"   Synced at: {data['synced_at']}")
    
    # Show status breakdown
    status_counts = {}
    for tr in tool_requests:
        status = tr.get("status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\n📊 Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"   {status}: {count}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
