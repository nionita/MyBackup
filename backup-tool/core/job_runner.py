import os
import time
from core import logging_setup, archiver, retention
from backends import BACKEND_REGISTRY

def instantiate_backend(job_config, backend_config):
    b_type = backend_config.get("backend_type")
    if b_type not in BACKEND_REGISTRY:
        raise ValueError(f"Unknown backend type: {b_type}")
        
    class_path = BACKEND_REGISTRY[b_type]
    module_name, class_name = class_path.rsplit(".", 1)
    
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return cls(job_config, backend_config)

def run_job(job_config: dict) -> bool:
    job_name = job_config["name"]
    logger = logging_setup.get_job_logger(job_name)
    logger.info("Backup started")
    
    start_time = time.time()
    sources = [s for s in job_config.get("sources", []) if os.path.exists(s)]
    
    if not sources:
        logger.error("No valid sources found to backup.")
        return False
        
    archive_format = job_config.get("archive", {}).get("format", "none")
    comp_level = job_config.get("archive", {}).get("compression_level", 6)
    exclude_patterns = job_config.get("exclude_patterns", [])
    
    archive_path = None
    
    try:
        if archive_format != "none":
            archive_path = archiver.create_archive(
                job_name=job_name,
                sources=sources,
                archive_format=archive_format,
                compression_level=comp_level,
                exclude_patterns=exclude_patterns
            )
            target_key = f"{job_name}/{os.path.basename(archive_path)}"
        else:
            logger.error("Format 'none' (flat upload) is not fully implemented yet.")
            return False
            
        success = True
        
        for b_conf in job_config.get("backends", []):
            b_type = b_conf.get("backend_type")
            if b_type == "google_drive":
                logger.warning(f"[{b_type}] Google Drive backend is postponed. Skipping.")
                continue
                
            try:
                backend = instantiate_backend(job_config, b_conf)
                
                # Auth
                backend.authenticate()
                
                # Upload
                logger.info(f"[{b_type}] Upload started: {os.path.basename(archive_path)}")
                b_start = time.time()
                backend.upload(archive_path, target_key)
                b_duration = time.time() - b_start
                b_size_mb = os.path.getsize(archive_path) / (1024 * 1024)
                throughput = b_size_mb / b_duration if b_duration > 0 else 0
                logger.info(f"[{b_type}] Upload completed ({b_duration:.1f}s, {throughput:.1f} MB/s)")
                
                # Retention
                retention_count = b_conf.get("retention_count", 5)
                retention.run_retention(backend, logger, job_name, retention_count)
                
            except Exception as e:
                logger.error(f"[{b_type}] Backend operation failed: {e}")
                success = False

    except Exception as e:
        logger.error(f"Job failed during archiving: {e}")
        success = False
    finally:
        if archive_path and os.path.exists(archive_path):
            os.remove(archive_path)
            
    total_duration = time.time() - start_time
    logger.info(f"Backup completed (Duration: {total_duration:.1f}s)")
    return success

def run_retention_only(job_config: dict):
    job_name = job_config["name"]
    logger = logging_setup.get_job_logger(job_name)
    logger.info("Retention cleanup started")
    
    for b_conf in job_config.get("backends", []):
        b_type = b_conf.get("backend_type")
        if b_type == "google_drive":
            logger.warning(f"[{b_type}] Google Drive backend is postponed. Skipping.")
            continue
            
        try:
            backend = instantiate_backend(job_config, b_conf)
            backend.authenticate()
            retention_count = b_conf.get("retention_count", 5)
            retention.run_retention(backend, logger, job_name, retention_count)
        except Exception as e:
            logger.error(f"[{b_type}] Retention cleanup failed: {e}")
