# ⚠️ Offene Entscheidung: RSA-Signierung für Google Drive Backend

## Problem

Google Drive Service Account-Authentifizierung erfordert JWT-Signierung mit RS256 (RSA + SHA-256). Die Python-Standardbibliothek enthält **kein RSA-Modul**. Dies ist die einzige Stelle im gesamten Tool, wo RSA benötigt wird.

## Optionen

### Option A: Pure-Python RSA (empfohlen)

**Beschreibung:** RSA PKCS#1 v1.5 Signatur komplett in Python implementieren, nur mit stdlib-Modulen (`int`, `pow`, `hashlib`, `base64`, `struct`).

**Aufwand:** ~100-150 Zeilen Code

**Was implementiert werden muss:**
1. PEM-Datei lesen → Base64-Block extrahieren → Bytes dekodieren.
2. DER/ASN.1 parsen, um die RSA-Parameter `n` (Modulus) und `d` (Private Exponent) zu extrahieren.
   - PKCS#1-Format (`BEGIN RSA PRIVATE KEY`): Direkt die RSA-Struktur.
   - PKCS#8-Format (`BEGIN PRIVATE KEY`): Äußere Hülle parsen, dann RSA-Struktur.
   - Google Service Account JSON liefert typischerweise PKCS#8.
3. PKCS#1 v1.5 Signatur-Padding zusammenbauen:
   - DigestInfo-Struktur für SHA-256.
   - Padding: `0x00 0x01 [0xFF...] 0x00 [DigestInfo + Hash]`.
4. Signatur berechnen: `pow(padded_integer, d, n)`.
5. Ergebnis als Bytes zurückgeben.

**Vorteile:**
- 100% stdlib, keine Abhängigkeit.
- Python `pow(base, exp, mod)` ist hochperformant (nutzt intern optimierte Algorithmen).
- RSA-Signierung (nicht Entschlüsselung) ist die einfachste RSA-Operation.

**Nachteile:**
- Eigene Kryptografie-Implementierung → sollte gründlich getestet werden.
- ASN.1-Parsing ist fehleranfällig (aber für diesen konkreten Fall überschaubar).

**Risiko-Minderung:**
- Test-Vektor: JWT mit bekanntem Private Key signieren, gegen bekannte Google-Library-Signatur vergleichen.
- Der Code signiert nur (kein Entschlüsseln, kein Key-Generieren), also minimale Angriffsfläche.

---

### Option B: OpenSSL als Subprocess

**Beschreibung:** JWT-Payload als Datei/Pipe an `openssl dgst -sha256 -sign key.pem` übergeben.

```python
import subprocess
import tempfile

def rsa_sign_openssl(data: bytes, key_path: str) -> bytes:
    result = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", key_path],
        input=data,
        capture_output=True,
        check=True
    )
    return result.stdout
```

**Vorteile:**
- Nutzt bewährte, auditierte Kryptografie.
- Wenige Zeilen Code.

**Nachteile:**
- Abhängigkeit von `openssl` Binary.
  - **Linux:** Fast immer vorhanden (`/usr/bin/openssl`).
  - **Windows:** NICHT standardmäßig installiert. Muss separat installiert werden (z. B. mit Git for Windows, Chocolatey, oder manuell von https://slproweb.com/products/Win32OpenSSL.html).
- Subprocess-Aufrufe sind langsamer als in-process (vernachlässigbar bei Backup-Frequenz).
- Private Key muss als Datei vorliegen (liegt beim Service Account sowieso vor).

**Windows-Workaround:** Das Tool könnte beim Setup prüfen ob `openssl` verfügbar ist und entsprechend warnen.

---

### Option C: Minimale externe Bibliothek

**Beschreibung:** Eine einzelne externe Bibliothek einmal systemweit installieren:

```bash
pip install PyJWT cryptography
```

**Vorteile:**
- Bewährte, auditierte Implementierung.
- Einfachste Codierung.

**Nachteile:**
- Verletzt das "keine externen Bibliotheken"-Constraint.
- `cryptography`-Paket hat eigene C-Abhängigkeiten (OpenSSL-Bindings), Build auf manchen Systemen problematisch.
- Erfordert pip und ggf. Build-Tools.

---

### Option D: Hybrid-Ansatz

**Beschreibung:** 
1. Versuche zuerst, `openssl` als Subprocess zu nutzen.
2. Wenn `openssl` nicht verfügbar: Fallback auf Pure-Python-RSA.

**Vorteile:** Bestmögliche Sicherheit wo verfügbar, trotzdem überall funktional.

**Nachteile:** Zwei Code-Pfade die getestet/gewartet werden müssen.

---

## Empfehlung

**Option A (Pure-Python RSA)** für maximale Portabilität und Konsistenz mit dem stdlib-Constraint.

**Oder Option D (Hybrid)** wenn die zusätzliche Komplexität akzeptabel ist.

---

## Entscheidung

> **OFFEN — vor der Implementierung entscheiden.**
>
> Diese Datei dem Programmieragenten mitgeben und dort die gewählte Option als Constraint angeben.
