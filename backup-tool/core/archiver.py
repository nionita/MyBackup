import os
import tarfile
import zipfile
import tempfile
import fnmatch
from datetime import datetime, timezone
from core import logging_setup

class ArchiveError(Exception):
    pass

def should_exclude(rel_path, exclude_patterns):
    """
    Evaluates if a path should be excluded based on fnmatch glob patterns.
    It checks the relative path, the basename, and the constituent directories.
    """
    if not exclude_patterns:
        return False
        
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        # Check intermediate directories
        parts = rel_path.replace('\\', '/').split('/')
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False

def create_archive(job_name: str, sources: list[str], archive_format: str, 
                   compression_level: int = 6, temp_dir: str = None,
                   exclude_patterns: list[str] = None) -> str:
    """Creates a compressed archive for the given sources."""
    if exclude_patterns is None:
        exclude_patterns = []
        
    logger = logging_setup.get_job_logger(job_name)
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%dT%H%M%SZ")
    
    if archive_format not in ["tar.gz", "zip"]:
        raise ArchiveError(f"Unsupported archive format: {archive_format}")
        
    ext = ".tar.gz" if archive_format == "tar.gz" else ".zip"
    filename = f"{job_name}_{timestamp_str}{ext}"
    
    out_dir = temp_dir if temp_dir else tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    
    logger.info(f"Creating archive {filename} (Format: {archive_format})...")
    
    total_size = 0
    file_count = 0

    try:
        if archive_format == "tar.gz":
            with tarfile.open(out_path, "w:gz", compresslevel=compression_level) as tar:
                for source in sources:
                    if not os.path.exists(source):
                        continue
                    
                    if os.path.isfile(source):
                        rel_in_source = os.path.basename(source)
                        if should_exclude(rel_in_source, exclude_patterns):
                            continue
                        arcname = os.path.splitdrive(source)[1].lstrip(os.path.sep)
                        tar.add(source, arcname=arcname)
                        file_count += 1
                        total_size += os.path.getsize(source)
                    else:
                        for root_dir, dirs, files in os.walk(source):
                            dirs[:] = [d for d in dirs if not should_exclude(os.path.relpath(os.path.join(root_dir, d), source), exclude_patterns)]
                            
                            for file in files:
                                file_path = os.path.join(root_dir, file)
                                rel_path = os.path.relpath(file_path, source)
                                if should_exclude(rel_path, exclude_patterns):
                                    continue
                                
                                arcname = os.path.splitdrive(file_path)[1].lstrip(os.path.sep)
                                tar.add(file_path, arcname=arcname)
                                file_count += 1
                                total_size += os.path.getsize(file_path)
                                
        elif archive_format == "zip":
            # Note: ZIP_DEFLATED level 1-9 is supported since Py 3.7
            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zf:
                for source in sources:
                    if not os.path.exists(source):
                        continue
                        
                    if os.path.isfile(source):
                        rel_in_source = os.path.basename(source)
                        if should_exclude(rel_in_source, exclude_patterns):
                            continue
                        arcname = os.path.splitdrive(source)[1].lstrip(os.path.sep)
                        zf.write(source, arcname=arcname)
                        file_count += 1
                        total_size += os.path.getsize(source)
                    else:
                        for root_dir, dirs, files in os.walk(source):
                            dirs[:] = [d for d in dirs if not should_exclude(os.path.relpath(os.path.join(root_dir, d), source), exclude_patterns)]
                            
                            for file in files:
                                file_path = os.path.join(root_dir, file)
                                rel_path = os.path.relpath(file_path, source)
                                if should_exclude(rel_path, exclude_patterns):
                                    continue
                                
                                arcname = os.path.splitdrive(file_path)[1].lstrip(os.path.sep)
                                zf.write(file_path, arcname=arcname)
                                file_count += 1
                                total_size += os.path.getsize(file_path)
                                
        out_size_mb = os.path.getsize(out_path) / (1024 * 1024)
        logger.info(f"Archive created: {filename} ({out_size_mb:.2f} MB, {file_count} files, original size: {total_size / (1024*1024):.2f} MB)")
        return out_path
        
    except Exception as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise ArchiveError(f"Failed to create archive: {e}")
