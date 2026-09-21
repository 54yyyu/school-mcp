"""File downloader module for Canvas files."""

import re
import os
import html
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional
from urllib.parse import urlparse, parse_qs
import requests
from canvasapi import Canvas
from .config import get_config, get_download_path

# Canvas file links inside HTML, e.g. /courses/40243/files/6852894?verifier=...&wrap=1
# or the API form /api/v1/courses/40243/files/6852894. Group 1 is the file id,
# group 2 the optional query string.
FILE_LINK_RE = re.compile(r'/files/(\d+)(?:/[\w-]*)?(\?[^"\'\s<>]*)?')

class CanvasDownloader:
    """Class for downloading files from Canvas."""
    
    def __init__(self, account: Optional[str] = None):
        """
        Initialize Canvas connection.

        Args:
            account: Name of the configured account to use (defaults to the active one)
        """
        try:
            config = get_config(account)
            self.account = config['account']
            self.domain = config['canvas_domain'].replace('https://', '').replace('http://', '')
            self.token = config['canvas_access_token']
            self.canvas = Canvas(f'https://{self.domain}', self.token)
        except Exception as e:
            raise ValueError(f"Error initializing CanvasDownloader: {str(e)}")

    def get_current_courses(self) -> List[Dict[str, Any]]:
        """Get all active courses."""
        try:
            courses = list(self.canvas.get_courses(
                enrollment_type='student',
                enrollment_state='active'
            ))
            
            courses_list = []
            for course in courses:
                courses_list.append({
                    'id': course.id,
                    'name': course.name
                })
            
            return courses_list
        except Exception as e:
            raise ValueError(f"Error fetching courses: {str(e)}")

    def _extract_section_info(self, title: str) -> tuple:
        """
        Extract section number and name from titles like "04 - Diffusion at Cellular and Molecular Scales"
        Returns tuple of (section_num, section_name) or (None, None) if no pattern found
        """
        patterns = [
            r'^(\d{1,2})\s*-\s*(.+)',  # "04 - Title"
            r'^(\d{1,2})\.\s*(.+)',     # "04. Title"
            r'^(\d{1,2})\s+(.+)'        # "04 Title"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title)
            if match:
                section_num = match.group(1).zfill(2)  # Pad with leading zero if needed
                section_name = match.group(2).strip()
                return section_num, section_name
        
        return None, None

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to be valid across operating systems."""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove control characters
        filename = "".join(char for char in filename if ord(char) >= 32)
        return filename.strip()

    def download_file(self, url: str, filepath: Path, filename: str = None) -> Dict[str, Any]:
        """Download a file and return status information."""
        try:
            # Canvas-hosted URLs need the token; requests drops it on redirects
            # to other hosts (e.g. the file store), so it never leaks.
            headers = {}
            if urlparse(url).hostname == self.domain:
                headers['Authorization'] = f'Bearer {self.token}'
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status()
            
            if not filename:
                if "Content-Disposition" in response.headers:
                    cd = response.headers["Content-Disposition"]
                    filename = re.findall("filename=(.+)", cd)[0].strip('"')
                else:
                    filename = url.split('/')[-1].split('?')[0]
            
            filename = self.sanitize_filename(filename)
            
            # Ensure file extension exists
            if '.' not in filename:
                content_type = response.headers.get('content-type')
                if content_type:
                    ext = mimetypes.guess_extension(content_type)
                    if ext:
                        filename += ext

            full_path = filepath / filename
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Skip if file exists with same size
            if full_path.exists() and full_path.stat().st_size == int(response.headers.get('content-length', 0)):
                return {
                    "status": "skipped",
                    "filename": filename,
                    "path": str(full_path),
                    "size": full_path.stat().st_size,
                    "message": "File already exists with same size"
                }
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(full_path, 'wb') as f:
                for data in response.iter_content(1024):
                    f.write(data)
            
            return {
                "status": "success",
                "filename": filename,
                "path": str(full_path),
                "size": full_path.stat().st_size,
                "message": "File downloaded successfully"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "filename": filename if filename else "unknown",
                "path": str(filepath),
                "message": f"Error downloading file: {str(e)}"
            }

    def _file_links(self, markup: Optional[str]) -> Dict[int, Optional[str]]:
        """
        Canvas file ids linked from an HTML body, mapped to their `verifier`
        (None when a link has none). A verifier lets a student fetch the file
        even when the course's Files tab is disabled.
        """
        links: Dict[int, Optional[str]] = {}
        for file_id, query in FILE_LINK_RE.findall(html.unescape(markup or '')):
            verifier = parse_qs(query.lstrip('?')).get('verifier', [None])[0] if query else None
            fid = int(file_id)
            if links.get(fid) is None:
                links[fid] = verifier
        return links

    def download_all_course_files(self, course_id: int, download_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Download every file reachable in a course: module items, assignment
        attachments and links in assignment descriptions, the Files tab, and
        links in Pages and announcements. Each file is fetched once (deduped by
        file id), under the first section it turns up in.

        download_path is the root for this run only; it does not change the
        saved default (see config.save_download_path).
        """
        try:
            course = self.canvas.get_course(course_id)
            course_name = self.sanitize_filename(course.name)
            base_path = Path(download_path or get_download_path()).expanduser() / course_name
            base_path.mkdir(parents=True, exist_ok=True)

            files: List[Dict[str, Any]] = []
            notes: List[str] = []
            stats = {"total": 0, "successful": 0, "failed": 0, "skipped": 0, "locked": 0}
            seen: set = set()

            def record(info: Dict[str, Any]) -> None:
                files.append(info)
                stats["total"] += 1
                key = {"success": "successful", "skipped": "skipped",
                       "locked": "locked"}.get(info["status"], "failed")
                stats[key] += 1

            def section_error(name: str, path: Path, e: Exception) -> None:
                files.append({"status": "error", "filename": name, "path": str(path),
                              "message": f"Error processing {name}: {str(e)}"})

            def fetch_by_id(file_id: int, dest: Path, verifier: Optional[str] = None,
                            label: str = '') -> None:
                """Look a file up by id (with its verifier if any) and download it once."""
                if file_id in seen:
                    return
                seen.add(file_id)
                try:
                    kwargs = {'verifier': verifier} if verifier else {}
                    f = self.canvas.get_file(file_id, **kwargs)
                    name = getattr(f, 'display_name', None) or f.filename
                    if getattr(f, 'locked_for_user', False) or not getattr(f, 'url', None):
                        record({"status": "locked", "filename": name, "path": str(dest),
                                "message": getattr(f, 'lock_explanation', None) or "File is locked"})
                        return
                    record(self.download_file(f.url, dest, name))
                except Exception as e:
                    record({"status": "error", "filename": label or f"file {file_id}",
                            "path": str(dest), "message": f"Error downloading file: {str(e)}"})

            def fetch_links(markup: Optional[str], dest: Path) -> None:
                for file_id, verifier in self._file_links(markup).items():
                    fetch_by_id(file_id, dest, verifier)

            # Modules
            try:
                for module in course.get_modules():
                    module_path = base_path / "Modules" / self.sanitize_filename(module.name)
                    current_section = None
                    try:
                        for item in module.get_module_items():
                            if item.type == 'SubHeader' or (item.type == 'ExternalUrl' and item.title):
                                section_num, section_name = self._extract_section_info(item.title)
                                if section_num and section_name:
                                    current_section = f"{section_num} - {section_name}"
                            elif item.type == 'File':
                                dest = module_path
                                if current_section:
                                    dest = module_path / self.sanitize_filename(current_section)
                                fetch_by_id(item.content_id, dest, label=item.title)
                    except Exception as e:
                        section_error(f"module {module.name}", module_path, e)
            except Exception as e:
                section_error("modules", base_path / "Modules", e)

            # Assignments: direct attachments and files linked from the description
            assignment_path = base_path / "Assignments"
            try:
                for assignment in course.get_assignments():
                    dest = assignment_path / self.sanitize_filename(assignment.name)
                    for attachment in getattr(assignment, 'attachments', None) or []:
                        if attachment.get('id') in seen:
                            continue
                        seen.add(attachment.get('id'))
                        record(self.download_file(attachment['url'], dest,
                                                  attachment.get('display_name') or attachment['filename']))
                    fetch_links(getattr(assignment, 'description', None), dest)
            except Exception as e:
                section_error("assignments", assignment_path, e)

            # Files tab (often disabled for students)
            files_path = base_path / "Files"
            try:
                for f in course.get_files():
                    if f.id in seen:
                        continue
                    seen.add(f.id)
                    record(self.download_file(f.url, files_path, getattr(f, 'display_name', None) or f.filename))
            except Exception as e:
                if 'unauthorized' in str(e).lower():
                    notes.append("Files tab is disabled for students in this course; "
                                 "fetched linked files instead.")
                else:
                    section_error("course files", files_path, e)

            # Pages
            pages_path = base_path / "Pages"
            try:
                for page in course.get_pages():
                    body = getattr(course.get_page(page.url), 'body', None)
                    fetch_links(body, pages_path / self.sanitize_filename(page.title))
            except Exception as e:
                if 'not found' in str(e).lower() or 'unauthorized' in str(e).lower():
                    notes.append("Pages are not available in this course.")
                else:
                    section_error("pages", pages_path, e)

            # Announcements (all of them, not just the recent ones)
            ann_path = base_path / "Announcements"
            try:
                start = getattr(course, 'start_at', None) or '2000-01-01'
                end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')
                for topic in self.canvas.get_announcements(
                        context_codes=[f"course_{course.id}"], start_date=start[:10], end_date=end):
                    fetch_links(getattr(topic, 'message', None),
                                ann_path / self.sanitize_filename(topic.title))
            except Exception as e:
                section_error("announcements", ann_path, e)

            return {
                "course_name": course.name,
                "base_path": str(base_path),
                "files": files,
                "notes": notes,
                "stats": stats,
            }

        except Exception as e:
            raise ValueError(f"Error downloading course files: {str(e)}")
