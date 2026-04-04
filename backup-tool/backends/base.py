from abc import ABC, abstractmethod
from datetime import datetime

class BackendBase(ABC):
    def __init__(self, job_config: dict, backend_config: dict):
        self.job_config = job_config
        self.backend_config = backend_config
        self.job_name = job_config.get("name", "unknown")

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the backend."""
        ...

    @abstractmethod
    def upload(self, local_path: str, remote_key: str) -> None:
        """Upload a file to the backend."""
        ...

    @abstractmethod
    def list_backups(self, prefix: str) -> list[dict]:
        """List backups. Returns [{"key": "...", "last_modified": datetime, "size": int}]"""
        ...

    @abstractmethod
    def delete_backup(self, remote_key: str) -> None:
        """Delete a backup from the backend."""
        ...

    @abstractmethod
    def download(self, remote_key: str, local_path: str) -> None:
        """Download a backup from the backend."""
        ...
