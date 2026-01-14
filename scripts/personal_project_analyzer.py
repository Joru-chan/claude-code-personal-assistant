#!/usr/bin/env python3
"""
Personal Project Analyzer
Generates a quick report for the Projects database.

Usage:
    python personal_project_analyzer.py
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from notion_client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class ProjectAnalyzer:
    """Analyzes personal projects and generates a summary report."""

    DATABASE_ID = "2e85ae60-7903-81c4-9798-f583477ca854"

    def __init__(self):
        notion_token = os.getenv("NOTION_TOKEN")
        if not notion_token:
            raise ValueError("NOTION_TOKEN environment variable is required")
        self.notion = Client(auth=notion_token)
        self.today = datetime.now().date()
        self.upcoming_window = self.today + timedelta(days=14)

    def query_database(self) -> Dict:
        try:
            return self.notion.databases.query(database_id=self.DATABASE_ID)
        except Exception as exc:
            print(f"Error querying Projects database: {exc}")
            return {"results": []}

    def parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.split("T")[0]).date()
        except (ValueError, AttributeError):
            return None

    def extract_project(self, page: Dict) -> Dict:
        props = page.get("properties", {})
        name = self._extract_title(props, ["Name", "Title"])
        status = self._extract_select(props, ["Status"]) or "Not started"
        priority = self._extract_select(props, ["Priority"]) or "Medium"
        category = self._extract_select(props, ["Category"])
        target_date = self._extract_date(props, ["Target Date", "Due Date"])
        notes = self._extract_richtext(props, ["Notes"])

        return {
            "id": page.get("id"),
            "name": name,
            "status": status,
            "priority": priority,
            "category": category,
            "target_date": target_date,
            "notes": notes,
            "url": page.get("url", ""),
        }

    def _extract_title(self, props: Dict, names: List[str]) -> str:
        for name in names:
            prop = props.get(name, {})
            if prop.get("type") == "title" and prop.get("title"):
                return prop["title"][0].get("plain_text", "Untitled Project")
        return "Untitled Project"

    def _extract_select(self, props: Dict, names: List[str]) -> Optional[str]:
        for name in names:
            prop = props.get(name, {})
            if prop.get("type") == "select" and prop.get("select"):
                return prop["select"]["name"]
        return None

    def _extract_date(self, props: Dict, names: List[str]) -> Optional[datetime.date]:
        for name in names:
            prop = props.get(name, {})
            if prop.get("type") == "date" and prop.get("date"):
                return self.parse_date(prop["date"]["start"])
        return None

    def _extract_richtext(self, props: Dict, names: List[str]) -> str:
        for name in names:
            prop = props.get(name, {})
            if prop.get("type") == "rich_text" and prop.get("rich_text"):
                return prop["rich_text"][0].get("plain_text", "")
        return ""

    def summarize(self, projects: List[Dict]) -> Dict[str, List[Dict]]:
        summary = {
            "in_progress": [],
            "not_started": [],
            "on_hold": [],
            "done": [],
            "upcoming": [],
        }
        for project in projects:
            status = project["status"].lower()
            if status in ("in progress", "active"):
                summary["in_progress"].append(project)
            elif status in ("on hold", "paused"):
                summary["on_hold"].append(project)
            elif status in ("done", "completed"):
                summary["done"].append(project)
            else:
                summary["not_started"].append(project)

            if project["target_date"] and project["target_date"] <= self.upcoming_window:
                summary["upcoming"].append(project)
        return summary

    def format_project(self, project: Dict) -> str:
        category = f" • {project['category']}" if project["category"] else ""
        target = (
            f" • Target: {project['target_date']}"
            if project["target_date"]
            else ""
        )
        return f"- {project['name']} ({project['priority']}){category}{target}"

    def generate_report(self) -> str:
        raw = self.query_database()
        projects = [self.extract_project(item) for item in raw.get("results", [])]
        summary = self.summarize(projects)

        lines = []
        lines.append("Projects Summary")
        lines.append("")
        lines.append("In Progress:")
        lines.extend([self.format_project(p) for p in summary["in_progress"]] or ["- None"])
        lines.append("")
        lines.append("Not Started:")
        lines.extend([self.format_project(p) for p in summary["not_started"]] or ["- None"])
        lines.append("")
        lines.append("On Hold:")
        lines.extend([self.format_project(p) for p in summary["on_hold"]] or ["- None"])
        lines.append("")
        lines.append("Upcoming (next 2 weeks):")
        lines.extend([self.format_project(p) for p in summary["upcoming"]] or ["- None"])

        return "\n".join(lines)


def analyze_projects() -> str:
    return ProjectAnalyzer().generate_report()


if __name__ == "__main__":
    print(analyze_projects())
