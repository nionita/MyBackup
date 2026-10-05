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
    if not isinstance(data, dict):
        raise ConfigError(f"Job '{job_name}' must be a JSON object.")
    archive = data.get("archive", {})
    if not isinstance(archive, dict):
        raise ConfigError(f"Invalid archive configuration in job '{job_name}'.")
    preserve_links = archive.get("preserve_directory_symlinks", False)
    if not isinstance(preserve_links, bool):
        raise ConfigError(f"Invalid archive.preserve_directory_symlinks in job '{job_name}'.")

    if not re.match(r"^[a-zA-Z0-9_]+$", job_name):
        raise ConfigError(f"Job name '{job_name}' contains invalid characters.")

    if "name" not in data or data["name"] != job_name:
        raise ConfigError(f"Job config missing 'name' or does not match filename '{job_name}'")
        
    if "sources" not in data or not isinstance(data["sources"], list) or len(data["sources"]) == 0:
        raise ConfigError(f"Job '{job_name}' must have at least one source.")
        
    for source in data["sources"]:
        if not (os.path.exists(source) or (preserve_links and os.path.islink(os.path.normpath(source)))):
            import logging
            try:
                logging.getLogger("backup").warning(f"Source path does not exist: {source} in job {job_name}")
            except Exception:
                pass

    if not any(os.path.exists(s) or (preserve_links and os.path.islink(os.path.normpath(s))) for s in data["sources"]):
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
    if preserve_links and data["archive"]["format"] != "tar.gz":
        raise ConfigError(f"Job '{job_name}': archive.preserve_directory_symlinks requires tar.gz.")
    data["archive"]["preserve_directory_symlinks"] = preserve_links

    encryption = data.setdefault("encryption", {})
    if not isinstance(encryption, dict):
        raise ConfigError(f"Invalid encryption configuration in job '{job_name}'.")
    encryption.setdefault("enabled", False)
    if not isinstance(encryption["enabled"], bool):
        raise ConfigError(f"Invalid encryption.enabled in job '{job_name}'.")
    for field in ("recipient", "executable"):
        if field in encryption and (not isinstance(encryption[field], str) or not encryption[field].strip()):
            raise ConfigError(f"Invalid encryption.{field} in job '{job_name}'.")
        
    if "compression_level" not in data["archive"]:
        data["archive"]["compression_level"] = 6
    else:
        lvl = data["archive"]["compression_level"]
        if not isinstance(lvl, int) or lvl < 1 or lvl > 9:
            raise ConfigError(f"Invalid compression level {lvl} in job '{job_name}'.")

    if "change_detection" not in data:
        data["change_detection"] = {"enabled": True}
    elif not isinstance(data["change_detection"], dict):
        raise ConfigError(f"Invalid change_detection configuration in job '{job_name}'.")
    elif "enabled" not in data["change_detection"]:
        data["change_detection"]["enabled"] = True
    elif not isinstance(data["change_detection"]["enabled"], bool):
        raise ConfigError(f"Invalid change_detection.enabled in job '{job_name}'.")
        
    return data

def load_job_configs(config_dir="config", errors=None):
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
        if filename.endswith(".json"):
            if not filename.startswith("job_"):
                import logging
                logging.getLogger("backup").warning(f"File '{filename}' ignored: job files must start with 'job_' prefix")
                continue
                
            job_name = filename[4:-5]
            filepath = os.path.join(jobs_dir, filename)
            check_permissions(filepath)
                    
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("enabled", True) is False:
                    import logging
                    logging.getLogger("backup").info(f"Skipping job '{job_name}' because 'enabled' is false.")
                    continue
                data = resolve_env_vars(data)
                data = validate_job_config(job_name, data)
                jobs.append(data)
            except (ConfigError, OSError, ValueError, TypeError, KeyError) as error:
                if errors is None:
                    raise ConfigError(f"Invalid job '{job_name}': {error}") from error
                errors[job_name] = str(error)
            
    return jobs

def load_backend_credentials(config_dir="config"):
    """Loads decentralized credential layers securely out of config_dir/credentials directory."""
    creds = {}
    creds_dir = os.path.join(config_dir, "credentials")
    if not os.path.exists(creds_dir):
        return creds
        
    for filename in os.listdir(creds_dir):
        if filename.endswith(".json"):
            backend_id = filename[:-5]
            filepath = os.path.join(creds_dir, filename)
            
            # Warn if credentials layout is left world-readable 
            if platform_utils.is_linux():
                try:
                    st = os.stat(filepath)
                    import stat
                    if stat.S_IROTH & st.st_mode:
                        import logging
                        logging.getLogger("backup").warning(f"Credential {filepath} is world-readable! Consider chmod 600.")
                except Exception:
                    pass
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ConfigError(f"Credentials in {filepath} must be a JSON object.")
                creds[backend_id] = resolve_env_vars(data)
            except (ConfigError, OSError, ValueError) as error:
                if backend_id != "age":
                    raise ConfigError(f"Invalid credentials in {filepath}: {error}") from error
                # Defer optional encryption credential errors to jobs using them.
                creds[backend_id] = ConfigError(f"Invalid credentials in {filepath}: {error}")
            
    return creds
