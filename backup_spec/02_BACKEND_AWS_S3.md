# Backend-Spezifikation: AWS S3

## Überblick

Upload/Download/List/Delete von Backup-Dateien in einen AWS S3 Bucket. Ausschließlich per REST API (kein `boto3`, kein `awscli`). Authentifizierung über kurzlebige Credentials (STS) oder IAM User Access Keys.

---

## Authentifizierung

### Credential-Typen

**Option A: IAM User mit Access Key + Secret Key (einfacher, weniger sicher)**
- In der Job-Konfiguration: `aws_access_key_id` und `aws_secret_access_key`.
- Keys können manuell rotiert werden.
- Gültigkeit: unbegrenzt (bis manuell rotiert).

**Option B: IAM User Access Key → STS AssumeRole → temporäre Credentials (empfohlen)**
- In der Konfiguration: `aws_access_key_id`, `aws_secret_access_key`, `aws_role_arn`.
- Das Tool ruft per REST API `STS AssumeRole` auf und bekommt temporäre Credentials (Access Key, Secret Key, Session Token).
- Gültigkeit: 1–12 Stunden (konfigurierbar via `aws_session_duration_seconds`, Standard: 3600).
- Vorteil: Der IAM User braucht nur `sts:AssumeRole`-Permission, alle S3-Rechte liegen auf der Rolle.

### Empfehlung

Option B ist die empfohlene Variante wegen besserer Sicherheit (temporäre Tokens, minimale IAM-User-Rechte). Option A soll trotzdem als Fallback unterstützt werden.

### Credential-Speicherung

