import json
import os
import re
from core import platform_utils

class ConfigError(Exception):
    pass

def resolve_env_vars(data):
    """Recursively traverses a python structure and resolves $ENV: references."""
    if isinstance(data, dict):
        for k, v in data.items():
            data[k] = resolve_env_vars(v)
        return data
    elif isinstance(data, list):
        return [resolve_env_vars(i) for i in data]
    elif isinstance(data, str) and data.startswith("$ENV:"):
        env_var = data[5:]
        val = os.environ.get(env_var)
        if val is None:
            raise ConfigError(f"Environment variable '{env_var}' referenced in config but not set.")
        return val
    else:
        return data

def load_global_config(config_dir="config"):
    """Loads the global configuration, returning defaults if not found."""
    global_file = os.path.join(config_dir, "global.json")
    if not os.path.exists(global_file):
        return {
            "version": "1.0",
            "log_level": "INFO",
            "log_file": os.path.join(platform_utils.get_default_paths()["log_dir"], "backup.log"),
            "log_max_bytes": 10485760,
            "log_backup_count": 5,
            "temp_dir": None
        }
    
    with open(global_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in {global_file}: {e}")
            
    return resolve_env_vars(data)

def validate_job_config(job_name, data):
    """Validates the job configuration dict according to the specified rules."""
    if not re.match(r"^[a-zA-Z0-9_]+$", job_name):
        raise ConfigError(f"Job name '{job_name}' contains invalid characters.")

    if "name" not in data or data["name"] != job_name:
        raise ConfigError(f"Job config missing 'name' or does not match filename '{job_name}'")
        
    if "sources" not in data or not isinstance(data["sources"], list) or len(data["sources"]) == 0:
        raise ConfigError(f"Job '{job_name}' must have at least one source.")
        
    for source in data["sources"]:
        if not os.path.exists(source):
            import logging
            try:
                logging.getLogger("backup").warning(f"Source path does not exist: {source} in job {job_name}")
            except Exception:
                pass

    if not any(os.path.exists(s) for s in data["sources"]):
        raise ConfigError(f"None of the sources for job '{job_name}' exist.")
        
    if "backends" not in data or not isinstance(data["backends"], list) or len(data["backends"]) == 0:
        raise ConfigError(f"Job '{job_name}' must have at least one backend.")
        
    for backend in data["backends"]:
        if "backend_type" not in backend:
            raise ConfigError(f"Backend in job '{job_name}' missing backend_type.")
        if "retention_count" not in backend or not isinstance(backend["retention_count"], int) or backend["retention_count"] < 1:
            raise ConfigError(f"Backend {backend.get('backend_type')} in job '{job_name}' has missing or invalid retention_count.")
            
    if "archive" not in data:
        data["archive"] = {}
        
    if "format" not in data["archive"]:
        data["archive"]["format"] = "zip" if platform_utils.is_windows() else "tar.gz"
        
    if data["archive"]["format"] not in ["zip", "tar.gz", "none"]:
        raise ConfigError(f"Invalid archive format in job '{job_name}': {data['archive']['format']}")
        
    if "compression_level" not in data["archive"]:
        data["archive"]["compression_level"] = 6
    else:
        lvl = data["archive"]["compression_level"]
        if not isinstance(lvl, int) or lvl < 1 or lvl > 9:
            raise ConfigError(f"Invalid compression level {lvl} in job '{job_name}'.")
        
    return data

def load_job_configs(config_dir="config"):
    """Loads all jobs from config_dir/jobs directory."""
    jobs = []
    jobs_dir = os.path.join(config_dir, "jobs")
    if not os.path.exists(jobs_dir):
        return jobs
        
    def check_permissions(path):
        if platform_utils.is_linux():
            try:
                st = os.stat(path)
                import stat
                if stat.S_IROTH & st.st_mode:
                    import logging
                    logging.getLogger("backup").warning(f"Path {path} is world-readable! Consider chmod 600.")
            except Exception:
                pass
                
    check_permissions(jobs_dir)
            
    for filename in os.listdir(jobs_dir):
        if filename.startswith("job_") and filename.endswith(".json"):
            job_name = filename[4:-5]
            filepath = os.path.join(jobs_dir, filename)
            check_permissions(filepath)
                    
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    raise ConfigError(f"Invalid JSON in {filepath}: {e}")
                    
            if data.get("enabled", True) is False:
                continue
                
            data = resolve_env_vars(data)
            data = validate_job_config(job_name, data)
            jobs.append(data)
            
    return jobs
