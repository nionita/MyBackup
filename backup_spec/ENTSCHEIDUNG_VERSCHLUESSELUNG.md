# Entscheidung: Optionale Backup-Verschlüsselung mit age

## Gewählte Lösung

Das externe [age-Programm](https://github.com/FiloSottile/age) übernimmt die
Verschlüsselung. Python verwendet ausschließlich Standardbibliothek und
`subprocess` ohne Shell. Es werden keine Python-Pakete, Bindings oder venvs
benötigt. Linux und Windows werden durch offizielle age-Binärdateien unterstützt.
Installation ist optional: Nur Jobs mit `encryption.enabled: true` benötigen age.

## Konfiguration und Schlüssel

`credentials/age.json` enthält `recipient` (einen öffentlichen nativen
`age1...`-Empfänger) und optional `executable` (Standard `age` auf PATH).
Job-Felder im `encryption`-Objekt überschreiben die geteilten Werte; `$ENV:`-
Referenzen sind erlaubt. Private age-Identitäten bleiben separat auf dem
Recovery-System. `age-keygen` dient zur Generierung, nicht die Backup-Anwendung.

Bei Rotation wird ein neuer Empfänger eingetragen. Der Empfänger-Hash im
Policy-Fingerprint erzwingt ein neues Backup. Alte private Schlüssel müssen so
lange verfügbar bleiben, wie damit verschlüsselte Backups existieren. Ein
separates, geprüftes Recovery-Backup der privaten Schlüssel ist erforderlich.

## Ablauf und Fehlerverhalten

1. Pro Job age und Empfänger prüfen, auch bei unveränderten Quellen.
2. TAR/ZIP in einem privaten temporären Verzeichnis komprimieren.
3. Archiv einmal mit age verschlüsseln; bestehendes age-Dateiformat verwenden.
4. Klartextarchiv entfernen und dieselbe `.age`-Datei an ausstehende Backends laden.
5. Erfolg je Destination speichern und temporäre Dateien aufräumen.

Fehlendes/beschädigtes age, ungültiger Empfänger, defekte optionale Credentials
oder Verschlüsselungsfehler führen nur beim betroffenen Job zum Fehler. Andere
Jobs laufen weiter. Es gibt keinen Fallback auf Klartext-Upload. Temporäre
Payloads und Diagnosen werden nicht vollständig in Python-Speicher geladen.
Linux-Staging-Verzeichnisse sind owner-only; unter Windows müssen passende
ACLs vorliegen. Temporäres Klartextspeichern ist vorgesehen; Dateilöschung ist
keine sichere Löschung. Äußere Dateinamen, Zeitstempel und Größen bleiben sichtbar.
Retention gilt gemeinsam für alte Klartext- und neue age-Backups des Jobs.

## Restore

```sh
python backup-tool/backup.py decrypt downloaded.tar.gz.age --identity backup-identity.txt --output restored.tar.gz
```

Der Befehl benötigt keine Job-Konfiguration. `--executable PATH` ist optional.
Das gesamte Archiv wird in eine temporäre Datei entschlüsselt und geprüft;
erst danach wird es ohne Überschreiben eines bestehenden Outputs veröffentlicht.
Falsche Schlüssel und beschädigte/abgeschnittene Dateien werden abgelehnt.
Die atomare Veröffentlichung verwendet Hardlinks: Linux-Dateisysteme und Windows
NTFS werden unterstützt; FAT/exFAT als Output-Dateisystem nicht. Danach wird das
Archiv manuell inspiziert und entpackt. Unabhängiger Restore direkt mit age ist
möglich. Vollständige Installation, Beispiele und Einschränkungen: Haupt-README.

## Verworfen bzw. nicht Teil von V1

Keine selbst implementierte Kryptografie und kein eigenes verschlüsseltes
Containerformat. Der frühere OpenSSL-AES-CBC-Vorschlag wird nicht umgesetzt:
es fehlte Authentifizierung, und der geheime Schlüssel wurde als Prozessargument
übergeben. Keine Python-Kryptobibliothek. Kein Passphrase-Modus, keine Plugins,
SSH-Empfänger oder mehreren Empfänger in der Konfiguration. Keine automatische
Schlüsselrotation oder Archivextraktion.
