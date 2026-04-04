# Backup-Tool: Architektur & Hauptspezifikation

## Überblick

Plattformübergreifendes Backup-Tool in Python (≥ 3.12), das Dateien und Verzeichnisse in Cloud-Backends sichert. Nur Python-Standardbibliothek, keine externen Pakete, kein venv.

## Grundsätze

- **Nur stdlib**: Kein `pip install`, keine externen Pakete. Erlaubt sind alle Module aus der Python-Standardbibliothek (z. B. `json`, `hashlib`, `hmac`, `http.client`, `urllib`, `ssl`, `zipfile`, `tarfile`, `logging`, `configparser`, `pathlib`, `os`, `platform`, `shutil`, `datetime`, `email.utils`, `base64`, `struct`, `secrets`).
- **Cross-Platform**: Muss auf Windows 10/11 und modernem Linux (Ubuntu 22.04+, Debian 12+, Fedora 38+) identisch funktionieren.
- **Einzelinstallation**: Ein Verzeichnis pro Maschine, z. B. `/opt/backup-tool/` (Linux) oder `C:\backup-tool\` (Windows).
- **Privilegien**: Muss als root (Linux) bzw. als Administrator (Windows) laufen können, damit alle Verzeichnisse lesbar sind. Muss aber auch als normaler User laufen können (für User-spezifische Backups).

---

## Verzeichnisstruktur

```
backup-tool/
├── backup.py              # Haupt-Einstiegspunkt (CLI)
├── config/
│   ├── global.json        # Globale Einstellungen (Log-Level, Log-Pfad, Temp-Verzeichnis)
│   └── jobs/
│       ├── job_webserver.json
│       ├── job_documents.json
│       └── ...
├── backends/
│   ├── __init__.py
│   ├── base.py            # Abstrakte Backend-Klasse
│   ├── aws_s3.py          # AWS S3 Backend
│   └── google_drive.py    # Google Drive Backend
├── core/
│   ├── __init__.py
│   ├── archiver.py        # Komprimierung (tar.gz / zip)
│   ├── config_loader.py   # Konfiguration laden & validieren
│   ├── job_runner.py      # Ein Backup-Job ausführen
│   ├── retention.py       # Alte Backups rotieren/löschen
│   ├── logging_setup.py   # Logging-Konfiguration
│   └── platform_utils.py  # Plattform-spezifische Hilfsfunktionen
├── logs/
│   └── backup.log         # Standard-Log-Datei
└── README.md
```

---

## CLI-Interface

Der Einstiegspunkt ist `backup.py`. Aufruf:

```bash
# Alle konfigurierten Jobs ausführen:
python backup.py run

# Einen bestimmten Job ausführen:
python backup.py run --job webserver

# Alle Jobs auflisten:
python backup.py list-jobs

# Konfiguration validieren:
python backup.py validate

# Manuell Retention (alte Backups löschen) für einen Job ausführen:
python backup.py cleanup --job webserver

