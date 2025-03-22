"""Deadline scraper module for fetching Canvas and Gradescope assignments."""

from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re
import pytz
import pandas as pd
from datetime import datetime, timedelta
from gradescopeapi.classes.connection import GSConnection
from canvasapi import Canvas
from .config import get_config

class Platform(Enum):
    """Platforms for assignments."""
    CANVAS = "Canvas"
    GRADESCOPE = "Gradescope"

@dataclass
class Assignment:
    """Data class for an assignment."""
    platform: Platform
    course_name: str
    assignment_name: str
    due_date: datetime
    late_due_date: Optional[datetime] = None
    points_possible: Optional[float] = None
    url: Optional[str] = None
    status: Optional[str] = None

class DeadlineScraper:
    """Class for scraping deadlines from Canvas and Gradescope."""
    
    def __init__(self):
        """Initialize connections to Canvas and Gradescope."""
        try:
            config = get_config()
            
            # Initialize Gradescope
            self.gs_connection = GSConnection()
            self.gs_connection.login(
                config['gradescope_email'], 
                config['gradescope_password']
            )
            
            # Initialize Canvas
            domain = config['canvas_domain'].replace('https://', '').replace('http://', '')
            self.canvas = Canvas(f'https://{domain}', config['canvas_access_token'])
            
        except Exception as e:
            raise ValueError(f"Error initializing DeadlineScraper: {str(e)}")

    def _get_current_term_info(self) -> Tuple[str, str, str]:
        """
        Determine current academic term information including term code.
        Returns tuple of (term_name, year, term_code)
        where term_code is: 1=spring, 2=summer, 3=fall
        """
        now = datetime.now()
        year = str(now.year)
        
        if 1 <= now.month <= 5:  # Spring
            return ('Spring', year, '1')
        elif 6 <= now.month <= 8:  # Summer
            return ('Summer', year, '2')
        else:  # Fall
            return ('Fall', year, '3')

    def _get_current_term(self) -> Tuple[str, str]:
        """
        Get current term info for Gradescope (term name and year only).
        Returns tuple of (term_name, year)
        """
        term, year, _ = self._get_current_term_info()
        return term, year

    def _is_current_term_course(self, course_name: str) -> bool:
        """
        Check if a course belongs to the current term based on both standardized
        course codes and text patterns.
        """
        current_term, current_year, current_term_code = self._get_current_term_info()
        
        # Try to match standardized format first (e.g., ECONUN1155_001_2024_1)
        standardized_pattern = r'.*_\d{3}_(\d{4})_(\d).*'
        match = re.match(standardized_pattern, course_name)
        
        if match:
            year, term_code = match.groups()
            return year == current_year and term_code == current_term_code
        
        # If no match, check text-based patterns
        course_lower = course_name.lower()
        term_lower = current_term.lower()
        
        # Common term patterns in text-based course names
        term_patterns = [
            f"{term_lower} {current_year}",     # "spring 2024"
            f"{term_lower}{current_year}",      # "spring2024"
            f"{current_year}{term_lower}",      # "2024spring"
            f"{term_lower}'{current_year[2:]}", # "spring'24"
            f"{term_lower} '{current_year[2:]}" # "spring '24"
        ]
        
        return any(pattern in course_lower for pattern in term_patterns)

    def get_gradescope_assignments(self, days_ahead: int = 14) -> List[Assignment]:
        """Get upcoming assignments from Gradescope."""
        try:
            # Get current courses
            courses = self.gs_connection.account.get_courses()
            current_term, current_year = self._get_current_term()
            active_courses = []
            
            if "student" in courses:
                for course_id, course in courses["student"].items():
                    if course.semester == current_term and course.year == current_year:
                        active_courses.append({
                            'id': course_id,
                            'name': course.full_name,
                            'short_name': course.name
                        })
            
            # Get assignments for each course
            assignments_list = []
            for course in active_courses:
                assignments = self.gs_connection.account.get_assignments(course['id'])
                
                for assignment in assignments:
                    if getattr(assignment, 'submissions_status', None) != 'Submitted':
                        due_date = getattr(assignment, 'due_date', None)
                        if due_date and due_date > datetime.now(due_date.tzinfo):
                            # Check if it's within the days_ahead limit
                            if due_date <= datetime.now(due_date.tzinfo) + timedelta(days=days_ahead):
                                assignments_list.append(Assignment(
                                    platform=Platform.GRADESCOPE,
                                    course_name=course['name'],
                                    assignment_name=assignment.name,
                                    due_date=due_date,
                                    late_due_date=getattr(assignment, 'late_due_date', None),
                                    status=getattr(assignment, 'submissions_status', 'Not submitted')
                                ))
            
            return assignments_list
        except Exception as e:
            raise ValueError(f"Error fetching Gradescope assignments: {str(e)}")

    def get_canvas_assignments(self, days_ahead: int = 14) -> List[Assignment]:
        """Get upcoming assignments from Canvas."""
        try:
            # Get all active courses first
            all_courses = list(self.canvas.get_courses(
                enrollment_type='student',
                enrollment_state='active'
            ))
            
            # Filter for current term courses
            current_courses = [
                course for course in all_courses 
                if self._is_current_term_course(course.name)
            ]
            
            upcoming_assignments = []
            cutoff_date = datetime.now(pytz.UTC) + timedelta(days=days_ahead)
            
            for course in current_courses:
                try:
                    assignments = list(course.get_assignments())
                    
                    for assignment in assignments:
                        due_date = getattr(assignment, 'due_at', None)
                        if due_date:
                            due_date = pd.to_datetime(due_date)
                            
                            if (due_date <= cutoff_date and 
                                due_date >= datetime.now(pytz.UTC) and 
                                getattr(assignment, 'published', False)):
                                
                                try:
                                    submission = assignment.get_submission(
                                        self.canvas.get_current_user().id
                                    )
                                    submission_status = submission.workflow_state
                                except Exception:
                                    submission_status = 'No submission'
                                
                                if submission_status not in ['submitted', 'graded']:
                                    upcoming_assignments.append(Assignment(
                                        platform=Platform.CANVAS,
                                        course_name=course.name,
                                        assignment_name=assignment.name,
                                        due_date=due_date,
                                        late_due_date=None,
                                        points_possible=getattr(assignment, 'points_possible', None),
                                        url=getattr(assignment, 'html_url', None),
                                        status=submission_status
                                    ))
                except Exception:
                    continue
            
            return upcoming_assignments
        
        except Exception as e:
            raise ValueError(f"Error fetching Canvas assignments: {str(e)}")

    def get_all_assignments(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """Get all assignments from Canvas and Gradescope as a list of dictionaries."""
        try:
            # Get assignments from both platforms
            gradescope_assignments = self.get_gradescope_assignments(days_ahead)
            canvas_assignments = self.get_canvas_assignments(days_ahead)
            
            # Combine assignments
            all_assignments = gradescope_assignments + canvas_assignments
            
            # Sort assignments by due date
            all_assignments.sort(key=lambda x: x.due_date)
            
            # Convert to dictionaries
            assignment_dicts = []
            local_tz = datetime.now().astimezone().tzinfo
            
            for assignment in all_assignments:
                # Convert due date to local timezone
                due_date = assignment.due_date
                if isinstance(due_date, pd.Timestamp):
                    if due_date.tz is None:
                        due_date = due_date.tz_localize('UTC')
                    due_date = due_date.tz_convert(local_tz)
                else:
                    if due_date.tzinfo is None:
                        due_date = pytz.UTC.localize(due_date)
                    due_date = due_date.astimezone(local_tz)
                
                # Format the late due date
                late_due_date = None
                if assignment.late_due_date:
                    late_date = assignment.late_due_date
                    if isinstance(late_date, pd.Timestamp):
                        if late_date.tz is None:
                            late_date = late_date.tz_localize('UTC')
                        late_date = late_date.tz_convert(local_tz)
                    else:
                        if late_date.tzinfo is None:
                            late_date = pytz.UTC.localize(late_date)
                        late_date = late_date.astimezone(local_tz)
                    late_due_date = late_date.strftime('%Y-%m-%d %I:%M %p %Z')
                
                # Calculate time remaining
                # Convert to UTC for time calculation
                if isinstance(due_date, pd.Timestamp):
                    due_date_utc = due_date.tz_convert(pytz.UTC)
                else:
                    due_date_utc = due_date.astimezone(pytz.UTC)
                time_remaining = due_date_utc - datetime.now(pytz.UTC)
                days_remaining = time_remaining.days
                hours_remaining = time_remaining.seconds // 3600
                
                if days_remaining > 0:
                    time_str = f"{days_remaining} days, {hours_remaining} hours"
                else:
                    time_str = f"{hours_remaining} hours"
                
                assignment_dicts.append({
                    'platform': assignment.platform.value,
                    'course_name': assignment.course_name,
                    'assignment_name': assignment.assignment_name,
                    'due_date': due_date.strftime('%Y-%m-%d %I:%M %p %Z'),
                    'late_due_date': late_due_date,
                    'points_possible': assignment.points_possible,
                    'url': assignment.url,
                    'status': assignment.status,
                    'time_remaining': time_str
                })
            
            return assignment_dicts
        
        except Exception as e:
            raise ValueError(f"Error fetching assignments: {str(e)}")
