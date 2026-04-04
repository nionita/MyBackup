# Spezifikation: Backup-Job Konfiguration

## Überblick

Jeder Backup-Job ist eine eigene JSON-Datei unter `config/jobs/`. Jeder Job definiert: welche Verzeichnisse gesichert werden, in welche Backends, mit welchen Optionen.

---

## Dateiname-Konvention

`job_{name}.json` — z. B. `job_webserver.json`, `job_documents.json`.

Der `name`-Feld innerhalb der Datei muss mit dem Dateinamen (ohne `job_`-Präfix und `.json`) übereinstimmen. Das Tool prüft dies bei der Validierung.

---

## Schema

```json
{
  "name": "webserver",
  "description": "Tägliches Backup der Webserver-Konfiguration und Daten",
  "enabled": true,

  "sources": [
    "/etc/nginx",
    "/var/www/html",
    "/etc/letsencrypt"
  ],

  "exclude_patterns": [
    "*.tmp",
    "*.log",
    "__pycache__",
    ".git"
  ],

  "archive": {
    "format": "tar.gz",
    "compression_level": 6
  },

  "backends": [
    {
      "backend_type": "aws_s3",
      "aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID",
      "aws_secret_access_key": "$ENV:AWS_SECRET_ACCESS_KEY",
      "aws_role_arn": "arn:aws:iam::123456789012:role/BackupRole",
      "aws_session_duration_seconds": 3600,
      "aws_region": "eu-central-1",
      "aws_bucket": "my-backup-bucket",
      "aws_prefix": "backups/webserver/",
      "multipart_threshold_mb": 100,
      "multipart_chunk_size_mb": 50,
      "retention_count": 7
    },
    {
      "backend_type": "google_drive",
      "gd_service_account_json": "/opt/backup-tool/credentials/gd_service_account.json",
      "gd_folder_id": "1AbC_dEfGhIjKlMnOpQrStUvWxYz",
      "gd_upload_chunk_size_mb": 50,
      "retention_count": 5
    }
  ]
}
```

---

## Feldbeschreibung

### Job-Ebene

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|-------------|
| `name` | string | ja | Eindeutiger Job-Name, alphanumerisch + Unterstrich |
| `description` | string | nein | Menschenlesbare Beschreibung |
| `enabled` | bool | ja | `false` = Job wird bei `run` übersprungen |
| `sources` | list[string] | ja | Absolut-Pfade zu Verzeichnissen/Dateien die gesichert werden |
| `exclude_patterns` | list[string] | nein | Glob-Patterns für Dateien/Verzeichnisse die ausgeschlossen werden |
| `archive` | object | nein | Archivierungs-Optionen (wenn nicht gesetzt: Standardwerte) |
| `backends` | list[object] | ja | Mindestens ein Backend |

### `sources`-Feld

- Absolut-Pfade, plattformgerecht (Linux: `/var/www`, Windows: `C:\Users\me\Documents`).
- Symlinks: Werden standardmäßig gefolgt (d. h. das Ziel wird gesichert). Später optional: `"follow_symlinks": false`.
- Nicht existierende Quellen: Werden geloggt als WARNING, Job läuft weiter mit den vorhandenen Quellen. Wenn ALLE Quellen fehlen → Job schlägt fehl.

### `exclude_patterns`-Feld

- Glob-Patterns, ausgewertet mit `fnmatch` (stdlib) auf den relativen Dateipfad innerhalb der Quelle.
- Beispiele: `"*.tmp"` matcht alle `.tmp`-Dateien, `"__pycache__"` matcht Verzeichnisse mit dem Namen.
- Ausschluss-Prüfung sowohl auf Dateinamen als auch auf Verzeichnisnamen.

### `archive`-Objekt

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|-------------|
| `format` | string | `"tar.gz"` (Linux), `"zip"` (Windows) | `"tar.gz"`, `"zip"` oder `"none"` |
| `compression_level` | int | 6 | 1 (schnell, wenig Kompression) bis 9 (langsam, max. Kompression) |

- Wenn `"format": "none"`: Dateien werden einzeln hochgeladen. Verzeichnisstruktur wird durch Pfad-Präfixe abgebildet. Retention bezieht sich dann auf "Backup-Sets" (gruppiert nach Timestamp-Präfix).

