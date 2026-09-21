"""File downloader module for Canvas files."""

import re
import os
import html
import hashlib
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

    def _entry(self, f: Any, source: str, source_name: str, rel_dir: str) -> Dict[str, Any]:
        """Normalize a canvasapi File or an assignment attachment dict into a listing entry."""
        get = f.get if isinstance(f, dict) else (lambda k, d=None: getattr(f, k, d))
        name = get('display_name') or get('filename') or f"file {get('id')}"
        locked = bool(get('locked_for_user')) or not get('url')
        return {
            "id": get('id'),
            "display_name": name,
            "size": get('size'),
            "content_type": get('content-type'),
            "created_at": get('created_at'),
            "updated_at": get('updated_at'),
            "modified_at": get('modified_at'),
            "source": source,
            "source_name": source_name,
            "rel_path": str(Path(rel_dir) / self.sanitize_filename(name)),
            "locked": locked,
            "lock_explanation": (get('lock_explanation') or "File is locked") if locked else None,
            "url": get('url'),
        }

    def list_course_files(self, course_id: int) -> Dict[str, Any]:
        """
        Discover every file reachable in a course without downloading anything:
        module items, assignment attachments and description links, the Files
        tab, and links in Pages and announcements. Each file appears once
        (deduped by file id), under the first section it turns up in.

        Returns course_name, files (entries with id, display_name, size, dates,
        source, rel_path, locked, url), notes, and errors (non-fatal).
        """
        course = self.canvas.get_course(course_id)
        files: List[Dict[str, Any]] = []
        notes: List[str] = []
        errors: List[Dict[str, Any]] = []
        seen: set = set()

        def add(f: Any, source: str, source_name: str, rel_dir: str) -> None:
            fid = f.get('id') if isinstance(f, dict) else getattr(f, 'id', None)
            if fid in seen:
                return
            seen.add(fid)
            files.append(self._entry(f, source, source_name, rel_dir))

        def add_by_id(file_id: int, source: str, source_name: str, rel_dir: str,
                      verifier: Optional[str] = None) -> None:
            """Look a file up by id (with its verifier if any) and add it once."""
            if file_id in seen:
                return
            try:
                kwargs = {'verifier': verifier} if verifier else {}
                add(self.canvas.get_file(file_id, **kwargs), source, source_name, rel_dir)
            except Exception as e:
                seen.add(file_id)
                errors.append({"file_id": file_id, "source": source, "source_name": source_name,
                               "message": f"Could not look up file: {str(e)}"})

        def add_links(markup: Optional[str], source: str, source_name: str, rel_dir: str) -> None:
            for file_id, verifier in self._file_links(markup).items():
                add_by_id(file_id, source, source_name, rel_dir, verifier)

        def section_error(name: str, e: Exception) -> None:
            errors.append({"file_id": None, "source": name, "source_name": None,
                           "message": f"Error processing {name}: {str(e)}"})

        # Modules
        try:
            for module in course.get_modules():
                module_dir = Path("Modules") / self.sanitize_filename(module.name)
                current_section = None
                try:
                    for item in module.get_module_items():
                        if item.type == 'SubHeader' or (item.type == 'ExternalUrl' and item.title):
                            section_num, section_name = self._extract_section_info(item.title)
                            if section_num and section_name:
                                current_section = f"{section_num} - {section_name}"
                        elif item.type == 'File':
                            rel_dir = module_dir
                            if current_section:
                                rel_dir = module_dir / self.sanitize_filename(current_section)
                            add_by_id(item.content_id, "module", module.name, str(rel_dir))
                except Exception as e:
                    section_error(f"module {module.name}", e)
        except Exception as e:
            section_error("modules", e)

        # Assignments: direct attachments and files linked from the description
        try:
            for assignment in course.get_assignments():
                rel_dir = str(Path("Assignments") / self.sanitize_filename(assignment.name))
                for attachment in getattr(assignment, 'attachments', None) or []:
                    add(attachment, "assignment", assignment.name, rel_dir)
                add_links(getattr(assignment, 'description', None), "assignment", assignment.name, rel_dir)
        except Exception as e:
            section_error("assignments", e)

        # Files tab (often disabled for students)
        try:
            for f in course.get_files():
                add(f, "files_tab", "Files", "Files")
        except Exception as e:
            if 'unauthorized' in str(e).lower():
                notes.append("Files tab is disabled for students in this course; "
                             "listed linked files instead.")
            else:
                section_error("course files", e)

        # Pages
        try:
            for page in course.get_pages():
                body = getattr(course.get_page(page.url), 'body', None)
                add_links(body, "page", page.title,
                          str(Path("Pages") / self.sanitize_filename(page.title)))
        except Exception as e:
            if 'not found' in str(e).lower() or 'unauthorized' in str(e).lower():
                notes.append("Pages are not available in this course.")
            else:
                section_error("pages", e)

        # Announcements (all of them, not just the recent ones)
        try:
            start = getattr(course, 'start_at', None) or '2000-01-01'
            end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')
            for topic in self.canvas.get_announcements(
                    context_codes=[f"course_{course.id}"], start_date=start[:10], end_date=end):
                add_links(getattr(topic, 'message', None), "announcement", topic.title,
                          str(Path("Announcements") / self.sanitize_filename(topic.title)))
        except Exception as e:
            section_error("announcements", e)

        return {"course_id": course.id, "course_name": course.name,
                "files": files, "notes": notes, "errors": errors}

    def download_all_course_files(self, course_id: int, download_path: Optional[str] = None,
                                  file_ids: Optional[List[int]] = None,
                                  since: Optional[datetime] = None,
                                  flat: bool = False) -> Dict[str, Any]:
        """
        Download a course's files, as discovered by list_course_files.

        download_path is the root for this run only; it does not change the
        saved default. file_ids / since restrict the run to those files. With
        flat=True files go straight into the root instead of
        <root>/<course>/<section>/.
        """
        try:
            listing = self.list_course_files(course_id)
            root = Path(download_path or get_download_path()).expanduser()
            base_path = root if flat else root / self.sanitize_filename(listing["course_name"])
            base_path.mkdir(parents=True, exist_ok=True)

            entries = filter_since(listing["files"], since)
            files: List[Dict[str, Any]] = []
            stats = {"total": 0, "successful": 0, "failed": 0, "skipped": 0, "locked": 0}

            def record(info: Dict[str, Any]) -> None:
                files.append(info)
                stats["total"] += 1
                key = {"success": "successful", "skipped": "skipped",
                       "locked": "locked"}.get(info["status"], "failed")
                stats[key] += 1

            if file_ids is not None:
                wanted = set(file_ids)
                entries = [e for e in entries if e["id"] in wanted]
                for missing in sorted(wanted - {e["id"] for e in entries}):
                    record({"status": "error", "filename": f"file {missing}", "path": str(base_path),
                            "message": "Not found among this course's files"
                                       + (" (or older than --since)" if since else "")})
            else:
                # Files that could not even be looked up count as failures of a full run
                for err in listing["errors"]:
                    if err["file_id"] is not None:
                        record({"status": "error", "filename": f"file {err['file_id']}",
                                "path": str(base_path), "message": err["message"]})
                    else:
                        files.append({"status": "error", "filename": err["source"],
                                      "path": str(base_path), "message": err["message"]})

            for e in entries:
                dest = base_path if flat else base_path / Path(e["rel_path"]).parent
                if e["locked"]:
                    record({"status": "locked", "filename": e["display_name"], "path": str(dest),
                            "message": e["lock_explanation"]})
                else:
                    record(self.download_file(e["url"], dest, e["display_name"]))

            return {
                "course_name": listing["course_name"],
                "base_path": str(base_path),
                "files": files,
                "notes": listing["notes"],
                "stats": stats,
            }

        except Exception as e:
            raise ValueError(f"Error downloading course files: {str(e)}")

    def remote_sha256(self, url: str) -> str:
        """Hash a Canvas file's content by streaming it, without saving it."""
        headers = {}
        if urlparse(url).hostname == self.domain:
            headers['Authorization'] = f'Bearer {self.token}'
        digest = hashlib.sha256()
        with requests.get(url, stream=True, headers=headers) as response:
            response.raise_for_status()
            for chunk in response.iter_content(65536):
                digest.update(chunk)
        return digest.hexdigest()


