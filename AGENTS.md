# Agent Context & Findings

This document tracks vital architecture notes, structural findings, and testing quirks specifically useful to help future AI agents avoid redundant research or pitfalls!

## Project Scope Constraint
The cross-platform Backup Tool is built globally in **Python 3.12+**. 
**Crucial Condition**: No third-party bindings or environments (`pip`, `venv`, `boto3`) are allowed. Everything relies purely on the OS core Python Built-ins.

## Directory Structure Map
- **Application App**: `backup-tool/`
- **Testing Modules**: `tests/`
- **German Documentation Specs**: `backup_spec/` (Contains original `01...` through `06` module specific specs).

## Engineering Decisions
- **Cross-Platform Nuances**: Path mappings fall back via `core/platform_utils.py` (e.g., matching `%TEMP%` vs `/tmp`).
- **AWS API Mechanics**: 
  - Authentic `aws_sigv4.py` natively implements HMAC SHA256 validation sequences.
  - S3 Object API targets (uploading/deleting/listing via `list-type=2`) use native `urllib.request` pipelines. 
  - Multiparts trigger thresholds default to uploading exactly `50MB` arrays if raw objects bypass `100MB`.
  - The STS `AssumeRole` token fetcher maps XML namespace outputs via `xml.etree.ElementTree` dynamically (`.//{*}Credentials`).

## Testing Findings & Environment Warnings
- Since we use standard `unittest`, tests require forcing `PYTHONPATH` references against `./backup-tool`.
- To run tests via Powershell organically execute:
  ```powershell
  $env:PYTHONPATH="backup-tool"; python -m unittest discover tests/
  ```
- **CAUTION during `tearDown()` in Logging test scenarios:**
  Make absolutely sure to clear and gracefully close standard `logging` Handlers! Without explicit teardown loops calling `handler.close()`, Windows OS throws heavy `PermissionError [WinError 32]` halts constantly as `RotatingFileHandler` permanently locks temporal test-log files blocking `tempfile.TemporaryDirectory().cleanup()` sweeps!

## Future Roadmap Priorities
- **Google Drive Backend Endpoint** (Requires establishing RSA architecture inside `ENTSCHEIDUNG_RSA_SIGNIERUNG.md`).
- **AES Backup Output Encryption Setup** (Deferred until architecture passes `ENTSCHEIDUNG_VERSCHLUESSELUNG.md`).
