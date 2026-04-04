# Spezifikation: Scheduling & Installation

## Überblick

Das Backup-Tool selbst enthält keinen eigenen Scheduler. Es wird von externen Mechanismen aufgerufen:
- **Linux**: cron
- **Windows**: Task Scheduler (Aufgabenplanung)

---

## Linux: cron

### Aufruf

```bash
# Alle Jobs ausführen — täglich um 03:00 Uhr:
0 3 * * * /usr/bin/python3 /opt/backup-tool/backup.py run >> /opt/backup-tool/logs/cron.log 2>&1

# Bestimmten Job ausführen — alle 6 Stunden:
0 */6 * * * /usr/bin/python3 /opt/backup-tool/backup.py run --job webserver >> /opt/backup-tool/logs/cron.log 2>&1
```

### Hinweise

- Absolut-Pfade verwenden (cron hat minimalen PATH).
- `>> ... 2>&1`: stdout und stderr in eine Log-Datei umleiten (zusätzlich zum internen Logging).
- Wenn als root laufen soll: In root's crontab (`sudo crontab -e`) oder in `/etc/cron.d/backup-tool`.
- Wenn als normaler User: In User-crontab (`crontab -e`).

### Umgebungsvariablen in cron

Credentials per Umgebungsvariable müssen in cron explizit gesetzt werden:

```cron
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=wJalr...
0 3 * * * /usr/bin/python3 /opt/backup-tool/backup.py run
```

Oder besser: In einem Wrapper-Script, das die Variablen aus einer geschützten Datei lädt:

```bash
#!/bin/bash
source /opt/backup-tool/.env
/usr/bin/python3 /opt/backup-tool/backup.py run
```

Die `.env`-Datei: `chmod 600`, besitzt von root.

---

## Windows: Task Scheduler

### Aufruf

Das Tool stellt ein Hilfs-Kommando bereit, das einen Task-Scheduler-Eintrag erstellt:

```cmd
python backup.py install-scheduler --job webserver --schedule daily --time 03:00
python backup.py install-scheduler --job documents --schedule hourly --interval 6
python backup.py install-scheduler --all --schedule daily --time 03:00
```

### Hintergrund-Implementierung

Das Tool verwendet `schtasks.exe` (in Windows eingebaut, keine externe Abhängigkeit):

```python
import subprocess

def install_windows_task(job_name, schedule_type, time_str=None, interval=None):
    python_path = sys.executable  # aktueller Python-Interpreter
    script_path = os.path.abspath("backup.py")

    task_name = f"BackupTool_{job_name}"
    command = f'"{python_path}" "{script_path}" run --job {job_name}'

    args = [
        "schtasks", "/Create",
        "/TN", task_name,
        "/TR", command,
        "/SC", schedule_type.upper(),  # DAILY, HOURLY
        "/F"  # Force (überschreiben wenn vorhanden)
    ]

    if time_str:
        args.extend(["/ST", time_str])  # z.B. "03:00"
    if interval:
        args.extend(["/RI", str(interval * 60)])  # Intervall in Minuten

    # Als Admin ausführen
    args.extend(["/RL", "HIGHEST"])  # Höchste Privilegien

    subprocess.run(args, check=True)
```

### Unterstützte Schedules

| Parameter | Beschreibung |
|-----------|-------------|
| `--schedule daily --time 03:00` | Täglich um 03:00 |
| `--schedule hourly --interval 6` | Alle 6 Stunden |
| `--schedule weekly --time 02:00 --day MON` | Wöchentlich Montag 02:00 |

### Entfernen eines Tasks

```cmd
python backup.py uninstall-scheduler --job webserver
python backup.py uninstall-scheduler --all
```

Intern: `schtasks /Delete /TN BackupTool_webserver /F`

### Umgebungsvariablen unter Windows

Task Scheduler unterstützt keine direkten Umgebungsvariablen im Task. Lösungen:
1. **System-Umgebungsvariablen** setzen (Systemsteuerung → Erweiterte Systemeinstellungen → Umgebungsvariablen).
2. **Wrapper-Batch-Datei**:
   ```batch
   @echo off
   set AWS_ACCESS_KEY_ID=AKIA...
   set AWS_SECRET_ACCESS_KEY=wJalr...
   python C:\backup-tool\backup.py run
   ```
3. Credentials direkt in der Job-Konfiguration (weniger sicher, aber funktioniert immer).

---

## Installation

### Linux

```bash
# 1. Verzeichnis erstellen
sudo mkdir -p /opt/backup-tool
sudo cp -r backup-tool/* /opt/backup-tool/

# 2. Berechtigungen setzen
sudo chmod 700 /opt/backup-tool/config/
sudo chmod 600 /opt/backup-tool/config/jobs/*.json
sudo chmod 600 /opt/backup-tool/credentials/*

# 3. Log-Verzeichnis
sudo mkdir -p /opt/backup-tool/logs
sudo chmod 755 /opt/backup-tool/logs

# 4. Test
sudo python3 /opt/backup-tool/backup.py validate

# 5. Cron einrichten
sudo crontab -e
# → Zeile hinzufügen (siehe oben)
```

### Windows

```cmd
:: 1. Verzeichnis
mkdir C:\backup-tool
xcopy /E /I backup-tool\* C:\backup-tool\

:: 2. Test
python C:\backup-tool\backup.py validate

:: 3. Task Scheduler einrichten
python C:\backup-tool\backup.py install-scheduler --all --schedule daily --time 03:00
```

### Setup-Hilfskommando

Das Tool bietet ein `setup`-Kommando, das die Ersteinrichtung unterstützt:

```bash
python backup.py setup
```

Dieses Kommando:
1. Prüft Python-Version (≥ 3.12).
2. Prüft ob benötigte Verzeichnisse existieren, erstellt sie bei Bedarf.
3. Erstellt eine Beispiel-`global.json` wenn keine vorhanden.
4. Erstellt eine Beispiel-Job-Datei wenn keine Jobs vorhanden.
5. Prüft Dateiberechtigungen und korrigiert sie (nur Linux, nur als root).
6. Gibt Hinweise zur Scheduler-Einrichtung aus.

---

## Python-Anforderung

- Mindestversion: **Python 3.12**
- Das Tool prüft beim Start die Python-Version und bricht mit klarer Fehlermeldung ab wenn < 3.12:
  ```python
  import sys
  if sys.version_info < (3, 12):
      print("FEHLER: Python 3.12 oder höher erforderlich.", file=sys.stderr)
      sys.exit(1)
  ```
- Kein venv, kein pip, kein Paketmanager. Nur die System-Python-Installation.

---

## Plattform-spezifische Unterschiede

| Aspekt | Linux | Windows |
|--------|-------|---------|
| Standardpfad | `/opt/backup-tool/` | `C:\backup-tool\` |
| Scheduling | cron | Task Scheduler (schtasks) |
| Root/Admin | `sudo python3 backup.py run` | Als Admin CMD/PowerShell |
| Dateiberechtigungen | `chmod 600` prüfbar | ACL-Check (optional, nicht blockierend) |
| Standard-Archivformat | tar.gz | zip |
| Pfad-Trennzeichen | `/` | `\` (intern `pathlib.Path` für Normalisierung) |
| Temp-Verzeichnis | `/tmp` | `%TEMP%` |
| Zeilenumbrüche in Logs | `\n` | `\n` (auch auf Windows, für Konsistenz) |
