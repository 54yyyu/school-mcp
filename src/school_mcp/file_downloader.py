"""File downloader module for Canvas files."""

import re
import os
import mimetypes
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional
import requests
from canvasapi import Canvas
from .config import get_config, get_download_path, save_download_path

class CanvasDownloader:
    """Class for downloading files from Canvas."""
    
    def __init__(self):
        """Initialize Canvas connection."""
        try:
            config = get_config()
            domain = config['canvas_domain'].replace('https://', '').replace('http://', '')
            self.canvas = Canvas(f'https://{domain}', config['canvas_access_token'])
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
            response = requests.get(url, stream=True)
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

    def download_all_course_files(self, course_id: int, download_path: Optional[str] = None) -> Dict[str, Any]:
        """Download all files from a course."""
        try:
            course = self.canvas.get_course(course_id)
            course_name = self.sanitize_filename(course.name)
            
            if download_path:
                base_path = Path(download_path) / course_name
                save_download_path(download_path)
            else:
                base_path = Path(get_download_path()) / course_name
            
            base_path.mkdir(parents=True, exist_ok=True)
            
            # Track downloads
            total_files = 0
            successful = 0
            failed = 0
            skipped = 0
            download_results = []
            
            # Create result object
            result = {
                "course_name": course.name,
                "base_path": str(base_path),
                "files": download_results,
                "stats": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "skipped": 0
                }
            }
            
            # Download module files
            try:
                modules = course.get_modules()
                
                for module in modules:
                    module_path = base_path / "Modules" / self.sanitize_filename(module.name)
                    current_section = None
                    
                    try:
                        items = module.get_module_items()
                        for item in items:
                            # Check for section headers
                            if item.type == 'SubHeader' or (item.type == 'ExternalUrl' and item.title):
                                section_num, section_name = self._extract_section_info(item.title)
                                if section_num and section_name:
                                    current_section = f"{section_num} - {section_name}"
                            
                            # Handle files
                            elif item.type == 'File':
                                try:
                                    file = course.get_file(item.content_id)
                                    download_path = module_path
                                    if current_section:
                                        download_path = module_path / self.sanitize_filename(current_section)
                                    
                                    result_info = self.download_file(file.url, download_path, file.filename)
                                    download_results.append(result_info)
                                    
                                    total_files += 1
                                    if result_info["status"] == "success":
                                        successful += 1
                                    elif result_info["status"] == "skipped":
                                        skipped += 1
                                    else:
                                        failed += 1
                                        
                                except Exception as e:
                                    download_results.append({
                                        "status": "error",
                                        "filename": item.title,
                                        "path": str(module_path),
                                        "message": f"Error downloading file: {str(e)}"
                                    })
                                    total_files += 1
                                    failed += 1
                    except Exception as e:
                        download_results.append({
                            "status": "error",
                            "filename": f"Module {module.name}",
                            "path": str(module_path),
                            "message": f"Error processing module items: {str(e)}"
                        })
            except Exception as e:
                download_results.append({
                    "status": "error",
                    "filename": "Modules",
                    "path": str(base_path / "Modules"),
                    "message": f"Error processing modules: {str(e)}"
                })

            # Download assignment files
            try:
                assignments = course.get_assignments()
                assignment_path = base_path / "Assignments"
                
                for assignment in assignments:
                    current_path = assignment_path / self.sanitize_filename(assignment.name)
                    
                    # Download description attachments
                    if hasattr(assignment, 'description'):
                        urls = re.findall(r'href="([^"]+)"', assignment.description or '')
                        for url in urls:
                            if '/files/' in url and '/preview' not in url:
                                try:
                                    file_id = url.split('/files/')[-1].split('/')[0]
                                    file = course.get_file(file_id)
                                    result_info = self.download_file(file.url, current_path)
                                    download_results.append(result_info)
                                    
                                    total_files += 1
                                    if result_info["status"] == "success":
                                        successful += 1
                                    elif result_info["status"] == "skipped":
                                        skipped += 1
                                    else:
                                        failed += 1
                                except Exception:
                                    continue
                    
                    # Download direct attachments
                    if hasattr(assignment, 'attachments'):
                        for attachment in assignment.attachments:
                            result_info = self.download_file(attachment['url'], current_path, attachment['filename'])
                            download_results.append(result_info)
                            
                            total_files += 1
                            if result_info["status"] == "success":
                                successful += 1
                            elif result_info["status"] == "skipped":
                                skipped += 1
                            else:
                                failed += 1
            except Exception as e:
                download_results.append({
                    "status": "error",
                    "filename": "Assignments",
                    "path": str(assignment_path),
                    "message": f"Error processing assignments: {str(e)}"
                })

            # Download course files
            try:
                files = course.get_files()
                files_path = base_path / "Files"
                
                for file in files:
                    result_info = self.download_file(file.url, files_path, file.filename)
                    download_results.append(result_info)
                    
                    total_files += 1
                    if result_info["status"] == "success":
                        successful += 1
                    elif result_info["status"] == "skipped":
                        skipped += 1
                    else:
                        failed += 1
            except Exception as e:
                download_results.append({
                    "status": "error",
                    "filename": "Files",
                    "path": str(base_path / "Files"),
                    "message": f"Error processing course files: {str(e)}"
                })
            
            # Update stats
            result["stats"]["total"] = total_files
            result["stats"]["successful"] = successful
            result["stats"]["failed"] = failed
            result["stats"]["skipped"] = skipped
            
            return result
            
        except Exception as e:
            raise ValueError(f"Error downloading course files: {str(e)}")
