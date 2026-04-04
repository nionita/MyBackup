# ⚠️ Offene Entscheidung: Lokale Verschlüsselung (für spätere Phase)

## Kontext

Lokale Verschlüsselung der Backups VOR dem Upload, damit die Cloud-Anbieter keinen Zugriff auf die Backup-Inhalte haben. Dieses Feature ist als OPTIONAL eingeplant — nicht für die erste Version.

## Machbarkeit mit Python-Standardbibliothek

Die Python-stdlib enthält **kein AES-Modul**. Die Situation ist ähnlich wie beim RSA-Problem (siehe `ENTSCHEIDUNG_RSA_SIGNIERUNG.md`).

---

## Optionen

### Option 1: AES-Verschlüsselung via OpenSSL-Subprocess

```python
import subprocess

def encrypt_file(input_path: str, output_path: str, key_hex: str):
    """AES-256-CBC Verschlüsselung via openssl."""
    subprocess.run([
        "openssl", "enc", "-aes-256-cbc",
        "-in", input_path,
        "-out", output_path,
        "-K", key_hex,           # 256-bit Key als Hex
        "-iv", iv_hex,           # 128-bit IV als Hex
        "-nosalt"                # Salt separat managen
    ], check=True)
```

**Vorteile:**
- Bewährte AES-Implementierung.
- Performant (nativ, Hardware-AES-Beschleunigung möglich).

**Nachteile:**
- Abhängigkeit von `openssl` (auf Windows nicht Standard — siehe RSA-Entscheidung).
- Temporäre Dateien auf Disk (Klartext → verschlüsselt).

---

### Option 2: Pure-Python AES-Implementierung

Theoretisch möglich, aber:
- AES in reinem Python ist **extrem langsam** (Faktor 100-1000x langsamer als native Implementierung).
- Für Backup-Dateien im GB-Bereich praktisch nicht nutzbar.
- **Nicht empfohlen.**

---

### Option 3: Externe Bibliothek (`cryptography`)

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = AESGCM.generate_key(bit_length=256)
aesgcm = AESGCM(key)
nonce = os.urandom(12)
ciphertext = aesgcm.encrypt(nonce, plaintext, None)
```

**Vorteile:**
- Performant, sicher, gut dokumentiert.
- AES-GCM bietet Authenticated Encryption (Integrität + Vertraulichkeit).

**Nachteile:**
- Externe Abhängigkeit.

---

### Option 4: Externes Verschlüsselungstool (z. B. `gpg`, `age`)

Statt eigene Verschlüsselung zu implementieren, ein externes Tool aufrufen:

```python
# Mit GPG:
subprocess.run(["gpg", "--symmetric", "--cipher-algo", "AES256",
                "--passphrase-fd", "0", "--batch", "-o", output_path, input_path],
               input=passphrase.encode(), check=True)

# Mit age (https://age-encryption.org/):
subprocess.run(["age", "-r", public_key, "-o", output_path, input_path], check=True)
```

**Vorteile:**
- Bewährte, auditierte Tools.
- GPG ist auf vielen Linux-Systemen vorinstalliert.

**Nachteile:**
- Zusätzliche System-Abhängigkeit.
- Auf Windows nicht standardmäßig vorhanden.

---

## Key Management

Unabhängig von der gewählten Verschlüsselungsmethode muss ein Key-Management-Konzept definiert werden:

### Symmetrischer Schlüssel (AES)

- **Key-Generierung:** `secrets.token_bytes(32)` für AES-256.
- **Key-Speicherung:** Separates Key-File, z. B. `/opt/backup-tool/keys/encryption.key`.
  - **Linux:** `chmod 600`, Besitzer = Backup-User.
  - **Windows:** ACL-Schutz.
- **Key in der Job-Konfiguration:**
  ```json
  {
    "encryption": {
      "enabled": true,
      "key_file": "/opt/backup-tool/keys/encryption.key",
      "algorithm": "aes-256-cbc"
    }
  }
  ```

### Key Rotation

**Problem:** Wenn der Key rotiert wird, können alte Backups nicht mehr entschlüsselt werden (es sei denn, der alte Key ist noch verfügbar).

**Lösung: Key-Versionierung**

1. Jeder Key bekommt eine Version (z. B. `v1`, `v2`, ...).
2. Backup-Dateien enthalten die Key-Version im Dateinamen oder in einem Metadaten-Header:
   `webserver_2026-04-04T061800Z_kv1.tar.gz.enc`
3. Alle Key-Versionen werden aufbewahrt:
   ```
   keys/
   ├── encryption_v1.key
   ├── encryption_v2.key  (aktuell)
   └── key_manifest.json  # Welche Version ist aktuell
   ```
4. Zum Entschlüsseln: Key-Version aus Dateiname/Header lesen, passenden Key laden.
5. Rotation:
   ```bash
   python backup.py rotate-key
   ```
   - Generiert neuen Key mit inkrementierter Version.
   - Aktualisiert `key_manifest.json`.
   - Alte Keys werden NICHT gelöscht.
   - Zukünftige Backups nutzen den neuen Key.

**Wichtig:** Alte Keys dürfen nur manuell gelöscht werden, nachdem sichergestellt ist, dass keine Backups mit dieser Key-Version mehr existieren.

### Verschlüsseltes Backup-Format

```
[4 bytes: Magic Number "BKUP"]
[2 bytes: Format-Version]
[2 bytes: Key-Version]
[16 bytes: IV / Nonce]
[Rest: verschlüsselte Daten]
```

Dieses Header-Format erlaubt dem Tool, beim Entschlüsseln automatisch den richtigen Key zu wählen.

---

## Ablauf mit Verschlüsselung

1. Quellverzeichnisse → Archiv erstellen (tar.gz/zip).
2. Archiv mit konfiguriertem Key verschlüsseln → `.enc`-Datei.
3. Verschlüsselte Datei hochladen.
4. Temporäre Dateien (unverschlüsseltes Archiv, verschlüsselte Datei) löschen.

Beim Restore:
1. Verschlüsselte Datei herunterladen.
2. Key-Version aus Header lesen, passenden Key laden.
3. Entschlüsseln → Archiv.
4. Archiv entpacken.

---

## Empfehlung

**Option 1 (OpenSSL-Subprocess)** für Linux-First-Ansatz.

**Oder Option 3 (cryptography-Bibliothek)**, falls die stdlib-Beschränkung für Verschlüsselung gelockert wird — dies wäre die robusteste und sicherste Lösung.

**Option 2 (Pure-Python AES) ist NICHT empfohlen** wegen inakzeptabler Performance.

---

## Entscheidung

> **OFFEN — vor der Implementierung der Verschlüsselungs-Phase entscheiden.**
>
> Diese Datei dem Programmieragenten mitgeben, wenn das Feature implementiert werden soll.
