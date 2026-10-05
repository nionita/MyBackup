"""Optional file encryption through the external age executable (stdlib only)."""

import os
import re
import shutil
import subprocess
import tempfile


class EncryptionError(Exception):
    pass


def _executable(name):
    if not isinstance(name, str) or not name.strip():
        raise EncryptionError("age executable must be a non-empty string.")
    path = shutil.which(name)
    if path is None:
        raise EncryptionError(f"age executable not found: {name}")
    return os.path.abspath(path)


def _run(arguments, *, stdout, timeout=None):
    # Keep both payload and diagnostic output off Python's heap.
    with tempfile.TemporaryFile() as errors:
        try:
            result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=errors, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise EncryptionError(f"Could not run age: {error}") from error
        if result.returncode:
            errors.seek(0)
            detail = errors.read(4096).decode("utf-8", errors="replace").strip()
            raise EncryptionError(f"age failed (exit {result.returncode}): {detail}")


def prepare(job_config, credentials=None):
    """Merge credentials and check age/recipient before any backup operations."""
    config = job_config.get("encryption", {})
    if not config.get("enabled", False):
        return None
    shared = (credentials or {}).get("age", {})
    if isinstance(shared, Exception):
        if "recipient" not in config:
            raise EncryptionError(f"Cannot load shared age credentials: {shared}")
        # A job with its own recipient can operate independently of age.json.
        shared = {}
    if not isinstance(shared, dict):
        raise EncryptionError("Shared age credentials must be a JSON object.")
    effective = {**shared, **config}
    recipient = effective.get("recipient")
    # Native v1 age recipients only; age itself checks the Bech32 checksum.
    if not isinstance(recipient, str) or not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}", recipient):
        raise EncryptionError("Encryption requires one native age public recipient (age1...).")
    executable = _executable(effective.get("executable", "age"))
    # Encrypt an empty input to validate the recipient and executable even when
    # change detection would skip the actual backup. No source data is read.
    _run([executable, "--encrypt", "--recipient", recipient],
         stdout=subprocess.DEVNULL, timeout=30)
    return {"recipient": recipient, "executable": executable}


def encrypt_archive(archive_path, settings):
    """Encrypt once to an owner-only file; remove incomplete output on failure."""
    output = archive_path + ".age"
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            _run([settings["executable"], "--encrypt", "--recipient", settings["recipient"],
                  os.path.abspath(archive_path)], stdout=stream)
        return output
    except BaseException:
        os.unlink(output)
        raise


def decrypt(input_path, identity_path, output_path, executable="age"):
    """Decrypt fully before publishing; never overwrite an existing output."""
    output_path = os.path.abspath(output_path)
    if os.path.lexists(output_path):
        raise EncryptionError(f"Output already exists: {output_path}")
    executable = _executable(executable)
    fd, temporary = tempfile.mkstemp(prefix=".age-decrypt-", dir=os.path.dirname(output_path))
    try:
        with os.fdopen(fd, "wb") as stream:
            _run([executable, "--decrypt", "--identity", os.path.abspath(identity_path),
                  os.path.abspath(input_path)], stdout=stream)
            stream.flush()
            os.fsync(stream.fileno())
        # An atomic, no-overwrite publication on Linux and Windows/NTFS.
        # Unlike replace/rename this cannot clobber a concurrently created file.
        os.link(temporary, output_path)
    except OSError as error:
        raise EncryptionError(f"Could not publish decrypted archive: {error}") from error
    finally:
        os.unlink(temporary)
