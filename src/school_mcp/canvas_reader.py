"""Read-only Canvas lookups: courses, announcements, inbox and grades."""

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from canvasapi import Canvas
from .config import get_config


def make_canvas(config: Dict[str, Optional[str]]) -> Canvas:
    """Build a Canvas client from an account config."""
    domain = config['canvas_domain'].replace('https://', '').replace('http://', '')
    return Canvas(f'https://{domain}', config['canvas_access_token'])


def html_to_text(markup: Optional[str]) -> str:
    """Rough HTML to plain text: keeps paragraph and list breaks, drops tags."""
    if not markup:
        return ""
    text = re.sub(r'(?is)<(script|style).*?</\1>', '', markup)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)<li[^>]*>', '\n- ', text)
    text = re.sub(r'(?i)</(p|div|h\d|li|tr|ul|ol)>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()


def _course_code(course) -> str:
    return getattr(course, 'course_code', None) or getattr(course, 'name', str(course.id))


class CanvasReader:
    """Read-only access to one account's Canvas data."""

    def __init__(self, account: Optional[str] = None):
        config = get_config(account)
        self.account = config['account']
        self.canvas = make_canvas(config)
        self._courses = None

    # ---------- courses ----------

    def courses(self) -> List[Any]:
        """Active student courses (cached per instance)."""
        if self._courses is None:
            self._courses = list(self.canvas.get_courses(
                enrollment_type='student',
                enrollment_state='active',
                include=['total_scores'],
            ))
        return self._courses

    def resolve_course(self, query: str) -> Any:
        """
        Find one active course by Canvas id, course code (e.g. "20.201") or a
        case-insensitive piece of its name (e.g. "crispr").
        """
        courses = self.courses()
        q = str(query).strip().lower()

        if q.isdigit():
            for c in courses:
                if c.id == int(q):
                    return c

        exact = [c for c in courses if _course_code(c).lower() == q]
        if len(exact) == 1:
            return exact[0]

        partial = [c for c in courses
                   if q in _course_code(c).lower() or q in getattr(c, 'name', '').lower()]
        if len(partial) == 1:
            return partial[0]

        listing = ', '.join(f"{_course_code(c)} ({c.id})" for c in courses)
        if not partial:
            raise ValueError(f"No active course matches '{query}'. Courses: {listing}")
        matches = ', '.join(f"{_course_code(c)} ({c.id})" for c in partial)
        raise ValueError(f"'{query}' matches several courses: {matches}")

    def course_list(self) -> List[Dict[str, Any]]:
        return [{'id': c.id, 'code': _course_code(c), 'name': c.name} for c in self.courses()]

    # ---------- announcements ----------

    def announcements(self, course: Optional[str] = None, days: int = 14,
                      unread_only: bool = False) -> List[Dict[str, Any]]:
        """Announcements posted in the last `days` days, newest first."""
        courses = [self.resolve_course(course)] if course else self.courses()
        if not courses:
            return []
        code_by_context = {f"course_{c.id}": _course_code(c) for c in courses}

        now = datetime.now(timezone.utc)
        topics = self.canvas.get_announcements(
            context_codes=list(code_by_context),
            start_date=(now - timedelta(days=days)).strftime('%Y-%m-%d'),
            end_date=(now + timedelta(days=1)).strftime('%Y-%m-%d'),
        )

        result = []
        for t in topics:
            read_state = getattr(t, 'read_state', None)
            if unread_only and read_state != 'unread':
                continue
            author = getattr(t, 'author', None) or {}
            result.append({
                'id': t.id,
                'course': code_by_context.get(getattr(t, 'context_code', ''), ''),
                'title': t.title,
                'author': author.get('display_name'),
                'posted_at': getattr(t, 'posted_at', None),
                'read_state': read_state,
                'url': getattr(t, 'html_url', None),
                'message': html_to_text(getattr(t, 'message', '')),
            })
        result.sort(key=lambda a: a['posted_at'] or '', reverse=True)
        return result

    # ---------- inbox ----------

    def inbox(self, scope: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Conversation list, newest first. `scope` is one of Canvas's inbox scopes:
        None (inbox), "unread", "starred", "sent", "archived".
        """
        kwargs = {'scope': scope} if scope else {}
        result = []
        for conv in self.canvas.get_conversations(**kwargs):
            participants = [p.get('name') for p in getattr(conv, 'participants', []) or []]
            result.append({
                'id': conv.id,
                'subject': conv.subject,
                'course': getattr(conv, 'context_name', None),
                'participants': participants,
                'last_message_at': getattr(conv, 'last_message_at', None),
                'message_count': getattr(conv, 'message_count', None),
                'state': conv.workflow_state,
                'preview': getattr(conv, 'last_message', None),
            })
            if len(result) >= limit:
                break
        return result

    def message(self, conversation_id: int, mark_read: bool = False) -> Dict[str, Any]:
        """A full conversation thread, oldest message first. Leaves it unread unless asked."""
        conv = self.canvas.get_conversation(
            conversation_id, auto_mark_as_read=mark_read
        )
        names = {p['id']: p.get('name') for p in getattr(conv, 'participants', []) or []}
        messages = []
        for m in reversed(getattr(conv, 'messages', []) or []):
            messages.append({
                'author': names.get(m.get('author_id'), m.get('author_id')),
                'created_at': m.get('created_at'),
                'body': m.get('body', ''),
                'attachments': [
                    {'filename': a.get('display_name') or a.get('filename'), 'url': a.get('url')}
                    for a in m.get('attachments', []) or []
                ],
            })
        return {
            'id': conv.id,
            'subject': conv.subject,
            'course': getattr(conv, 'context_name', None),
            'participants': list(names.values()),
            'state': conv.workflow_state,
            'messages': messages,
        }

    # ---------- grades ----------

    def grade_summary(self) -> List[Dict[str, Any]]:
        """Current overall score per active course (None when the course hides it)."""
        result = []
        for c in self.courses():
            enrollment = next(
                (e for e in getattr(c, 'enrollments', []) or [] if e.get('type') == 'student'),
                {},
            )
            result.append({
                'id': c.id,
                'code': _course_code(c),
                'current_score': enrollment.get('computed_current_score'),
                'current_grade': enrollment.get('computed_current_grade'),
            })
        return result

    def course_grades(self, course: str) -> Dict[str, Any]:
        """Per-assignment scores for one course, in due-date order."""
        c = self.resolve_course(course)
        rows = []
        for a in c.get_assignments(include=['submission'], order_by='due_at'):
            if not getattr(a, 'published', True):
                continue
            sub = getattr(a, 'submission', None) or {}
            rows.append({
                'assignment': a.name,
                'due_at': getattr(a, 'due_at', None),
                'score': sub.get('score'),
                'points_possible': getattr(a, 'points_possible', None),
                'grade': sub.get('grade'),
                'state': sub.get('workflow_state'),
                'late': sub.get('late'),
                'missing': sub.get('missing'),
                'url': getattr(a, 'html_url', None),
            })
        return {'id': c.id, 'code': _course_code(c), 'name': c.name, 'assignments': rows}
