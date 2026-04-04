# Google Drive Setup Guide for Backup Tool

This guide explains how to properly connect a Google Drive account to your local Backup Tool using secure Service Accounts.

There are currently two ways to connect your Google Drive to the script depending entirely on if you are an Enterprise User navigating Shared Drives, or a Consumer User mapping personal drives.

## Option A: OAuth Refresh Tokens (For standard Consumer `@gmail.com` accounts)
Google recently locked down Service Account capabilities—they currently have exactly 0 bytes of storage natively! If you try to upload a file to a regular Google Drive folder via a robot, Google denies the upload citing `storageQuotaExceeded`. 

To bypass this without creating a Google Workspace, you must authenticate the script to run as **you**. This allows it to upload files natively against your own 15GB+ storage quota. 

**Step 1: Get an OAuth Client ID**
1. Go to your [Google Cloud Console](https://console.cloud.google.com/) and ensure the **Google Drive API** is enabled.
2. Go to **APIs & Services** -> **OAuth consent screen** (OAuth-Zustimmungsbildschirm). Select **External** and fill in required fake details. 
3. **CRITICAL STEP:** While still on the OAuth Consent Screen, you must either click **Publish App** (App veröffentlichen) to remove testing limits, OR scroll down to **Test users** and manually add your specific `@gmail.com` email address. If you do not do this, Google will block your login attempt!
4. Go to **APIs & Services** -> **Credentials**.
5. Click **+ CREATE CREDENTIALS** -> **OAuth client ID**.
6. Select Application Type: **Desktop app**. Name it "Backup-Tool", click Create.
7. A window will pop up containing your `Client ID` and `Client Secret`. Keep this open!

**Step 2: Generate the Refresh Token**
We have built a native Auto-Authenticator into the CLI that will automatically handle the Google OAuth handshakes for you!
Simply execute:
```powershell
python backup-tool/backup.py setup-gdrive
```
1. It will prompt you for the `Client ID` and `Client Secret` you just generated.
2. It will spin up a local web server and launch your browser.
3. Once you click "Allow", it physically catches the redirect, generates the token natively, and writes everything centrally to `<config-dir>\credentials\google_drive.json`.

**Step 3: Define your Backup Job**
Because your credentials are now stored centrally, your `jobs/job_....json` mapping becomes beautifully clean! You simply reference the backend type and define your unique folder:

```json
{
  "name": "gdrive_test",
  "enabled": true,
  "sources": [ "/var/www" ],
  "archive": { "format": "tar.gz" },
  "backends": [
    {
      "backend_type": "google_drive",
      "gd_folder_id": "YOUR_FOLDER_ID_STRING",
      "retention_count": 5
    }
  ]
}
```

---

## Option B: Service Accounts (For Enterprise Workspace / GSuite accounts)
If you operate Google environments where "Shared Drives" are active, or possess Domain-Wide Delegation, setting up Service Accounts allows completely invisible headless validation using RSA!

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API**.
3. Go to **APIs & Services** -> **Credentials**.
4. Click **+ CREATE CREDENTIALS** -> **Service account**.
5. Once created, go to the **Keys** tab -> **Add Key** -> **Create new key** -> **JSON**. 
6. Download the JSON credential file to your system (e.g. `C:\backup-credentials\service-account.json`).
7. Share your target Drive folder natively assigning the JSON's `client_email` string to Editor privileges.

Open your `config/jobs/...json` block and define it utilizing the bot identity:
```json
{
  "name": "gdrive_test",
  "enabled": true,
  "sources": [ "/var/www" ],
  "archive": { "format": "tar.gz", "compression_level": 6 },
  "backends": [
    {
      "backend_type": "google_drive",
      "gd_service_account_file": "C:\\backup-credentials\\service-account.json",
      "gd_folder_id": "YOUR_FOLDER_ID_STRING",
      "retention_count": 5,
      "gd_force_pure_python_rsa": false
    }
  ]
}
```
If you ever wish to rigorously bypass OpenSSL mathematically inside your test environments to verify that standard Python handles hashing correctly natively, you can swap `"gd_force_pure_python_rsa": true`.
