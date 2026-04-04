# Backend-Spezifikation: Google Drive

## Überblick

Upload/Download/List/Delete von Backup-Dateien in Google Drive. Ausschließlich per REST API (keine `google-api-python-client`, kein `google-auth`). Authentifizierung über Google Service Account.

---

## Authentifizierung

### Ansatz: Service Account mit JWT → Access Token

Google APIs akzeptieren OAuth2 Access Tokens. Ein Service Account generiert selbst einen JWT, signiert ihn mit seinem privaten Schlüssel, tauscht ihn gegen ein kurzlebiges Access Token (1 Stunde gültig) ein.

### Ablauf

1. **Service Account JSON-Datei** enthält: `client_email`, `private_key` (RSA PEM), `token_uri`.
2. **JWT erstellen** mit Header `{"alg": "RS256", "typ": "JWT"}` und Payload:
   ```json
   {
     "iss": "{client_email}",
     "scope": "https://www.googleapis.com/auth/drive.file",
     "aud": "https://oauth2.googleapis.com/token",
     "iat": {current_unix_timestamp},
     "exp": {current_unix_timestamp + 3600}
   }
   ```
3. **JWT signieren** mit RS256 (RSA + SHA-256) unter Verwendung des Private Keys.
4. **Token-Tausch** per POST:
   ```
   POST https://oauth2.googleapis.com/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
   &assertion={signed_jwt}
   ```
5. **Antwort**: `{"access_token": "ya29.xxx", "token_type": "Bearer", "expires_in": 3600}`
6. **Token verwenden**: `Authorization: Bearer ya29.xxx` bei allen API-Aufrufen.
7. **Token-Caching**: Token zwischenspeichern und erst erneuern, wenn die Gültigkeit < 5 Minuten beträgt.

---

## ⚠️ Kritisches Problem: RSA-Signierung ohne externe Bibliothek

Python-Standardbibliothek enthält **kein RSA-Modul**. Für die JWT-Signierung mit RS256 wird RSA PKCS#1 v1.5 Signatur benötigt. Es gibt folgende Lösungen:

### Lösung 1: Pure-Python RSA-Implementierung (empfohlen für stdlib-Constraint)

Eine minimale RSA-PKCS1v15-Signatur in reinem Python implementieren:
- Private Key aus PEM parsen (Base64 dekodieren, ASN.1/DER-Struktur manuell parsen).
- RSA-Signatur berechnen: `signature = pow(padded_hash, d, n)` wobei `d` und `n` aus dem privaten Schlüssel kommen.
- Die mathematischen Operationen (modulare Exponentiation) sind in Python mit `int` und `pow(base, exp, mod)` performant genug, da Python beliebig große Ganzzahlen nativ unterstützt.
- Aufwand: ca. 100-150 Zeilen Code für PEM-Parsing + PKCS1v15-Padding + Signatur.
- Vorteil: Bleibt 100% stdlib.
- Nachteil: Eigene Kryptografie-Implementierung (Security-Review empfohlen).

### Lösung 2: Systemweites OpenSSL als Subprocess

```python
import subprocess
# JWT-Header.Payload in eine Datei schreiben, dann:
result = subprocess.run(
    ["openssl", "dgst", "-sha256", "-sign", "private_key.pem"],
    input=signing_input.encode(),
    capture_output=True
)
signature = result.stdout
```
- Vorteil: Nutzt bewährte Kryptografie-Library.
- Nachteil: Abhängigkeit von `openssl` auf dem System (auf Linux immer vorhanden, auf Windows nicht immer installiert).

### Lösung 3: Minimale externe Abhängigkeit akzeptieren

Falls die reine-stdlib-Anforderung für diesen einen Fall gelockert wird:
- `PyJWT` + `cryptography` installieren (z. B. als einmalige System-Installation).
- Oder nur `cryptography` für RSA-Operationen.

### Empfehlung

