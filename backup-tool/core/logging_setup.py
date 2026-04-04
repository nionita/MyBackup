import logging
import logging.handlers
import os
from . import platform_utils

class JobLogAdapter(logging.LoggerAdapter):
    """
    Adapter to inject 'job_name' into the log output format.
    Format string is e.g.: [%(asctime)s] [%(levelname)-5s] [%(job_name)-10s] %(message)s
    """
    def process(self, msg, kwargs):
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra'].update(self.extra)
        return msg, kwargs

class JobNameFilter(logging.Filter):
    """
    Filter to ensure every log record has a 'job_name' attribute.
    Defaults to 'global' if not provided via an adapter's extra.
    """
    def filter(self, record):
        if not hasattr(record, 'job_name'):
            record.job_name = 'global'
        return True

def setup_logger(log_level: str = "INFO", log_file: str = None, 
                 max_bytes: int = 10485760, backup_count: int = 5) -> logging.Logger:
    """Sets up the root logger configuration."""
    logger = logging.getLogger("backup")
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-5s] [%(job_name)-10s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    job_filter = JobNameFilter()
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    ch.addFilter(job_filter)
    logger.addHandler(ch)
    
    # File handler
    if log_file is None:
        defaults = platform_utils.get_default_paths()
        log_file = os.path.join(defaults["log_dir"], "backup.log")
        
    try:
        log_dir = os.path.dirname(os.path.abspath(log_file))
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        fh.setLevel(level)
        fh.setFormatter(formatter)
        fh.addFilter(job_filter)
        logger.addHandler(fh)
    except Exception as e:
        # Fallback to console only if we can't write to file
        logger.error(f"Failed to setup file logging at {log_file}. Error: {e}")
        
    return logger

def get_job_logger(job_name: str) -> logging.LoggerAdapter:
    """Returns a logger adapter configured with the specific job name."""
    logger = logging.getLogger("backup")
    return JobLogAdapter(logger, {"job_name": job_name})
