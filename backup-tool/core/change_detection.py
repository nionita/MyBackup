"""Local, backend-neutral source change detection for backup jobs."""

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone

from core import archiver


STATE_VERSION = 1
FINGERPRINT_VERSION = 1


class StateError(Exception):
    """Raised when local change-detection state cannot be persisted."""


def _add_value(digest, value):
    """Add a length-delimited value, avoiding ambiguous hash inputs."""
    if not isinstance(value, bytes):
        value = str(value).encode("utf-8", errors="surrogateescape")
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _add_metadata(digest, file_stat):
    _add_value(digest, stat.S_IFMT(file_stat.st_mode))
    _add_value(digest, stat.S_IMODE(file_stat.st_mode))
    _add_value(digest, file_stat.st_mtime_ns)
    if os.name != "nt":
        _add_value(digest, file_stat.st_uid)
        _add_value(digest, file_stat.st_gid)


def calculate_source_fingerprint(sources, exclude_patterns, preserve_directory_symlinks=False):
    """Hash the exact included archive payload and restorable metadata."""
    digest = hashlib.sha256()
    _add_value(digest, f"source-fingerprint-v{FINGERPRINT_VERSION}")

    for file_path, archive_name in archiver.iter_included_files(sources, exclude_patterns, preserve_directory_symlinks):
        file_stat = os.lstat(file_path)
        _add_value(digest, "entry")
        _add_value(digest, archive_name.replace(os.path.sep, "/"))
        _add_metadata(digest, file_stat)

        if stat.S_ISLNK(file_stat.st_mode):
            _add_value(digest, "symlink")
            _add_value(digest, os.readlink(file_path))
        elif stat.S_ISREG(file_stat.st_mode):
            _add_value(digest, "file")
            with open(file_path, "rb") as source_file:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    _add_value(digest, chunk)
        else:
            _add_value(digest, "other")

    return digest.hexdigest()


def calculate_policy_fingerprint(job_config, encryption_settings=None):
    """Hash settings which alter the archive payload without exposing secrets."""
    policy = {
        "version": FINGERPRINT_VERSION,
        "sources": job_config.get("sources", []),
        "exclude_patterns": job_config.get("exclude_patterns", []),
        "archive": job_config.get("archive", {}),
    }
    if encryption_settings is not None:
        policy["encryption"] = {
            "enabled": True,
            "recipient_sha256": hashlib.sha256(encryption_settings["recipient"].encode("utf-8")).hexdigest(),
        }
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def state_path(state_dir, job_name):
    return os.path.join(state_dir, f"{job_name}.json")


def load_state(state_dir, job_name, logger):
    path = state_path(state_dir, job_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as state_file:
            loaded = json.load(state_file)
        if not isinstance(loaded, dict) or loaded.get("version") != STATE_VERSION:
            raise ValueError("unsupported state format")
        if not isinstance(loaded.get("destinations", {}), dict):
            raise ValueError("invalid destination records")
        return loaded
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.warning("Change-detection state ignored: %s", error)
        return None


def destination_key(identity):
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def destination_is_current(state, source_fingerprint, policy_fingerprint, identity):
    if not state:
        return False
    if state.get("source_fingerprint") != source_fingerprint:
        return False
    if state.get("policy_fingerprint") != policy_fingerprint:
        return False
    record = state.get("destinations", {}).get(destination_key(identity))
    return bool(record and record.get("identity") == identity)


def record_destination_success(state, source_fingerprint, policy_fingerprint, identity):
    """Return updated state containing one successfully protected destination."""
    if not state or state.get("source_fingerprint") != source_fingerprint or state.get("policy_fingerprint") != policy_fingerprint:
        state = {
            "version": STATE_VERSION,
            "source_fingerprint": source_fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "destinations": {},
        }
    else:
        state = {
            "version": STATE_VERSION,
            "source_fingerprint": source_fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "destinations": dict(state["destinations"]),
        }

    state["destinations"][destination_key(identity)] = {
        "identity": identity,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return state


def save_state(state_dir, job_name, state):
    """Persist state atomically with owner-only file permissions."""
    try:
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        os.chmod(state_dir, 0o700)
        path = state_path(state_dir, job_name)
        fd, temporary_path = tempfile.mkstemp(prefix=f".{job_name}.", suffix=".tmp", dir=state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file, indent=2, sort_keys=True)
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
            os.chmod(path, 0o600)
        except Exception:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
            raise
    except OSError as error:
        raise StateError(f"Could not save change-detection state: {error}") from error
