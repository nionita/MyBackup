import os
import json
import time
import base64
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from backends.base import BackendBase
from core import rsa_signer

class GoogleDriveBackend(BackendBase):
    def __init__(self, job_config: dict, backend_config: dict):
        super().__init__(job_config, backend_config)
        self.folder_id = self.backend_config.get("gd_folder_id")
        self.force_pure_python = self.backend_config.get("gd_force_pure_python_rsa", False)
        
        # Scenario A: Service account integration (Enterprise/Workspace)
        self.service_account_file = self.backend_config.get("gd_service_account_file")
        
        # Scenario B: Consumer OAuth integration (Refresh tokens bypass storage quotas)
        self.client_id = self.backend_config.get("gd_client_id")
        self.client_secret = self.backend_config.get("gd_client_secret")
        self.refresh_token = self.backend_config.get("gd_refresh_token")
        
        if not self.folder_id:
            raise ValueError("Google Drive target Folder ID (gd_folder_id) is missing")
            
        # Determine authentication methodology based on provided configuration keys
        if self.refresh_token:
            if not self.client_id or not self.client_secret:
                raise ValueError("When using 'gd_refresh_token', you must also provide 'gd_client_id' and 'gd_client_secret'.")
        elif self.service_account_file:
            if not os.path.exists(self.service_account_file):
                raise ValueError(f"Google Drive service account JSON file missing: {self.service_account_file}")
            with open(self.service_account_file, "r") as f:
                self.sa_creds = json.load(f)
        else:
            raise ValueError("Google Drive backend requires either a 'gd_service_account_file' OR a valid 'gd_refresh_token' mapping.")
            
        self.access_token = None
        self.token_expiry = 0
        
    def _b64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')
        
    def _generate_jwt(self) -> str:
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claim = {
            "iss": self.sa_creds["client_email"],
            "scope": "https://www.googleapis.com/auth/drive",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": now + 3600,
            "iat": now
        }
        
        b64_hdr = self._b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        b64_clm = self._b64url_encode(json.dumps(claim, separators=(',', ':')).encode('utf-8'))
        
        signature_input = f"{b64_hdr}.{b64_clm}".encode('utf-8')
        
        signature = rsa_signer.sign_rsa_sha256(
            payload=signature_input, 
            private_key_pem=self.sa_creds["private_key"],
            force_pure_python=self.force_pure_python
        )
        
        b64_sig = self._b64url_encode(signature)
        return f"{b64_hdr}.{b64_clm}.{b64_sig}"

    def authenticate(self) -> None:
        if time.time() < self.token_expiry - 60 and self.access_token:
            return
            
        # Scenario B: OAuth User Consent Refresh Flow
        if self.refresh_token:
            data = urllib.parse.urlencode({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token"
            }).encode("utf-8")
        else:
            # Scenario A: RSA Service Account JWT Flow
            jwt_token = self._generate_jwt()
            data = urllib.parse.urlencode({
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token
            }).encode("utf-8")
        
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token", 
            data=data, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                self.access_token = resp_data["access_token"]
                self.token_expiry = time.time() + resp_data.get("expires_in", 3600)
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            raise Exception(f"Failed to authenticate with Google API: {e.code} {err}")

    def upload(self, local_path: str, remote_key: str) -> None:
        self.authenticate()
        logger = logging.getLogger("backup")
        file_size = os.path.getsize(local_path)
        filename = os.path.basename(local_path)
        
        # 1. Initiate Resumable Upload
        metadata = {
            "name": filename,
            "parents": [self.folder_id]
        }
        
        init_req = urllib.request.Request(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
            data=json.dumps(metadata).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size)
            },
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(init_req) as response:
                upload_url = response.headers.get("Location")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            raise Exception(f"HTTP Error {e.code}: {err_body}")
            
        chunk_size = 10 * 1024 * 1024  # 10MB Chunks
        
        # 2. Upload Chunks
        with open(local_path, "rb") as f:
            start_byte = 0
            while start_byte < file_size:
                chunk = f.read(chunk_size)
                end_byte = start_byte + len(chunk) - 1
                
                logger.info(f"[google_drive] Pushing block bytes {start_byte}-{end_byte} of {file_size}...")
                
                chunk_req = urllib.request.Request(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}"
                    },
                    method="PUT"
                )
                
                try:
                    with urllib.request.urlopen(chunk_req) as chunk_resp:
                        if chunk_resp.status in (200, 201):
                            break # Upload completely finished
                except urllib.error.HTTPError as e:
                    if e.code == 308:
                        # 308 Resume Incomplete - Expected when uploading parts
                        start_byte += len(chunk)
                        continue
                    else:
                        raise Exception(f"Chunk upload failed: {e.code} {e.read().decode()}")

    def list_backups(self, prefix: str) -> list[dict]:
        self.authenticate()
        
        # Fetch files matching exact job prefix naming rules to target retention
        job_name = prefix.rstrip('/')
        query = f"'{self.folder_id}' in parents and name contains '{job_name}_' and trashed=false"
        url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name,createdTime,size)&pageSize=100"
        
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.access_token}"})
        
        backups = []
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            for f in data.get("files", []):
                dt = datetime.strptime(f["createdTime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                backups.append({
                    "key": f["id"], # We return file ID as key for GDrive deletions
                    "name": f["name"],
                    "last_modified": dt,
                    "size": int(f.get("size", 0))
                })
                
        return backups

    def delete_backup(self, remote_key: str) -> None:
        self.authenticate()
        req = urllib.request.Request(
            f"https://www.googleapis.com/drive/v3/files/{remote_key}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            method="DELETE"
        )
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code != 404: # Ignore deletions of missing objects
                raise Exception(f"Delete failed: {e.code} {e.read().decode()}")

    def download(self, remote_key: str, local_path: str) -> None:
        pass
