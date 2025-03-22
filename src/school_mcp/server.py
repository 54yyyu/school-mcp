"""Main MCP server module for school tools."""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP, Context

from .deadline_scraper import DeadlineScraper
from .file_downloader import CanvasDownloader
from .reminders import ReminderManager
from .config import get_download_path, save_download_path

# Initialize FastMCP server
mcp = FastMCP("School Tools")

# =====================
# Deadline Tools
# =====================

@mcp.tool()
async def get_deadlines(days_ahead: int = 14) -> str:
    """
    Get upcoming deadlines from Canvas and Gradescope.
    
    Args:
        days_ahead: Number of days to look ahead for assignments (default: 14)
    """
    try:
        scraper = DeadlineScraper()
        assignments = scraper.get_all_assignments(days_ahead)
        
        if not assignments:
            return "No upcoming deadlines found."
        
        return json.dumps(assignments, indent=2)
    except Exception as e:
        return f"Error getting deadlines: {str(e)}"

@mcp.tool()
async def add_to_reminders(days_ahead: int = 14) -> str:
    """
    Add upcoming deadlines to macOS Reminders.
    
    Args:
        days_ahead: Number of days to look ahead for assignments (default: 14)
    """
    try:
        # Get assignments
        scraper = DeadlineScraper()
        assignments = scraper.get_all_assignments(days_ahead)
        
        if not assignments:
            return "No upcoming deadlines found to add to Reminders."
        
        # Add to Reminders
        reminder_manager = ReminderManager("Course Assignments")
        result = reminder_manager.add_assignments(assignments)
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error adding to Reminders: {str(e)}"

# =====================
# Canvas File Tools
# =====================

@mcp.tool()
async def list_courses() -> str:
    """
    List available courses from Canvas.
    """
    try:
        downloader = CanvasDownloader()
        courses = downloader.get_current_courses()
        
        if not courses:
            return "No active courses found."
        
        return json.dumps(courses, indent=2)
    except Exception as e:
        return f"Error listing courses: {str(e)}"

@mcp.tool()
async def download_course_files(course_id: int, download_path: Optional[str] = None) -> str:
    """
    Download files from a Canvas course.
    
    Args:
        course_id: Canvas course ID
        download_path: Path to download files to (optional, will use default if not provided)
    """
    try:
        downloader = CanvasDownloader()
        
        # Validate course_id
        courses = downloader.get_current_courses()
        course_exists = any(c["id"] == course_id for c in courses)
        
        if not course_exists:
            return f"Course with ID {course_id} not found."
        
        # Use default path if none provided
        if not download_path:
            download_path = get_download_path()
        
        # Download files
        result = downloader.download_all_course_files(course_id, download_path)
        
        return json.dumps({
            "status": "success",
            "message": f"Downloaded {result['stats']['successful']} files " +
                      f"({result['stats']['skipped']} skipped, {result['stats']['failed']} failed)",
            "course_name": result["course_name"],
            "download_path": result["base_path"],
            "stats": result["stats"]
        }, indent=2)
    except Exception as e:
        return f"Error downloading course files: {str(e)}"

@mcp.tool()
async def set_download_path(path: str) -> str:
    """
    Set the default download path for Canvas files.
    
    Args:
        path: Path to save downloaded files to
    """
    try:
        # Validate path
        if not os.path.isdir(path):
            return f"Error: Path '{path}' is not a valid directory."
        
        # Save path
        save_download_path(path)
        
        return f"Download path set to: {path}"
    except Exception as e:
        return f"Error setting download path: {str(e)}"

@mcp.tool()
async def get_download_path_info() -> str:
    """
    Get the current default download path for Canvas files.
    """
    try:
        path = get_download_path()
        return f"Current download path: {path}"
    except Exception as e:
        return f"Error getting download path: {str(e)}"

# Run the server
if __name__ == "__main__":
    mcp.run()