**Lösung 1** (Pure-Python RSA) ist konsistent mit dem stdlib-Constraint. Die Implementierung ist für RS256-Signierung (kein Entschlüsseln nötig) überschaubar. Der Programmieragent soll bei der Implementierung darauf achten, dass:
- Die PEM-Datei korrekt geparst wird (Base64 zwischen `-----BEGIN RSA PRIVATE KEY-----` / `-----END ...` Markern).
- DER/ASN.1-Parsing nur die benötigten Felder extrahiert (n, d für PKCS#1-Format bzw. n, d, e für PKCS#8-Format).
- PKCS#1 v1.5 Padding korrekt implementiert wird (DigestInfo für SHA-256).

**Alternativ Lösung 2**, falls die Zielmaschinen OpenSSL installiert haben.

→ **Entscheidung wird in `ENTSCHEIDUNG_RSA_SIGNIERUNG.md` dokumentiert.**

---

## Google Drive REST API Operationen

Alle Aufrufe an `https://www.googleapis.com/drive/v3/` bzw. `https://www.googleapis.com/upload/drive/v3/`.

### Upload (Resumable Upload empfohlen)

**Schritt 1: Upload initiieren**
```
POST /upload/drive/v3/files?uploadType=resumable HTTP/1.1
Host: www.googleapis.com
Authorization: Bearer {access_token}
Content-Type: application/json; charset=UTF-8

{
  "name": "webserver_2026-04-04T061800Z.tar.gz",
  "parents": ["{folder_id}"]
}
```
Antwort enthält Header `Location: {resumable_upload_uri}`.

**Schritt 2: Daten hochladen**
```
PUT {resumable_upload_uri} HTTP/1.1
Content-Length: {file_size}
Content-Type: application/octet-stream

{file_bytes}
```

- Für große Dateien: In Chunks senden (z. B. 50 MB). Jeder Chunk mit `Content-Range: bytes {start}-{end}/{total}`.
- Vorteile: Unterstützt Fortsetzen nach Abbruch.

### Auflisten (Files List)

```
GET /drive/v3/files?q='{folder_id}'+in+parents+and+name+contains+'{job_name}'&fields=files(id,name,createdTime,size)&orderBy=createdTime HTTP/1.1
Host: www.googleapis.com
Authorization: Bearer {access_token}
```

- Pagination: `pageToken` in der Antwort verwenden.
- `fields`-Parameter nutzen, um nur benötigte Felder abzurufen (Bandbreite sparen).

### Löschen (Delete File)

```
DELETE /drive/v3/files/{file_id} HTTP/1.1
Host: www.googleapis.com
Authorization: Bearer {access_token}
```

### Download (Get File)

```
GET /drive/v3/files/{file_id}?alt=media HTTP/1.1
Host: www.googleapis.com
Authorization: Bearer {access_token}
```

- Streaming: Antwort in Chunks lesen und auf Disk schreiben.

---

## Konfigurationsfelder (Backend-spezifisch im Job)

```json
{
  "backend_type": "google_drive",
  "gd_service_account_json": "/opt/backup-tool/credentials/gd_service_account.json",
  "gd_folder_id": "1AbC_dEfGhIjKlMnOpQrStUvWxYz",
  "gd_upload_chunk_size_mb": 50
}
```

- `gd_service_account_json`: Pfad zur Service-Account-JSON-Datei (von Google Cloud Console heruntergeladen).
  - Alternativ: `"$ENV:GD_SERVICE_ACCOUNT_JSON"` für Pfad aus Umgebungsvariable.
- `gd_folder_id`: Die Google Drive Folder-ID, in die Backups hochgeladen werden.
  - Der Service Account muss als Editor auf diesen Ordner berechtigt sein (Ordner mit dem Service Account teilen).
- `gd_upload_chunk_size_mb`: Chunk-Größe für Resumable Upload, Standard 50 MB.

### Sicherheitshinweis

Die Service-Account-JSON-Datei enthält den privaten Schlüssel. Diese Datei muss:
- Auf Linux: `chmod 600` (nur owner lesbar).
- Auf Windows: ACL so setzen, dass nur der ausführende Benutzer lesen kann.
- Das Tool prüft Dateiberechtigungen beim Laden und warnt bei zu offenen Berechtigungen.

---

## Fehlerbehandlung

- HTTP 401 Unauthorized: Token abgelaufen oder ungültig → Token neu generieren und Retry.
- HTTP 403 Forbidden: Keine Berechtigung auf den Ordner → klar loggen.
- HTTP 404 Not Found: Datei/Ordner existiert nicht.
- HTTP 429 Too Many Requests: Rate Limit → Backoff (Retry-After Header beachten).
- HTTP 5xx: Transient → Retry.
- JSON-Parse-Fehler: Unerwartete Antwort loggen.

---

## Google-Seite: Einrichtung (Empfehlung für Benutzer-Dokumentation)

1. Google Cloud Console → Projekt erstellen (oder existierendes verwenden).
2. Google Drive API aktivieren.
3. Service Account erstellen:
   - IAM & Admin → Service Accounts → Erstellen.
   - Name: z. B. `backup-tool`.
   - Keine besonderen Rollen nötig (Zugriff wird über Drive-Freigabe geregelt).
4. Key erstellen: Auf den Service Account klicken → Keys → Add Key → JSON → Herunterladen.
5. In Google Drive: Zielordner erstellen → Rechtsklick → Teilen → Service-Account-E-Mail (`backup-tool@project.iam.gserviceaccount.com`) als Editor hinzufügen.
6. Die Folder-ID aus der URL kopieren (z. B. `https://drive.google.com/drive/folders/1AbC_dEfGhIjKlMnOpQrStUvWxYz` → `1AbC_dEfGhIjKlMnOpQrStUvWxYz`).

---

## Token-Lebenszyklus

- Access Token: 1 Stunde gültig.
- Kein Refresh Token nötig (Service Account generiert bei Bedarf ein neues JWT).
- Empfehlung: Token in-memory cachen, 5 Minuten vor Ablauf automatisch erneuern.
- Rotation des Service-Account-Keys: In der Google Cloud Console alten Key löschen, neuen erstellen, JSON-Datei aktualisieren. Das Tool muss dafür nicht geändert werden.
