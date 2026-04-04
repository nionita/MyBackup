# Spezifikation: Logging

## Überblick

Strukturiertes, nützliches Logging mit Python `logging`-Modul (stdlib). Zwei Ziele: Datei und Console.

---

## Log-Format

```
[2026-04-04 06:18:00] [INFO ] [webserver  ] Backup gestartet
[2026-04-04 06:18:02] [INFO ] [webserver  ] Archiv erstellt: webserver_2026-04-04T061800Z.tar.gz (45.2 MB)
[2026-04-04 06:18:05] [INFO ] [webserver  ] [aws_s3] Upload gestartet: webserver_2026-04-04T061800Z.tar.gz
[2026-04-04 06:18:35] [INFO ] [webserver  ] [aws_s3] Upload abgeschlossen (30.1s, 1.5 MB/s)
[2026-04-04 06:18:36] [INFO ] [webserver  ] [aws_s3] Retention: 3 alte Backups gelöscht, 7 behalten
[2026-04-04 06:18:37] [INFO ] [webserver  ] [google_drive] Upload gestartet
[2026-04-04 06:19:10] [INFO ] [webserver  ] [google_drive] Upload abgeschlossen (33.2s, 1.4 MB/s)
[2026-04-04 06:19:11] [INFO ] [webserver  ] Backup abgeschlossen (Dauer: 71s)
[2026-04-04 06:19:11] [INFO ] [global     ] Alle Jobs abgeschlossen. 1 erfolgreich, 0 fehlgeschlagen.
```

### Format-String

```python
fmt = "[%(asctime)s] [%(levelname)-5s] [%(job_name)-10s] %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
```

- `job_name`: Wird über einen Custom-LogAdapter oder `extra`-Dict gesetzt. Für globale Meldungen: `global`.
- Timestamps: Lokalzeit (damit der Benutzer sofort Bezug herstellen kann). UTC ist optional über Konfiguration aktivierbar.

---

## Log-Ziele

### 1. Datei

- Pfad: Konfigurierbar in `global.json`, Standard: `logs/backup.log`.
- Rotation: `RotatingFileHandler` (stdlib `logging.handlers`).
  - `maxBytes`: Konfigurierbar, Standard 10 MB.
  - `backupCount`: Konfigurierbar, Standard 5 (= maximal 50 MB Log-Speicher).
- Level: Konfigurierbar, Standard `INFO`.

### 2. Console (stdout)

- Immer aktiv.
- Level: Gleich wie Datei, oder separat konfigurierbar.
- Format: Identisch zur Datei.

---

## Log-Level-Richtlinien

| Level | Wann verwenden |
|-------|---------------|
| `DEBUG` | HTTP-Requests/Responses (gekürzt), detaillierte Signatur-Berechnungen, Datei-für-Datei-Auflistung |
| `INFO` | Job-Start/Ende, Upload-Start/Ende, Archiv-Erstellung, Retention-Ergebnis, Zusammenfassung |
| `WARNING` | Quellverzeichnis existiert nicht (aber andere schon), Dateiberechtigungen zu offen, Retry nach transientem Fehler |
| `ERROR` | Backend-Fehler (Upload fehlgeschlagen), Authentifizierungsfehler, Konfigurationsfehler |
| `CRITICAL` | Nicht verwendet (kein Szenario wo das Tool weiterlaufen aber kritisch warnen muss) |

---

## Was geloggt werden muss (Checkliste)

### Beim Start
- [ ] Tool-Version
- [ ] Python-Version
- [ ] Betriebssystem
- [ ] Anzahl geladener Jobs
- [ ] Log-Level

### Pro Job
- [ ] Job-Name, Start-Timestamp
- [ ] Quellverzeichnisse (mit Prüfung ob existent)
- [ ] Anzahl Dateien und Gesamtgröße
- [ ] Archiv-Erstellung: Format, Dateiname, Größe, Dauer
- [ ] Pro Backend:
  - [ ] Backend-Typ
  - [ ] Upload: Start, Fortschritt (bei Multipart: Part-Nummer), Ende, Dauer, Durchsatz
  - [ ] Retention: Wie viele Backups vorhanden, wie viele gelöscht, wie viele behalten
  - [ ] Fehler: HTTP-Status, Fehlermeldung, Retry-Versuch
- [ ] Job-Ende: Dauer, Erfolg/Misserfolg

### Bei Fehlern
- [ ] Vollständige Fehlermeldung
- [ ] HTTP-Status-Code und Response-Body (gekürzt auf 500 Zeichen) bei Backend-Fehlern
- [ ] Stack-Trace bei unerwarteten Fehlern (DEBUG-Level)

### Bei Abschluss
- [ ] Zusammenfassung: X Jobs erfolgreich, Y fehlgeschlagen
- [ ] Gesamtdauer

---

## Implementierung: Custom LogAdapter

```python
import logging

class JobLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['job_name']:<10}] {msg}", kwargs

# Verwendung:
logger = logging.getLogger("backup")
job_logger = JobLogAdapter(logger, {"job_name": "webserver"})
job_logger.info("Backup gestartet")
```

---

## Kein Logging sensibler Daten

Folgende Daten dürfen NIE geloggt werden (auch nicht auf DEBUG):
- AWS Secret Access Key (auch nicht teilweise)
- AWS Session Token
- Google Service Account Private Key
- Dateiinhalte der Backups
- Vollständige Pfade zu Credential-Dateien auf DEBUG-Level (nur Dateiname, nicht Pfad)

**Erlaubt** auf DEBUG:
- AWS Access Key ID (nur die letzten 4 Zeichen: `****XYZW`)
- HTTP-Response-Bodies (gekürzt, ohne Auth-Header)
- Request-URLs (ohne Query-String-Credentials)