### `backends`-Liste

Jedes Element ist ein Objekt mit:
- `backend_type` (Pflicht): Identifiziert das Backend (`"aws_s3"`, `"google_drive"`).
- `retention_count` (Pflicht): Wie viele Backup-Kopien in diesem Backend behalten werden.
- Backend-spezifische Felder: siehe `02_BACKEND_AWS_S3.md` und `03_BACKEND_GOOGLE_DRIVE.md`.

Ein Job kann mehrere Backends haben (z. B. gleichzeitig in S3 und Google Drive sichern). Backends werden sequenziell abgearbeitet. Fehler in einem Backend blockieren nicht die anderen.

---

## Credential-Referenzierung via Umgebungsvariablen

Jedes String-Feld, das mit `$ENV:` beginnt, wird als Umgebungsvariablen-Referenz interpretiert:

```json
"aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID"
```

Das Tool liest den Wert von `os.environ["AWS_ACCESS_KEY_ID"]`. Wenn die Variable nicht gesetzt ist → Fehler mit klarer Meldung.

Vorteil: Credentials müssen nicht im Klartext in Konfigurationsdateien stehen.

---

## Beispiel: Minimaler Job

```json
{
  "name": "home_docs",
  "enabled": true,
  "sources": [
    "/home/nicu/Documents"
  ],
  "backends": [
    {
      "backend_type": "aws_s3",
      "aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID",
      "aws_secret_access_key": "$ENV:AWS_SECRET_ACCESS_KEY",
      "aws_region": "eu-central-1",
      "aws_bucket": "nicu-backups",
      "aws_prefix": "home_docs/",
      "retention_count": 10
    }
  ]
}
```

Hier wird ohne explizite `archive`-Konfiguration gearbeitet → Standardwerte (tar.gz auf Linux, zip auf Windows, Kompression 6).

---

## Beispiel: Windows-Job

```json
{
  "name": "windows_projects",
  "description": "Wöchentliches Backup der Projektdaten",
  "enabled": true,
  "sources": [
    "C:\\Users\\nicu\\Projects",
    "C:\\Users\\nicu\\Documents\\config"
  ],
  "exclude_patterns": [
    "node_modules",
    ".venv",
    "*.pyc",
    "*.obj"
  ],
  "archive": {
    "format": "zip",
    "compression_level": 6
  },
  "backends": [
    {
      "backend_type": "google_drive",
      "gd_service_account_json": "C:\\backup-tool\\credentials\\gd_service_account.json",
      "gd_folder_id": "1AbC_dEfGhIjKlMnOpQrStUvWxYz",
      "retention_count": 4
    }
  ]
}
```

---

## Validierungsregeln

Das Tool prüft beim Start (oder via `python backup.py validate`):

1. `name`: Muss alphanumerisch + Unterstrich sein, nicht leer.
2. `name` muss mit Dateiname übereinstimmen.
3. `sources`: Mindestens ein Eintrag. Warnung wenn ein Pfad nicht existiert.
4. `backends`: Mindestens ein Eintrag.
5. `backend_type`: Muss im Backend-Registry existieren.
6. `retention_count`: Muss ganzzahlig und ≥ 1 sein.
7. Backend-spezifische Pflichtfelder: Pro Backend-Typ geprüft (z. B. `aws_bucket` für S3).
8. `$ENV:`-Referenzen: Prüfen ob die Umgebungsvariable existiert (nur beim tatsächlichen Ausführen, nicht bei `validate` — dort nur Syntax-Check).
9. `archive.format`: Muss einer von `"tar.gz"`, `"zip"`, `"none"` sein.
10. `archive.compression_level`: 1–9.
11. Dateiberechtigungen der Konfigurationsdatei prüfen (Linux: max 0o644, Warnung wenn world-readable bei Credential-Inhalten).

---

## Backup-Benennung im Backend

Format: `{prefix}{job_name}/{job_name}_{iso8601_timestamp}{extension}`

Beispiel: `backups/webserver/webserver_2026-04-04T061800Z.tar.gz`

- Timestamp: UTC, ISO 8601, ohne Sonderzeichen die Probleme machen (`T` statt Leerzeichen, keine `:` → `HHMMSS`).
- Dadurch sind Backups natürlich chronologisch sortierbar.
