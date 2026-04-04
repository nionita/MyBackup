# Backup-Tool: Spezifikationspaket

## Für den Programmieragenten

Dieses Verzeichnis enthält alle Spezifikationen, um ein plattformübergreifendes Backup-Tool in Python zu implementieren. Lies die Dateien in der angegebenen Reihenfolge.

## Dateien

| # | Datei | Inhalt | Status |
|---|-------|--------|--------|
| 1 | `01_ARCHITEKTUR_UND_HAUPTSPEZIFIKATION.md` | Architektur, Module, CLI, Verzeichnisstruktur, Fehlerbehandlung, HTTP-Client | Bereit zur Implementierung |
| 2 | `02_BACKEND_AWS_S3.md` | AWS S3 Backend: SigV4, STS, REST API, Multipart Upload | Bereit zur Implementierung |
| 3 | `03_BACKEND_GOOGLE_DRIVE.md` | Google Drive Backend: Service Account, JWT, REST API, Resumable Upload | Bereit, aber ENTSCHEIDUNG nötig (RSA) |
| 4 | `04_JOB_KONFIGURATION.md` | Job-Format, Schema, Validierung, Beispiele | Bereit zur Implementierung |
| 5 | `05_SCHEDULING_UND_INSTALLATION.md` | cron (Linux), Task Scheduler (Windows), Setup | Bereit zur Implementierung |
| 6 | `06_LOGGING.md` | Log-Format, Level, Rotation, sensible Daten | Bereit zur Implementierung |

## Entscheidungsdokumente (vor Implementierung klären)

| Datei | Thema | Wann relevant |
|-------|-------|---------------|
| `ENTSCHEIDUNG_RSA_SIGNIERUNG.md` | Wie RSA für Google Drive JWT implementieren (Pure-Python vs. OpenSSL vs. Bibliothek) | **Vor Start des Google Drive Backends** |
| `ENTSCHEIDUNG_VERSCHLUESSELUNG.md` | Lokale Verschlüsselung: Methode, Key-Management, Rotation | **Spätere Phase — nicht für v1** |

## Rahmenbedingungen

- **Python ≥ 3.12**, nur Standardbibliothek
- **Kein** `pip install`, kein venv, kein `boto3`, kein `google-auth`, kein `requests`
- Cross-Platform: Windows 10/11 + Linux (Ubuntu 22.04+, Debian 12+, Fedora 38+)
- Nur Dateisystem-Backup (keine Datenbank-Dumps)
- Backends: AWS S3 und Google Drive (erweiterbar durch Plugin-Architektur)
- Scheduling: extern (cron / Windows Task Scheduler)

## Implementierungsreihenfolge (Empfehlung)

1. **Core-Infrastruktur**: `backup.py` CLI, `config_loader`, `logging_setup`, `platform_utils`
2. **Archiver**: `archiver.py` (tar.gz + zip)
3. **Backend-Basis**: `base.py` (abstrakte Klasse)
4. **AWS S3 Backend**: Komplett inkl. SigV4, STS, Multipart — (komplex, aber gut dokumentiert)
5. **Job Runner + Retention**: `job_runner.py`, `retention.py`
6. **Google Drive Backend**: Abhängig von RSA-Entscheidung
7. **Scheduling-Helpers**: `install-scheduler` / `uninstall-scheduler` Kommandos
8. **Setup-Kommando**: `setup`
9. **(Später) Verschlüsselung**: Abhängig von Entscheidung
