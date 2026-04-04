import platform
import os
import pathlib

def is_windows() -> bool:
    """Returns True if the current platform is Windows."""
    return platform.system().lower() == "windows"

def is_linux() -> bool:
    """Returns True if the current platform is Linux."""
    return platform.system().lower() == "linux"

def get_default_paths() -> dict:
    """Returns default paths depending on the platform."""
    if is_windows():
        return {
            "temp_dir": os.environ.get("TEMP", "C:\\temp"),
            "log_dir": "C:\\backup-tool\\logs",
            "install_dir": "C:\\backup-tool"
        }
    else:
        # Default for Linux
        return {
            "temp_dir": "/tmp",
            "log_dir": "/opt/backup-tool/logs",
            "install_dir": "/opt/backup-tool"
        }

def check_permissions(path: str) -> bool:
    """Checks if a path is readable."""
    return os.access(path, os.R_OK)

def resolve_home(path: str) -> str:
    """Resolves ~ (Unix) or %USERPROFILE% (Windows)."""
    p = str(path)
    if is_windows() and "%USERPROFILE%" in p:
        user_profile = os.environ.get("USERPROFILE", "")
        p = p.replace("%USERPROFILE%", user_profile)
    
    p = os.path.expanduser(p)
    
    # pathlib.Path.resolve() converts it to an absolute path cleanly
    try:
        return str(pathlib.Path(p).resolve())
    except Exception:
        return str(pathlib.Path(p).absolute())