def _timestamp(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except ValueError:
        return None


def filter_since(entries: List[Dict[str, Any]], since: Optional[datetime]) -> List[Dict[str, Any]]:
    """Entries created or updated at/after `since` (entries with no dates are kept)."""
    if since is None:
        return entries
    kept = []
    for e in entries:
        stamps = [t for t in (_timestamp(e.get(k)) for k in ("created_at", "updated_at", "modified_at")) if t]
        if not stamps or max(stamps) >= since:
            kept.append(e)
    return kept


def _local_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def compare_with_local(entries: List[Dict[str, Any]], local_dir: str,
                       downloader: CanvasDownloader) -> None:
    """
    Mark each entry with `local`: {"status", "path"} by looking for it anywhere
    under local_dir, independent of folder layout or renames. Read-only.

    have     same size and same name, or same size and identical content (sha256)
    changed  a file with the same name exists but its size differs
    missing  nothing matches
    """
    root = Path(local_dir).expanduser()
    if not root.is_dir():
        raise ValueError(f"'{local_dir}' is not a directory.")

    by_size: Dict[int, List[Path]] = {}
    by_name: Dict[str, List[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fn in filenames:
            if fn.startswith('.'):
                continue
            p = Path(dirpath) / fn
            try:
                by_size.setdefault(p.stat().st_size, []).append(p)
            except OSError:
                continue
            by_name.setdefault(fn.casefold(), []).append(p)

    local_hashes: Dict[Path, str] = {}

    def local_hash(p: Path) -> str:
        if p not in local_hashes:
            local_hashes[p] = _local_sha256(p)
        return local_hashes[p]

    for e in entries:
        names = {e["display_name"].casefold(), Path(e["rel_path"]).name.casefold()}
        same_size = by_size.get(e["size"], []) if e["size"] is not None else []
        match = next((p for p in same_size if p.name.casefold() in names), None)

        if match is None and same_size and not e["locked"]:
            try:
                remote = downloader.remote_sha256(e["url"])
                match = next((p for p in same_size if local_hash(p) == remote), None)
            except Exception:
                match = None

        if match is not None:
            e["local"] = {"status": "have", "path": str(match)}
            continue

        named = [p for n in names for p in by_name.get(n, [])]
        if named:
            e["local"] = {"status": "changed", "path": str(named[0])}
        else:
            e["local"] = {"status": "missing", "path": None}