# Version anzeigen:
python backup.py version
```

CLI-Parsing: Ausschließlich mit `argparse` (stdlib).

---

## Modulbeschreibungen

### `backup.py`
- Parst CLI-Argumente mit `argparse`.
- Lädt globale Konfiguration via `config_loader`.
- Initialisiert Logging via `logging_setup`.
- Für `run`: iteriert über alle (oder den angegebenen) Jobs, instanziiert `job_runner`.
- Exit-Code: 0 = alle Jobs erfolgreich, 1 = mindestens ein Job fehlgeschlagen.

### `core/config_loader.py`
- Liest `config/global.json` und alle `config/jobs/*.json`.
- Validiert Schema (Pflichtfelder, Typen) → Fehler = klare Fehlermeldung + Abbruch.
- Gibt strukturierte Python-Dicts zurück.
- Kein externes Schema-Validierungs-Tool – eigene Validierungslogik.

### `core/job_runner.py`
- Bekommt eine Job-Konfiguration.
- Ablauf pro Job:
  1. Quellverzeichnisse lesen, prüfen ob sie existieren.
  2. Optional: Archiv erstellen (siehe `archiver`).
  3. Für jedes konfigurierte Backend:
     a. Backend-Instanz erzeugen.
     b. Backup hochladen.
     c. Retention-Policy ausführen (alte Backups löschen).
  4. Temporäre Dateien aufräumen.
- Fehlerbehandlung: Fehler in einem Backend dürfen andere Backends nicht blockieren. Jeder Backend-Fehler wird geloggt, der Job gilt als fehlgeschlagen, wenn mindestens ein Backend fehlschlägt.

### `core/archiver.py`
- Erstellt aus einer Liste von Quellverzeichnissen ein Archiv.
- Format:
  - Linux: `.tar.gz` (Standard) — mit `tarfile`-Modul.
  - Windows: `.zip` (Standard) — mit `zipfile`-Modul.
  - Konfigurierbar pro Job: `"archive_format": "tar.gz"` oder `"zip"` oder `"none"`.
- Wenn `"archive_format": "none"`: Dateien werden einzeln hochgeladen (Flat-Upload). Verzeichnisstruktur wird durch Pfad-Präfixe im Backend abgebildet.
- Archiv-Dateiname: `{job_name}_{timestamp_iso8601}.tar.gz` (z. B. `webserver_2026-04-04T061800Z.tar.gz`).
- Temporäres Verzeichnis für das Archiv: konfigurierbar in `global.json`, Fallback `tempfile.gettempdir()`.

### `core/retention.py`
- Pro Job und Backend definiert: wie viele Backup-Kopien behalten werden (`"retention_count": 5`).
- Logik: Nach erfolgreichem Upload alte Backups im Backend auflisten, nach Datum sortieren, älteste löschen bis `retention_count` erreicht.
- Backend muss dafür eine `list_backups()` und `delete_backup()` Methode bereitstellen.

### `core/logging_setup.py`
- Nutzt Python `logging`-Modul.
- Log-Ziele:
  - Datei: konfigurierbar, Standard `logs/backup.log`.
  - Console: stdout (für cron-Sichtbarkeit).
- Log-Level: konfigurierbar (`DEBUG`, `INFO`, `WARNING`, `ERROR`), Standard: `INFO`.
- Log-Format: `[2026-04-04 06:18:00] [INFO] [job:webserver] Backup started`
- Log-Rotation: Über `logging.handlers.RotatingFileHandler` (stdlib) — z. B. max 10 MB, 5 Dateien behalten.

### `core/platform_utils.py`
- `is_windows()` / `is_linux()`: Plattformerkennung via `platform.system()`.
- `get_default_paths()`: Gibt plattformspezifische Standardpfade zurück (Temp, Log).
- `check_permissions(path)`: Prüft ob ein Verzeichnis lesbar ist.
- `resolve_home(path)`: Löst `~` auf (Unix) bzw. `%USERPROFILE%` (Windows).

### `backends/base.py`
- Abstrakte Basisklasse (`abc.ABC`):

```python
from abc import ABC, abstractmethod

class BackendBase(ABC):
    @abstractmethod
    def authenticate(self) -> None:
        """Authentifizierung durchführen (Token holen etc.)."""
        ...

    @abstractmethod
    def upload(self, local_path: str, remote_key: str) -> None:
        """Datei hochladen."""
        ...

    @abstractmethod
    def list_backups(self, prefix: str) -> list[dict]:
        """Vorhandene Backups auflisten. Rückgabe: [{"key": "...", "last_modified": datetime, "size": int}]"""
        ...

    @abstractmethod
    def delete_backup(self, remote_key: str) -> None:
        """Ein bestimmtes Backup löschen."""
        ...

    @abstractmethod
    def download(self, remote_key: str, local_path: str) -> None:
        """Backup herunterladen (für Restore-Funktionalität)."""
        ...
```

---

## Konfigurationsformat

### `config/global.json`

```json
{
  "version": "1.0",
  "log_level": "INFO",
  "log_file": "logs/backup.log",
  "log_max_bytes": 10485760,
  "log_backup_count": 5,
  "temp_dir": null
}
```

- `temp_dir`: `null` = System-Temp, oder absoluter Pfad.

### Job-Konfiguration: siehe Datei `04_JOB_KONFIGURATION.md`

---

## Fehlerbehandlung

- Alle Exceptions werden gefangen und geloggt.
- Kein `sys.exit(1)` innerhalb von Modulen — nur in `backup.py` auf Top-Level.
- Fehler-Hierarchie:
  - `ConfigError`: Konfigurationsfehler (fehlende Felder, ungültige Werte).
  - `BackendError`: Fehler bei Backend-Kommunikation (Auth-Fehler, Upload-Fehler, Netzwerkfehler).
  - `ArchiveError`: Fehler beim Erstellen des Archivs (Datei nicht lesbar, Platz reicht nicht).
- Retries: Netzwerk-Operationen (Upload, List, Delete) werden bei transienten Fehlern (HTTP 5xx, Timeout) bis zu 3x wiederholt mit exponentiellem Backoff (1s, 2s, 4s). Konfigurierbar in `global.json`: `"max_retries": 3`, `"retry_base_delay_seconds": 1`.

---

## HTTP-Client

Da keine externen Libs erlaubt sind, wird `urllib.request` für alle HTTP-Operationen verwendet:

- `urllib.request.Request` für Anfragen mit Custom-Headers.
- `urllib.request.urlopen()` für die Ausführung.
- SSL-Verifikation: aktiviert (Standard). Keine Umgehung.
- Timeouts: Konfigurierbar, Standard 30 Sekunden für Verbindung, 300 Sekunden für Upload.
- Für große Dateien: Streaming-Upload via `data`-Parameter mit File-Objekt (kein vollständiges Einlesen in den Speicher).

---

## Testbarkeit

- Alle Module sollen so geschrieben sein, dass sie unabhängig testbar sind.
- Backend-Klassen bekommen Abhängigkeiten (z. B. HTTP-Client) injiziert oder verwenden eine überschreibbare Methode für HTTP-Aufrufe.
- Empfehlung für Tests: `unittest` (stdlib), mit Mock-Backends die kein echtes Cloud-Backend brauchen.

---

## Erweiterbarkeit

- Neue Backends: Neue Datei in `backends/`, Klasse erbt von `BackendBase`.
- Backend-Registrierung: `backends/__init__.py` enthält ein Registry-Dict:

```python
BACKEND_REGISTRY = {
    "aws_s3": "backends.aws_s3.AwsS3Backend",
    "google_drive": "backends.google_drive.GoogleDriveBackend",
}
```

- Neue Backends werden durch Eintrag im Registry aktiviert — kein Umbau der Core-Logik nötig.
