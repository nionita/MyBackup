# Agent Context & Findings

This document tracks vital architecture notes, structural findings, and testing quirks specifically useful to help future AI agents avoid redundant research or pitfalls!

## Project Scope Constraint
The cross-platform Backup Tool is built globally in **Python 3.12+**. 
**Crucial Condition**: No third-party bindings or environments (`pip`, `venv`, `boto3`) are allowed. Everything relies purely on the OS core Python Built-ins.

## Directory Structure Map
- **Application App**: `backup-tool/`
- **Testing Modules**: `tests/`
- **German Documentation Specs**: `backup_spec/` (Contains original `01...` through `06` module specific specs).
- **Setup Guides**: `AWS_SETUP_GUIDE.md`, `GDRIVE_SETUP_GUIDE.md` at repo root.

## Credentials Architecture
Backend credentials (API keys, tokens) are **decoupled from job configs**. They live in `<config-dir>/credentials/<backend_type>.json` (e.g. `google_drive.json`, `aws_s3.json`). The `config_loader.load_backend_credentials()` function reads them, and `job_runner.instantiate_backend()` merges them into each backend's config at runtime. **Merge priority**: job-level keys override global credential keys (not the other way around). This means a user can have shared credentials but per-job overrides like `gd_folder_id`.

## Engineering Decisions
- **Cross-Platform Nuances**: Path mappings fall back via `core/platform_utils.py` (e.g., matching `%TEMP%` vs `/tmp`).
- **AWS API Mechanics**: 
  - Authentic `aws_sigv4.py` natively implements HMAC SHA256 validation sequences.
  - S3 Object API targets (uploading/deleting/listing via `list-type=2`) use native `urllib.request` pipelines. 
  - Multiparts trigger thresholds default to uploading exactly `50MB` arrays if raw objects bypass `100MB`.
  - The STS `AssumeRole` token fetcher maps XML namespace outputs via `xml.etree.ElementTree` dynamically (`.//{*}Credentials`).
- **Google Drive API Mechanics**:
  - Two auth modes: Service Account (JWT/RSA) and Consumer OAuth (refresh tokens). Routing is automatic based on which config keys are present (`gd_service_account_file` vs `gd_refresh_token`).
  - RSA signing uses a hybrid approach: OpenSSL subprocess first, pure-Python math fallback (`core/rsa_signer.py`).
  - Uploads use the Drive v3 resumable upload protocol with 10MB chunks.
  - The OAuth scope **must be** `https://www.googleapis.com/auth/drive` (full scope). The narrower `drive.file` scope silently blocks uploads to folders the user didn't create via the API.
- **Security Hardening**:
  - Credential files are written with `os.open(..., 0o600)` — never plain `open()`.
  - The OAuth callback server binds to `127.0.0.1` only (not `0.0.0.0`).
  - OAuth flow uses a `secrets.token_urlsafe(32)` CSRF state parameter.
  - CLI never accepts secrets as command-line arguments (they leak into process tables). Use interactive `input()` prompts only.
  - Temp files for OpenSSL key material are created with `0o600` permissions.

## Google Cloud Console Pitfalls
These are things that tripped us up and will trip up any user or agent again:
- **403 access_denied on first OAuth login**: New OAuth apps are in "Testing" mode. You MUST either publish the app OR add the user's email under OAuth Consent Screen → Test Users. The error message is in German and not obvious.
- **Service Account 403 on upload**: Service Accounts have their own email (e.g. `sa@project.iam.gserviceaccount.com`). The target Google Drive folder must be explicitly shared with that email. Even then, Service Account storage counts against the 15GB project quota, not the user's Drive quota — this is why Consumer OAuth is preferred for personal use.
- **Headless servers**: Google banned OOB (Out-of-Band) auth flows in 2022. The `setup-gdrive` command must be run on a machine with a browser. The resulting `google_drive.json` can then be copied to the headless server.

## Testing Findings & Environment Warnings
- Since we use standard `unittest`, tests require forcing `PYTHONPATH` references against `./backup-tool`.
- To run tests via Powershell organically execute:
  ```powershell
  $env:PYTHONPATH="backup-tool"; python -m unittest discover tests/
  ```
- **CAUTION during `tearDown()` in Logging test scenarios:**
  Make absolutely sure to clear and gracefully close standard `logging` Handlers! Without explicit teardown loops calling `handler.close()`, Windows OS throws heavy `PermissionError [WinError 32]` halts constantly as `RotatingFileHandler` permanently locks temporal test-log files blocking `tempfile.TemporaryDirectory().cleanup()` sweeps!
- **Credential merge tests** (`test_config_loader.py::test_load_backend_credentials`): These actually instantiate the `GoogleDriveBackend` class to verify merge priority. If you change the backend constructor signature, this test will break.

## Future Roadmap Priorities
- **AES Backup Output Encryption Setup** (Deferred until architecture passes `ENTSCHEIDUNG_VERSCHLUESSELUNG.md`).