- Credentials stehen in der Backend-spezifischen Konfiguration innerhalb der Job-Datei (siehe `04_JOB_KONFIGURATION.md`).
- **Alternativ**: Credentials können auch über Umgebungsvariablen (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ROLE_ARN`) referenziert werden. In der Konfiguration: `"aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID"`. Das Tool erkennt den `$ENV:`-Präfix und liest den Wert aus der Umgebung.
- Dateiberechtigungen: Die Job-Konfigurationsdateien müssen auf Linux `chmod 600` haben (nur owner lesbar). Das Tool prüft das beim Start und warnt, wenn die Berechtigungen zu offen sind.

---

## AWS Signature Version 4

Alle S3 REST-API-Aufrufe müssen mit AWS Signature Version 4 signiert werden. Das muss komplett selbst implementiert werden (kein SDK).

### Algorithmus (Implementierungsanweisung)

Die Signierung folgt dem AWS-Dokumentierten Prozess:

1. **Canonical Request erstellen:**
   ```
   HTTPRequestMethod + '\n' +
   CanonicalURI + '\n' +
   CanonicalQueryString + '\n' +
   CanonicalHeaders + '\n' +
   SignedHeaders + '\n' +
   HexEncode(Hash(RequestPayload))
   ```

2. **String to Sign erstellen:**
   ```
   Algorithm + '\n' +
   RequestDateTime + '\n' +
   CredentialScope + '\n' +
   HexEncode(Hash(CanonicalRequest))
   ```
   - Algorithm: `AWS4-HMAC-SHA256`
   - CredentialScope: `{date}/{region}/s3/aws4_request`

3. **Signing Key berechnen:**
   ```python
   def get_signature_key(key, date_stamp, region, service):
       k_date = hmac_sha256(("AWS4" + key).encode(), date_stamp)
       k_region = hmac_sha256(k_date, region)
       k_service = hmac_sha256(k_region, service)
       k_signing = hmac_sha256(k_service, "aws4_request")
       return k_signing
   ```

4. **Signatur berechnen:**
   ```python
   signature = hmac_sha256(signing_key, string_to_sign).hex()
   ```

5. **Authorization Header:**
   ```
   Authorization: AWS4-HMAC-SHA256
     Credential={access_key}/{credential_scope},
     SignedHeaders={signed_headers},
     Signature={signature}
   ```

### Benötigte stdlib-Module
- `hmac` — HMAC-SHA256
- `hashlib` — SHA256
- `datetime` — Timestamps
- `urllib.parse` — URL-Encoding
- `urllib.request` — HTTP-Requests

### STS AssumeRole (Option B)

REST-API-Aufruf an `https://sts.amazonaws.com/` (oder regionaler Endpoint):

```
POST / HTTP/1.1
Host: sts.amazonaws.com
Content-Type: application/x-www-form-urlencoded

Action=AssumeRole
&RoleArn={role_arn}
&RoleSessionName=backup-tool-{timestamp}
&DurationSeconds={duration}
&Version=2011-06-15
```

- Dieser Aufruf selbst muss ebenfalls mit SigV4 signiert werden (Service: `sts`, Region: `us-east-1` oder konfiguriert).
- Antwort: XML mit `AccessKeyId`, `SecretAccessKey`, `SessionToken`, `Expiration`.
- Das Tool muss die XML-Antwort parsen (mit `xml.etree.ElementTree`, stdlib).
- Bei Verwendung von Session Tokens: Header `X-Amz-Security-Token` bei jedem S3-Aufruf mitschicken.

---

## S3 REST API Operationen

### Upload (PUT Object)

```
PUT /{key} HTTP/1.1
Host: {bucket}.s3.{region}.amazonaws.com
Content-Length: {size}
Content-Type: application/octet-stream
x-amz-content-sha256: {sha256_hex_of_body}
x-amz-date: {iso8601_timestamp}
Authorization: {sigv4_header}
[X-Amz-Security-Token: {session_token}]  # nur bei STS
```

- Für Dateien > 100 MB: Multipart Upload verwenden.
- Multipart Upload:
  1. `POST /{key}?uploads` → Bekommt `UploadId` (XML-Antwort parsen).
  2. `PUT /{key}?partNumber={n}&uploadId={id}` für jeden Teil (mindestens 5 MB pro Teil, letzter Teil kann kleiner sein).
  3. `POST /{key}?uploadId={id}` mit XML-Body der Part-ETags → Abschluss.
  4. Bei Fehler: `DELETE /{key}?uploadId={id}` → Abbruch (Teile aufräumen).
- Part-Größe: Konfigurierbar, Standard 50 MB.
- Empfehlung: Ab 100 MB Dateigröße automatisch auf Multipart umschalten.

### Auflisten (List Objects)

```
GET /?prefix={job_name}/&list-type=2 HTTP/1.1
Host: {bucket}.s3.{region}.amazonaws.com
```

- Antwort: XML mit `<Contents><Key>`, `<LastModified>`, `<Size>`.
- Pagination: Wenn `<IsTruncated>true</IsTruncated>`, dann `continuation-token` aus `<NextContinuationToken>` verwenden.

### Löschen (Delete Object)

```
DELETE /{key} HTTP/1.1
Host: {bucket}.s3.{region}.amazonaws.com
```

### Download (GET Object)

```
GET /{key} HTTP/1.1
Host: {bucket}.s3.{region}.amazonaws.com
```

- Streaming-Download: In Chunks lesen und auf Disk schreiben (`shutil.copyfileobj` oder manuell in 8 KB Blöcken).

---

## Konfigurationsfelder (Backend-spezifisch im Job)

```json
{
  "backend_type": "aws_s3",
  "aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID",
  "aws_secret_access_key": "$ENV:AWS_SECRET_ACCESS_KEY",
  "aws_role_arn": "arn:aws:iam::123456789012:role/BackupRole",
  "aws_session_duration_seconds": 3600,
  "aws_region": "eu-central-1",
  "aws_bucket": "my-backup-bucket",
  "aws_prefix": "backups/",
  "multipart_threshold_mb": 100,
  "multipart_chunk_size_mb": 50
}
```

- `aws_role_arn`: Optional. Wenn gesetzt → STS AssumeRole. Wenn nicht → direkte Credentials.
- `aws_prefix`: Ordner-Präfix im Bucket. Backups landen z. B. unter `backups/webserver/webserver_2026-04-04T061800Z.tar.gz`.

---

## Fehlerbehandlung

- HTTP 403 Forbidden: Credential-Problem → klar loggen ("Zugriff verweigert. IAM-Rechte prüfen.").
- HTTP 404 Not Found: Bucket oder Key existiert nicht.
- HTTP 409 Conflict: Bei Multipart Upload → Abbruch/Retry.
- HTTP 5xx: Transienter Fehler → Retry (siehe Hauptspezifikation).
- STS-Fehler: Klare Meldung ("AssumeRole fehlgeschlagen. Role ARN und Rechte prüfen.").
- XML-Parse-Fehler: Unerwartete Antwort → vollständige Antwort loggen (DEBUG-Level).

---

## AWS-Seite: Einrichtung (Empfehlung für Benutzer-Dokumentation)

1. S3 Bucket erstellen (Versioning optional, kein Public Access).
2. IAM Role erstellen mit Policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "s3:PutObject",
         "s3:GetObject",
         "s3:ListBucket",
         "s3:DeleteObject"
       ],
       "Resource": [
         "arn:aws:s3:::my-backup-bucket",
         "arn:aws:s3:::my-backup-bucket/*"
       ]
     }]
   }
   ```
3. IAM User erstellen mit nur `sts:AssumeRole`-Berechtigung auf die obige Rolle.
4. Access Key für den IAM User generieren.
5. Trust Policy der Rolle so konfigurieren, dass der IAM User die Rolle annehmen darf.

---

## Hinweise für den Programmieragenten

- AWS SigV4 ist der komplexeste Teil. Es gibt ein offizielles Referenz-Beispiel von AWS in Python: https://docs.aws.amazon.com/general/latest/gr/sigv4-signed-request-examples.html — dieses als Vorlage verwenden.
- Alle Timestamps in UTC.
- `x-amz-content-sha256` Header ist bei S3 Pflicht (anders als bei anderen AWS Services).
- `Host`-Header muss exakt `{bucket}.s3.{region}.amazonaws.com` sein (Virtual-hosted-style).
- Für Regionen außerhalb `us-east-1`: Den regionalen Endpoint verwenden.
