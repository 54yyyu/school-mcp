"""Reminders module for adding deadlines to macOS Reminders."""

import re
import subprocess
from typing import Dict, Any, Optional
import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import pytz

@dataclass
class ReminderInfo:
    """Data class for reminder information."""
    title: str
    notes: str
    due_date: str
    list_name: str = "Course Assignments"

class ReminderManager:
    """Class for managing macOS Reminders."""
    
    def __init__(self, list_name: str = "Course Assignments"):
        """Initialize reminder manager with a specific list name."""
        self.list_name = list_name
        self._ensure_list_exists()

    def _ensure_list_exists(self) -> bool:
        """Create the reminder list if it doesn't exist."""
        # Single-line script to avoid potential syntax issues
        script = f'tell application "Reminders" to if not (exists list "{self.list_name}") then make new list with properties {{name:"{self.list_name}"}}'
        return self._run_applescript(script) is not None

    def _run_applescript(self, script: str) -> Optional[str]:
        """Execute an AppleScript and return its output."""
        try:
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode != 0:
                print(f"AppleScript error (code {result.returncode}): {result.stderr}")
                return None
            return result.stdout.strip()
        except Exception as e:
            print(f"Exception running AppleScript: {str(e)}")
            return None

    def _clean_title(self, title: str) -> str:
        """Clean the title for AppleScript."""
        # Remove or replace problematic characters
        return re.sub(r'["\\\{\}]', '', title)

    def add_reminder(self, reminder_info: ReminderInfo) -> Dict[str, Any]:
        """Add a reminder to Reminders."""
        # Clean strings for AppleScript
        title = self._clean_title(reminder_info.title)
        notes = self._clean_title(reminder_info.notes)
        
        # Simple single-line script approach to avoid potential syntax issues
        script = f'tell application "Reminders" to tell list "{reminder_info.list_name}" to make new reminder with properties {{name:"{title}", body:"{notes}"}}'
        
        result = self._run_applescript(script)
        
        if result is not None:
            return {
                "status": "success",
                "message": "Reminder added successfully",
                "title": title,
                "list": reminder_info.list_name
            }
        else:
            return {
                "status": "error",
                "message": "Failed to add reminder",
                "title": title,
                "list": reminder_info.list_name
            }

    def clear_all_assignments(self) -> Dict[str, Any]:
        """Clear all reminders from the assignments list."""
        # Single-line script to avoid potential syntax issues
        script = f'tell application "Reminders" to delete every reminder of list "{self.list_name}"'
        
        result = self._run_applescript(script)
        
        if result is not None:
            return {
                "status": "success",
                "message": f"All reminders cleared from list '{self.list_name}'",
                "list": self.list_name
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to clear reminders from list '{self.list_name}'",
                "list": self.list_name
            }

    def add_assignment(self, assignment: Dict[str, Any]) -> Dict[str, Any]:
        """Add an assignment to Reminders."""
        # Format the notes section
        notes = f"Course: {assignment['course_name']}\n"
        if assignment.get('points_possible'):
            notes += f"Points: {assignment['points_possible']}\n"
        if assignment.get('url'):
            notes += f"URL: {assignment['url']}\n"
        if assignment.get('late_due_date'):
            notes += f"Late submission deadline: {assignment['late_due_date']}\n"
        if assignment.get('time_remaining'):
            notes += f"Time remaining: {assignment['time_remaining']}\n"
        if assignment.get('due_date'):
            notes += f"Due: {assignment['due_date']}\n"
        
        # Create title
        title = f"[{assignment['platform']}] {assignment['assignment_name']}"
        
        # Create ReminderInfo without the due_date (will be added to notes instead)
        reminder_info = ReminderInfo(
            title=title,
            notes=notes,
            due_date="",  # Empty due date to avoid date parsing issues
            list_name=self.list_name
        )
        
        return self.add_reminder(reminder_info)

    def add_assignments(self, assignments: list) -> Dict[str, Any]:
        """Add multiple assignments to Reminders."""
        results = []
        successful = 0
        failed = 0
        
        # First clear existing reminders
        clear_result = self.clear_all_assignments()
        if clear_result["status"] != "success":
            print("Warning: Failed to clear existing reminders")
        
        # Add all assignments
        for assignment in assignments:
            result = self.add_assignment(assignment)
            results.append(result)
            
            if result["status"] == "success":
                successful += 1
            else:
                failed += 1
        
        return {
            "status": "success" if failed == 0 else "partial",
            "message": f"Added {successful} reminders, {failed} failed",
            "results": results,
            "stats": {
                "total": len(assignments),
                "successful": successful,
                "failed": failed
            }
        }
