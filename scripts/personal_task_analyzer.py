#!/usr/bin/env python3
"""
Personal Task Manager
Everything you need for personal task analysis from Notion.

Usage:
    from task_analyzer import analyze_personal_tasks
    report = analyze_personal_tasks()
    print(report)

Database ID: 2e85ae60-7903-8103-a2b5-f3961e369cfb
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from notion_client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TaskAnalyzer:
    """Analyzes personal tasks and generates actionable reports."""

    # Class constants
    DATABASE_ID = "2e85ae60-7903-8103-a2b5-f3961e369cfb"
    PRIORITY_EMOJIS = {
        "High": "🔴",
        "Critical": "🚨",
        "Medium": "🟡",
        "Low": "🟢",
        "Urgent": "🔴",
    }
    EFFORT_INDICATORS = {"Small": "⚡", "Medium": "🔨", "Large": "🏗️", "XL": "🏭"}

    def __init__(self):
        self.today = datetime.now().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.week_end = self.today + timedelta(days=7)

        # Initialize Notion client
        notion_token = os.getenv("NOTION_TOKEN")
        if not notion_token:
            raise ValueError("NOTION_TOKEN environment variable is required")
        self.notion = Client(auth=notion_token)

    def query_notion_database(self) -> Dict:
        """Query Notion database directly using notion-client."""
        try:
            response = self.notion.databases.query(database_id=self.DATABASE_ID)
            return response
        except Exception as e:
            print(f"Error querying Notion database: {e}")
            return {"results": []}

    def parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        """Parse date string from Notion API response."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.split("T")[0]).date()
        except (ValueError, AttributeError):
            return None

    def extract_task_data(self, page: Dict) -> Dict:
        """Extract and normalize task data from Notion page."""
        properties = page.get("properties", {})

        # Extract task name
        name = self._extract_text_property(properties, ["Task name", "Name", "Title"])

        # Extract completion status
        completed = self._extract_completion_status(properties)

        # Extract due date
        due_date = self._extract_date_property(
            properties, ["Due Date", "Due date", "Date", "Deadline"]
        )

        # Extract priority
        priority = self._extract_select_property(properties, ["Priority"], "Medium")

        # Extract tags
        tags = self._extract_multiselect_property(
            properties, ["Task type", "Tags", "Category"]
        )

        # Extract effort level
        effort = self._extract_select_property(properties, ["Effort", "Effort level"])

        # Extract description
        description = self._extract_richtext_property(properties, ["Description"])

        return {
            "id": page["id"],
            "name": name,
            "completed": completed,
            "due_date": due_date,
            "priority": priority,
            "tags": tags,
            "effort": effort,
            "description": description,
            "url": page.get("url", ""),
        }

    def _extract_text_property(self, properties: Dict, prop_names: List[str]) -> str:
        """Extract text from title property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "title" and prop.get("title"):
                return prop["title"][0].get("plain_text", "Unnamed Task")
        return "Unnamed Task"

    def _extract_completion_status(self, properties: Dict) -> bool:
        """Extract completion status from various property types."""
        status_prop = properties.get("Status", {})
        if status_prop.get("type") == "status" and status_prop.get("status"):
            status_name = status_prop["status"]["name"].lower()
            return status_name in ["done", "complete", "completed", "finished"]
        if status_prop.get("type") == "select" and status_prop.get("select"):
            status_name = status_prop["select"]["name"].lower()
            return status_name in ["done", "complete", "completed", "finished"]
        return False

    def _extract_date_property(
        self, properties: Dict, prop_names: List[str]
    ) -> Optional[datetime.date]:
        """Extract date from date property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "date" and prop.get("date"):
                return self.parse_date(prop["date"]["start"])
        return None

    def _extract_select_property(
        self, properties: Dict, prop_names: List[str], default: str = None
    ) -> Optional[str]:
        """Extract value from select property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "select" and prop.get("select"):
                return prop["select"]["name"]
        return default

    def _extract_multiselect_property(
        self, properties: Dict, prop_names: List[str]
    ) -> List[str]:
        """Extract values from multi-select property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "multi_select":
                return [tag["name"] for tag in prop.get("multi_select", [])]
            if prop.get("type") == "select" and prop.get("select"):
                return [prop["select"]["name"]]
        return []

    def _extract_richtext_property(
        self, properties: Dict, prop_names: List[str]
    ) -> str:
        """Extract text from rich text property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "rich_text" and prop.get("rich_text"):
                return prop["rich_text"][0].get("plain_text", "")
        return ""

    def categorize_tasks(self, tasks: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize tasks by urgency and completion status."""
        categories = {
            "overdue": [],
            "due_today_tomorrow": [],
            "due_this_week": [],
            "recently_completed": [],
            "active_backlog": [],
        }

        for task in tasks:
            if task["completed"]:
                categories["recently_completed"].append(task)
            elif task["due_date"]:
                if task["due_date"] < self.today:
                    categories["overdue"].append(task)
                elif task["due_date"] <= self.tomorrow:
                    categories["due_today_tomorrow"].append(task)
                elif task["due_date"] <= self.week_end:
                    categories["due_this_week"].append(task)
                else:
                    categories["active_backlog"].append(task)
            else:
                categories["active_backlog"].append(task)

        return categories

    def calculate_overdue_days(self, due_date: datetime.date) -> int:
        """Calculate how many days overdue a task is."""
        return max(0, (self.today - due_date).days)

    def format_task(
        self,
        task: Dict,
        show_overdue_days: bool = False,
        show_description: bool = False,
        show_id: bool = False,
    ) -> str:
        """Format a task for display."""
        priority_emoji = self.PRIORITY_EMOJIS.get(task["priority"], "🟡")
        effort_indicator = (
            self.EFFORT_INDICATORS.get(task["effort"], "") if task["effort"] else ""
        )
        tags_display = f" [{', '.join(task['tags'])}]" if task["tags"] else ""

        formatted = (
            f"{priority_emoji} {effort_indicator} {task['name']}{tags_display}".strip()
        )

        if show_overdue_days and task["due_date"]:
            days_overdue = self.calculate_overdue_days(task["due_date"])
            formatted += f" ({days_overdue} days overdue)"
        elif task["due_date"]:
            formatted += f" (Due: {task['due_date'].strftime('%m/%d')})"

        # Add full page ID
        if show_id:
            formatted += f" [ID: {task['id']}]"

        if show_description and task["description"]:
            description = task["description"][:100] + (
                "..." if len(task["description"]) > 100 else ""
            )
            formatted += f"\n    └─ {description}"

        return formatted

    def generate_report(self, task_data: List[Dict]) -> str:
        """Generate comprehensive task analysis report."""
        # Process and categorize tasks
        tasks = [self.extract_task_data(page) for page in task_data]
        categories = self.categorize_tasks(tasks)

        # Calculate metrics
        total_active = sum(
            len(categories[cat])
            for cat in [
                "overdue",
                "due_today_tomorrow",
                "due_this_week",
                "active_backlog",
            ]
        )
        total_completed = len(categories["recently_completed"])
        completion_rate = (
            round(total_completed / (total_active + total_completed) * 100)
            if (total_active + total_completed) > 0
            else 0
        )

        # Build report sections
        sections = []
        sections.append("# 📋 Personal Task Analysis")
        sections.append(f"*Generated: {self.today.strftime('%A, %B %d, %Y')}*\n")

        # Add task sections
        self._add_overdue_section(sections, categories["overdue"])
        self._add_urgent_section(sections, categories["due_today_tomorrow"])
        self._add_weekly_section(sections, categories["due_this_week"])
        self._add_completed_section(sections, categories["recently_completed"])
        self._add_backlog_section(sections, categories["active_backlog"])

        # Add summary
        self._add_summary_section(sections, categories, total_active, completion_rate)

        return "\n".join(sections)

    def _add_overdue_section(self, sections: List[str], overdue_tasks: List[Dict]):
        """Add overdue tasks section to report."""
        if overdue_tasks:
            sections.append("## 🔴 OVERDUE TASKS")
            sorted_tasks = sorted(
                overdue_tasks, key=lambda x: x["due_date"] or self.today
            )
            for task in sorted_tasks:
                sections.append(
                    f"• {self.format_task(task, show_overdue_days=True, show_description=True, show_id=True)}"
                )
            sections.append("")

    def _add_urgent_section(self, sections: List[str], urgent_tasks: List[Dict]):
        """Add urgent tasks section to report."""
        if urgent_tasks:
            sections.append("## ⚡ DUE TODAY/TOMORROW")
            sorted_tasks = sorted(
                urgent_tasks, key=lambda x: x["due_date"] or self.today
            )
            for task in sorted_tasks:
                urgency_tag = (
                    "🔥 TODAY" if task["due_date"] == self.today else "📅 TOMORROW"
                )
                sections.append(
                    f"• {urgency_tag} - {self.format_task(task, show_description=True, show_id=True)}"
                )
            sections.append("")

    def _add_weekly_section(self, sections: List[str], weekly_tasks: List[Dict]):
        """Add weekly tasks section to report."""
        if weekly_tasks:
            sections.append("## 📅 DUE THIS WEEK")
            sorted_tasks = sorted(
                weekly_tasks, key=lambda x: x["due_date"] or self.today
            )
            for task in sorted_tasks:
                sections.append(
                    f"• {self.format_task(task, show_description=True, show_id=True)}"
                )
            sections.append("")

    def _add_completed_section(self, sections: List[str], completed_tasks: List[Dict]):
        """Add completed tasks section to report."""
        if completed_tasks:
            sections.append("## ✅ RECENTLY COMPLETED")
            for task in completed_tasks[:5]:  # Show top 5
                sections.append(f"• {self.format_task(task, show_id=True)}")
            sections.append("")

    def _add_backlog_section(self, sections: List[str], backlog_tasks: List[Dict]):
        """Add backlog tasks section to report."""
        if backlog_tasks:
            sections.append("## 📝 ACTIVE BACKLOG")
            for task in backlog_tasks[:8]:  # Show top 8
                sections.append(f"• {self.format_task(task, show_id=True)}")
            if len(backlog_tasks) > 8:
                sections.append(f"• ... and {len(backlog_tasks) - 8} more items")
            sections.append("")

    def _add_summary_section(
        self,
        sections: List[str],
        categories: Dict,
        total_active: int,
        completion_rate: int,
    ):
        """Add summary section to report."""
        sections.append("## 📊 SUMMARY")
        sections.append(f"• **Total Active Tasks:** {total_active}")
        sections.append(f"• **Overdue:** {len(categories['overdue'])}")
        sections.append(
            f"• **Due Today/Tomorrow:** {len(categories['due_today_tomorrow'])}"
        )
        sections.append(f"• **Due This Week:** {len(categories['due_this_week'])}")
        sections.append(f"• **Completion Rate:** {completion_rate}%")

        if categories["overdue"] or categories["due_today_tomorrow"]:
            priority_count = len(categories["overdue"]) + len(
                categories["due_today_tomorrow"]
            )
            sections.append(
                f"• **🚨 Action Required:** {priority_count} high-priority tasks"
            )


def analyze_personal_tasks() -> str:
    """
    Main function to analyze personal tasks - queries Notion directly.

    Returns:
        Formatted analysis report string
    """
    analyzer = TaskAnalyzer()
    notion_data = analyzer.query_notion_database()
    task_pages = notion_data.get("results", [])
    return analyzer.generate_report(task_pages)


if __name__ == "__main__":
    # CLI usage
    print(analyze_personal_tasks())
