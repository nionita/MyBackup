import os
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET
from backends.base import BackendBase
from core import aws_sigv4

class BackendError(Exception):
    pass

class AwsS3Backend(BackendBase):
    def __init__(self, job_config: dict, backend_config: dict):
        super().__init__(job_config, backend_config)
        self.access_key = self.backend_config.get("aws_access_key_id")
        self.secret_key = self.backend_config.get("aws_secret_access_key")
        self.role_arn = self.backend_config.get("aws_role_arn")
        self.region = self.backend_config.get("aws_region", "us-east-1")
        self.bucket = self.backend_config.get("aws_bucket")
        self.prefix = self.backend_config.get("aws_prefix", "")
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"
            
        self.session_token = None
        
        self.multipart_threshold = self.backend_config.get("multipart_threshold_mb", 100) * 1024 * 1024
        self.chunk_size = self.backend_config.get("multipart_chunk_size_mb", 50) * 1024 * 1024
        
        if not self.access_key or not self.secret_key or not self.bucket:
            raise BackendError("Missing required AWS S3 configuration (keys or bucket).")
            
    def _retry_request(self, req: urllib.request.Request, max_retries=3):
        import logging
        logger = logging.getLogger("backup")
        for attempt in range(max_retries):
            try:
                response = urllib.request.urlopen(req, timeout=300)
                return response.read(), response.status, response.headers
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')
                if e.code in [403, 404]:
                    raise BackendError(f"HTTP {e.code}: {body}")
                elif e.code in [409, 500, 502, 503, 504]:
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt
                        logger.warning(f"AWS request failed with {e.code}, retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        raise BackendError(f"AWS request failed after {max_retries} attempts: HTTP {e.code} - {body}")
                else:
                    raise BackendError(f"HTTP {e.code}: {body}")
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(f"AWS request failed: {e}, retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise BackendError(f"AWS request error: {e}")
                    
        raise BackendError("Unexpected exit from retry loop")

    def authenticate(self) -> None:
        if not self.role_arn:
            return
            
        host = f"sts.{self.region}.amazonaws.com"
        
        payload = urllib.parse.urlencode({
            "Action": "AssumeRole",
            "RoleArn": self.role_arn,
            "RoleSessionName": f"backup-tool-{int(time.time())}",
            "DurationSeconds": self.backend_config.get("aws_session_duration_seconds", 3600),
            "Version": "2011-06-15"
        }).encode("utf-8")
        
        payload_hash = hashlib.sha256(payload).hexdigest()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-amz-content-sha256": payload_hash
        }
        
        signed_headers = aws_sigv4.generate_signed_headers(
            method="POST", host=host, uri="/", query="",
            access_key=self.access_key, secret_key=self.secret_key,
            region=self.region, service="sts",
            payload_hash=payload_hash, headers=headers
        )
        
        url = f"https://{host}/"
        req = urllib.request.Request(url, data=payload, headers=signed_headers, method="POST")
        resp_body, _, _ = self._retry_request(req)
        
        root = ET.fromstring(resp_body)
        creds = root.find(".//{*}Credentials")
        if creds is None:
            raise BackendError("Failed to parse STS AssumeRole response.")
            
        self.access_key = creds.findtext("{*}AccessKeyId")
        self.secret_key = creds.findtext("{*}SecretAccessKey")
        self.session_token = creds.findtext("{*}SessionToken")
        
    def _s3_request(self, method, key, query="", data=None, payload_hash=None, extra_headers=None):
        host = f"{self.bucket}.s3.{self.region}.amazonaws.com"
        # urllib requires the URI path with leading slash
        uri = f"/{key}" if key else "/"
        url = f"https://{host}{uri}"
        if query:
            url += f"?{query}"
            
        if payload_hash is None:
            if data:
                if isinstance(data, (bytes, bytearray)):
                    payload_hash = hashlib.sha256(data).hexdigest()
                else:
                    payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            else:
                payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                
        headers = {"x-amz-content-sha256": payload_hash}
        if self.session_token:
            headers["X-Amz-Security-Token"] = self.session_token
            
        if extra_headers:
            headers.update(extra_headers)
            
        signed = aws_sigv4.generate_signed_headers(
            method=method, host=host, uri=uri, query=query,
            access_key=self.access_key, secret_key=self.secret_key,
            region=self.region, service="s3",
            payload_hash=payload_hash, headers=headers
        )
        
        req = urllib.request.Request(url, data=data, headers=signed, method=method)
        return self._retry_request(req)
        
    def _get_file_hash(self, file_path):
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def upload(self, local_path: str, remote_key: str) -> None:
        file_size = os.path.getsize(local_path)
        full_remote_key = f"{self.prefix}{remote_key}"
        
        if file_size > self.multipart_threshold:
            self._multipart_upload(local_path, full_remote_key, file_size)
        else:
            self._single_upload(local_path, full_remote_key)
            
    def _single_upload(self, local_path, remote_key):
        file_hash = self._get_file_hash(local_path)
        file_size = os.path.getsize(local_path)
        
        with open(local_path, "rb") as f:
            data = f.read()
            
        extra = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_size)
        }
        self._s3_request("PUT", remote_key, data=data, payload_hash=file_hash, extra_headers=extra)

    def _multipart_upload(self, local_path, remote_key, file_size):
        import logging
        logger = logging.getLogger("backup")
        
        # 1. Initiate
        resp_body, _, _ = self._s3_request("POST", remote_key, query="uploads")
        root = ET.fromstring(resp_body)
        upload_id = root.findtext("{*}UploadId")
        if not upload_id:
            raise BackendError("Failed to get UploadId")
            
        parts = []
        try:
            with open(local_path, "rb") as f:
                part_num = 1
                while True:
                    data = f.read(self.chunk_size)
                    if not data:
                        break
                        
                    logger.info(f"Uploading part {part_num} of {remote_key}...")
                    payload_hash = hashlib.sha256(data).hexdigest()
                    extra = {"Content-Length": str(len(data))}
                    
                    query = f"partNumber={part_num}&uploadId={upload_id}"
                    _, _, resp_headers = self._s3_request("PUT", remote_key, query=query, data=data, payload_hash=payload_hash, extra_headers=extra)
                    
                    # Store ETag
                    etag = resp_headers.get("ETag")
                    parts.append((part_num, etag))
                    part_num += 1
                    
            # 3. Complete
            complete_xml = "<CompleteMultipartUpload>\n"
            for p_num, e_tag in parts:
                complete_xml += f"  <Part><PartNumber>{p_num}</PartNumber><ETag>{e_tag}</ETag></Part>\n"
            complete_xml += "</CompleteMultipartUpload>"
            
            complete_data = complete_xml.encode('utf-8')
            extra = {"Content-Type": "application/xml", "Content-Length": str(len(complete_data))}
            query = f"uploadId={upload_id}"
            
            # Use 'UNSIGNED-PAYLOAD' for hash as AWS supports it, or compute it. Let's compute it.
            self._s3_request("POST", remote_key, query=query, data=complete_data, extra_headers=extra)
            
        except Exception as e:
            # Abort Multipart Upload
            self._s3_request("DELETE", remote_key, query=f"uploadId={upload_id}")
            raise BackendError(f"Multipart upload failed: {e}")

    def list_backups(self, prefix: str) -> list[dict]:
        full_prefix = f"{self.prefix}{prefix}"
        query = f"list-type=2&prefix={full_prefix}"
        
        backups = []
        continuation_token = None
        
        while True:
            current_query = query
            if continuation_token:
                current_query += f"&continuation-token={urllib.parse.quote(continuation_token)}"
                
            resp_body, _, _ = self._s3_request("GET", "", query=current_query)
            root = ET.fromstring(resp_body)
            
            for content in root.findall("{*}Contents"):
                key = content.findtext("{*}Key")
                last_modified_str = content.findtext("{*}LastModified")
                size = int(content.findtext("{*}Size", "0"))
                last_modified = datetime.strptime(last_modified_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                
                # We strip the full prefix out to return the relative remote_key?
                # Actually, the BackendBase says list_backups returns "key", we'll just return the raw S3 key.
                backups.append({
                    "key": key,
                    "last_modified": last_modified,
                    "size": size
                })
                
            is_truncated = root.findtext("{*}IsTruncated")
            if is_truncated == "true":
                continuation_token = root.findtext("{*}NextContinuationToken")
            else:
                break
                
        return backups

    def delete_backup(self, remote_key: str) -> None:
        self._s3_request("DELETE", remote_key)
        
    def download(self, remote_key: str, local_path: str) -> None:
        # Extra: Simple download implementation
        pass
