#!/usr/bin/env python3
"""
Legacy Work Task Manager (Deprecated)

This repository is now personal-focused. This script is kept for reference
only and is not wired to any active Notion databases.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from notion_client import Client
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class WorkTaskAnalyzer:
    """Analyzes work tasks and generates actionable reports."""

    # Class constants (legacy placeholders)
    TODO_DATABASE_ID = ""
    ALL_SPRINTS_DATABASE_ID = ""
    MEETINGS_DATABASE = ""
    YOUR_NAME_USER_ID = ""
    TEAM_MEMBER_USER_ID = ""

    TAG_EMOJIS = {
        "Build": "🛠️",
        "Serve": "🤝",
        "Sell": "💰",
        "Raise": "💸",
        "Admin": "📋",
        "META": "🎯",
        "Learn": "📚",
        "Measure": "📊",
        "Maintain": "🔧",
    }

    def __init__(self):
        raise RuntimeError(
            "Deprecated: use scripts/personal_task_analyzer.py for personal tasks."
        )
        self.today = datetime.now().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.week_end = self.today + timedelta(days=7)

        # Initialize Notion client
        notion_token = os.getenv("NOTION_TOKEN")
        if not notion_token:
            raise ValueError("NOTION_TOKEN environment variable is required")
        self.notion = Client(auth=notion_token)

    def find_current_sprint(self) -> Optional[Dict]:
        """Find the current sprint based on today's date."""
        try:
            # Query all sprints and find current one manually
            response = self.notion.databases.query(
                database_id=self.ALL_SPRINTS_DATABASE_ID
            )

            sprints = response.get("results", [])
            for sprint in sprints:
                date_prop = sprint["properties"].get("Date", {})
                if date_prop.get("type") == "date" and date_prop.get("date"):
                    date_range = date_prop["date"]
                    start_date = self.parse_date(date_range.get("start"))
                    end_date = self.parse_date(date_range.get("end"))

                    if start_date and end_date:
                        if start_date <= self.today <= end_date:
                            return sprint  # Return full sprint object

            return None
        except Exception as e:
            print(f"Error finding current sprint: {e}")
            return None

    def find_latest_sprint_planning(self) -> Optional[Dict]:
        """Find the latest Sprint Planning meeting."""
        try:
            response = self.notion.databases.query(
                database_id=self.MEETINGS_DATABASE,
                filter={"property": "Name", "title": {"contains": "Sprint Planning"}},
                sorts=[{"property": "Created time", "direction": "descending"}],
            )

            meetings = response.get("results", [])
            if meetings:
                return meetings[0]  # Return the most recent sprint planning meeting
            return None
        except Exception as e:
            print(f"Error finding sprint planning meeting: {e}")
            return None

    def get_page_content(self, page_id: str) -> str:
        """Get the content of a Notion page."""
        try:
            response = self.notion.blocks.children.list(block_id=page_id)
            blocks = response.get("results", [])

            content_parts = []
            for block in blocks:
                if block["type"] == "paragraph" and block.get("paragraph", {}).get(
                    "rich_text"
                ):
                    text = "".join(
                        [text["plain_text"] for text in block["paragraph"]["rich_text"]]
                    )
                    if text.strip():
                        content_parts.append(text)
                elif block["type"] == "bulleted_list_item" and block.get(
                    "bulleted_list_item", {}
                ).get("rich_text"):
                    text = "".join(
                        [
                            text["plain_text"]
                            for text in block["bulleted_list_item"]["rich_text"]
                        ]
                    )
                    if text.strip():
                        content_parts.append(f"• {text}")
                elif block["type"] == "heading_1" and block.get("heading_1", {}).get(
                    "rich_text"
                ):
                    text = "".join(
                        [text["plain_text"] for text in block["heading_1"]["rich_text"]]
                    )
                    if text.strip():
                        content_parts.append(f"# {text}")
                elif block["type"] == "heading_2" and block.get("heading_2", {}).get(
                    "rich_text"
                ):
                    text = "".join(
                        [text["plain_text"] for text in block["heading_2"]["rich_text"]]
                    )
                    if text.strip():
                        content_parts.append(f"## {text}")
                elif block["type"] == "heading_3" and block.get("heading_3", {}).get(
                    "rich_text"
                ):
                    text = "".join(
                        [text["plain_text"] for text in block["heading_3"]["rich_text"]]
                    )
                    if text.strip():
                        content_parts.append(f"### {text}")

            return "\n".join(content_parts)
        except Exception as e:
            print(f"Error getting page content: {e}")
            return ""

    def query_work_tasks(self) -> tuple[Dict, Optional[Dict]]:
        """Query work tasks for current sprint from TODO database."""
        try:
            # First find the current sprint
            current_sprint = self.find_current_sprint()
            if not current_sprint:
                print("No current sprint found, querying all incomplete tasks")
                # Fallback: query all incomplete tasks
                response = self.notion.databases.query(
                    database_id=self.TODO_DATABASE_ID,
                    filter={"property": "Checkbox", "checkbox": {"equals": False}},
                )
                return response, None

            # Query tasks linked to current sprint
            response = self.notion.databases.query(
                database_id=self.TODO_DATABASE_ID,
                filter={
                    "and": [
                        {
                            "property": "Sprint",
                            "relation": {"contains": current_sprint["id"]},
                        },
                        {"property": "Checkbox", "checkbox": {"equals": False}},
                    ]
                },
            )
            return response, current_sprint
        except Exception as e:
            print(f"Error querying work tasks: {e}")
            return {"results": []}, None

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
        name = self._extract_text_property(properties, ["Name"])

        # Extract completion status
        completed = self._extract_checkbox_property(properties, "Checkbox")

        # Extract due date
        due_date = self._extract_date_property(properties, ["Due Date"])

        # Extract tags
        tags = self._extract_multiselect_property(properties, ["Tags"])

        # Extract sprint
        sprint = self._extract_relation_property(properties, ["Sprint"])

        # Extract person/assignee
        person = self._extract_people_property(properties, ["Person"])

        return {
            "id": page["id"],
            "name": name,
            "completed": completed,
            "due_date": due_date,
            "tags": tags,
            "sprint": sprint,
            "person": person,
            "url": page.get("url", ""),
        }

    def _extract_text_property(self, properties: Dict, prop_names: List[str]) -> str:
        """Extract text from title property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "title" and prop.get("title"):
                return prop["title"][0].get("plain_text", "Unnamed Task")
        return "Unnamed Task"

    def _extract_checkbox_property(self, properties: Dict, prop_name: str) -> bool:
        """Extract checkbox value."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "checkbox":
            return prop.get("checkbox", False)
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

    def _extract_multiselect_property(
        self, properties: Dict, prop_names: List[str]
    ) -> List[str]:
        """Extract values from multi-select property."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "multi_select":
                return [tag["name"] for tag in prop.get("multi_select", [])]
        return []

    def _extract_relation_property(
        self, properties: Dict, prop_names: List[str]
    ) -> List[str]:
        """Extract relation IDs."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "relation":
                return [rel["id"] for rel in prop.get("relation", [])]
        return []

    def _extract_people_property(
        self, properties: Dict, prop_names: List[str]
    ) -> List[str]:
        """Extract people names."""
        for prop_name in prop_names:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "people":
                return [person["name"] for person in prop.get("people", [])]
        return []

    def categorize_tasks(self, tasks: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize tasks by urgency, type, and person."""
        categories = {
            "overdue": [],
            "due_today_tomorrow": [],
            "due_this_week": [],
            "no_due_date": [],
            "by_tag": {},
            "by_person": {},
        }

        for task in tasks:
            # Categorize by urgency
            if task["due_date"]:
                if task["due_date"] < self.today:
                    categories["overdue"].append(task)
                elif task["due_date"] <= self.tomorrow:
                    categories["due_today_tomorrow"].append(task)
                elif task["due_date"] <= self.week_end:
                    categories["due_this_week"].append(task)
            else:
                categories["no_due_date"].append(task)

            # Categorize by tag
            for tag in task["tags"]:
                if tag not in categories["by_tag"]:
                    categories["by_tag"][tag] = []
                categories["by_tag"][tag].append(task)

            # Categorize by person
            for person in task["person"]:
                if person not in categories["by_person"]:
                    categories["by_person"][person] = []
                categories["by_person"][person].append(task)

        return categories

    def calculate_overdue_days(self, due_date: datetime.date) -> int:
        """Calculate how many days overdue a task is."""
        return max(0, (self.today - due_date).days)

    def format_task(
        self,
        task: Dict,
        show_overdue_days: bool = False,
        show_person: bool = False,
        show_id: bool = False,
    ) -> str:
        """Format a task for display."""
        tag_emojis = [self.TAG_EMOJIS.get(tag, "📌") for tag in task["tags"]]
        emoji_display = "".join(tag_emojis[:2]) if tag_emojis else "📌"
        tags_display = f" [{', '.join(task['tags'])}]" if task["tags"] else ""
        person_display = (
            f" [@{', '.join(task['person'])}]" if show_person and task["person"] else ""
        )

        formatted = f"{emoji_display} {task['name']}{tags_display}{person_display}"

        if show_overdue_days and task["due_date"]:
            days_overdue = self.calculate_overdue_days(task["due_date"])
            formatted += f" ({days_overdue} days overdue)"
        elif task["due_date"]:
            formatted += f" (Due: {task['due_date'].strftime('%m/%d')})"

        # Add full page ID
        if show_id:
            formatted += f" [ID: {task['id']}]"

        return formatted

    def generate_report(
        self, task_data: List[Dict], current_sprint: Optional[Dict] = None
    ) -> str:
        """Generate comprehensive work task analysis report."""
        # Process and categorize tasks
        tasks = [self.extract_task_data(page) for page in task_data]
        categories = self.categorize_tasks(tasks)

        # Calculate metrics
        total_tasks = len(tasks)
        overdue_count = len(categories["overdue"])
        urgent_count = len(categories["due_today_tomorrow"])

        # Build report sections
        sections = []
        sections.append("# 🛠️ Work Task Analysis")
        sections.append(f"*Generated: {self.today.strftime('%A, %B %d, %Y')}*\n")

        # Add current sprint context
        self._add_current_sprint_section(sections, current_sprint)

        # Add sprint planning context
        self._add_sprint_planning_section(sections)

        # Add task sections
        self._add_overdue_section(sections, categories["overdue"])
        self._add_urgent_section(sections, categories["due_today_tomorrow"])
        self._add_weekly_section(sections, categories["due_this_week"])
        self._add_person_breakdown(sections, categories["by_person"])

        # Add summary
        self._add_summary_section(sections, total_tasks, overdue_count, urgent_count)

        return "\n".join(sections)

    def _add_current_sprint_section(
        self, sections: List[str], current_sprint: Optional[Dict]
    ):
        """Add current sprint information to report."""
        if current_sprint:
            try:
                # Extract sprint name
                name_prop = current_sprint["properties"].get("Name", {})
                sprint_name = "Unknown Sprint"
                if name_prop.get("type") == "title" and name_prop.get("title"):
                    sprint_name = name_prop["title"][0].get(
                        "plain_text", "Unknown Sprint"
                    )

                # Extract sprint dates
                date_prop = current_sprint["properties"].get("Date", {})
                date_range_str = ""
                if date_prop.get("type") == "date" and date_prop.get("date"):
                    date_range = date_prop["date"]
                    start_date = self.parse_date(date_range.get("start"))
                    end_date = self.parse_date(date_range.get("end"))
                    if start_date and end_date:
                        date_range_str = f" ({start_date.strftime('%m/%d')} - {end_date.strftime('%m/%d')})"

                sections.append("## 🎯 CURRENT SPRINT")
                sections.append(f"**{sprint_name}**{date_range_str}")
                sections.append("")
            except Exception as e:
                print(f"Error adding current sprint section: {e}")
                sections.append("## 🎯 CURRENT SPRINT")
                sections.append("*Sprint information unavailable*")
                sections.append("")
        else:
            sections.append("## 🎯 CURRENT SPRINT")
            sections.append("*No active sprint found*")
            sections.append("")

    def _add_sprint_planning_section(self, sections: List[str]):
        """Add sprint planning context to report."""
        try:
            sprint_planning = self.find_latest_sprint_planning()
            if sprint_planning:
                sections.append("## 📋 LATEST SPRINT PLANNING")

                # Get meeting date
                date_prop = sprint_planning["properties"].get("Event time", {})
                if date_prop.get("type") == "date" and date_prop.get("date"):
                    meeting_date = self.parse_date(date_prop["date"]["start"])
                    if meeting_date:
                        sections.append(
                            f"*Meeting Date: {meeting_date.strftime('%B %d, %Y')}*"
                        )

                # Get page content
                content = self.get_page_content(sprint_planning["id"])
                if content:
                    # Limit content to prevent overwhelming output
                    content_lines = content.split("\n")
                    if len(content_lines) > 15:
                        content = (
                            "\n".join(content_lines[:15]) + "\n... (content truncated)"
                        )
                    sections.append(content)
                else:
                    sections.append("*No content available*")

                sections.append("")
        except Exception as e:
            print(f"Error adding sprint planning section: {e}")

    def _add_overdue_section(self, sections: List[str], overdue_tasks: List[Dict]):
        """Add overdue tasks section to report."""
        if overdue_tasks:
            sections.append("## 🔴 OVERDUE TASKS")
            sorted_tasks = sorted(
                overdue_tasks, key=lambda x: x["due_date"] or self.today
            )
            for task in sorted_tasks:
                sections.append(
                    f"• {self.format_task(task, show_overdue_days=True, show_person=True, show_id=True)}"
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
                    f"• {urgency_tag} - {self.format_task(task, show_person=True, show_id=True)}"
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
                    f"• {self.format_task(task, show_person=True, show_id=True)}"
                )
            sections.append("")

    def _add_person_breakdown(self, sections: List[str], person_dict: Dict):
        """Add breakdown by person."""
        if person_dict:
            sections.append("## 👥 BY PERSON")
            for person, person_tasks in sorted(person_dict.items()):
                person_emoji = "🧑‍💻" if "Your Name" in person else "🧑‍💼"
                overdue_count = len(
                    [
                        t
                        for t in person_tasks
                        if t["due_date"] and t["due_date"] < self.today
                    ]
                )
                sections.append(
                    f"### {person_emoji} {person} ({len(person_tasks)} tasks, {overdue_count} overdue)"
                )
                for task in person_tasks:  # Show all tasks per person
                    sections.append(f"• {self.format_task(task, show_id=True)}")
                sections.append("")

    def _add_tag_breakdown(self, sections: List[str], tags_dict: Dict):
        """Add breakdown by tags."""
        if tags_dict:
            sections.append("## 📊 BY CATEGORY")
            for tag, tag_tasks in sorted(tags_dict.items()):
                emoji = self.TAG_EMOJIS.get(tag, "📌")
                sections.append(f"### {emoji} {tag} ({len(tag_tasks)} tasks)")
                for task in tag_tasks[:3]:  # Show top 3 per category
                    sections.append(f"• {self.format_task(task)}")
                if len(tag_tasks) > 3:
                    sections.append(f"• ... and {len(tag_tasks) - 3} more")
                sections.append("")

    def _add_no_date_section(self, sections: List[str], no_date_tasks: List[Dict]):
        """Add tasks without due dates."""
        if no_date_tasks:
            sections.append("## 📝 NO DUE DATE")
            for task in no_date_tasks[:5]:  # Show top 5
                sections.append(f"• {self.format_task(task)}")
            if len(no_date_tasks) > 5:
                sections.append(f"• ... and {len(no_date_tasks) - 5} more items")
            sections.append("")

    def _add_summary_section(
        self, sections: List[str], total: int, overdue: int, urgent: int
    ):
        """Add summary section to report."""
        sections.append("## 📊 SUMMARY")
        sections.append(f"• **Total Active Tasks:** {total}")
        sections.append(f"• **Overdue:** {overdue}")
        sections.append(f"• **Due Today/Tomorrow:** {urgent}")

        if overdue > 0 or urgent > 0:
            priority_count = overdue + urgent
            sections.append(
                f"• **🚨 Action Required:** {priority_count} high-priority tasks"
            )


def analyze_work_tasks() -> str:
    """
    Main function to analyze work tasks - queries Notion directly.

    Returns:
        Formatted analysis report string
    """
    analyzer = WorkTaskAnalyzer()
    notion_data, current_sprint = analyzer.query_work_tasks()
    task_pages = notion_data.get("results", [])
    return analyzer.generate_report(task_pages, current_sprint)


if __name__ == "__main__":
    # CLI usage
    print(analyze_work_tasks())
