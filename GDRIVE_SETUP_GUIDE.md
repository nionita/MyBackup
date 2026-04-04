# Google Drive Setup Guide for Backup Tool

This guide explains how to properly connect a Google Drive account to your local Backup Tool using secure Service Accounts.

## 1. Creating a Google Cloud Service Account
Since our script runs hands-free in the background, we cannot use a normal User Login (OAuth Consent Screen). Instead, we use a robot account called a **Service Account**.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new Project or select an existing one.
3. Enable the **Google Drive API**: Open the Menu -> **APIs & Services** -> **Library**, search for "Google Drive API" and click **Enable**.
4. Go to **APIs & Services** -> **Credentials**.
5. Click **+ CREATE CREDENTIALS** -> **Service account**.
6. Give it a name (e.g., `backup-script-bot`) and click **Done**.
7. In the Servce Accounts list, click your new bot account, go to the **Keys** tab -> **Add Key** -> **Create new key**.
8. Select **JSON** and hit **Create**. This will download the credentials payload securely to your workstation.

**Security Warning**: Place this JSON file somewhere secure on your system (e.g., `C:\backup-credentials\service-account.json`) and **never** commit it to version control! 

---

## 2. Preparing Google Drive

Service Accounts start with their own isolated zero-byte drives. To have them upload files into your *personal* Google Drive, you have to share a folder with them!

1. Go to your normal Google Drive as your main user profile.
2. Create a new folder (e.g., `My Server Backups`).
3. Open the JSON file you downloaded in Step 1 and look for the `"client_email"` field. It will look like `backup-script-bot@your-project-id.iam.gserviceaccount.com`.
4. Right-click your `My Server Backups` folder in Google Drive -> **Share**.
5. Paste the robot's `client_email` into the box, give it **Editor** permissions, and click **Share**.

Now, the robot can upload files securely directly into your storage!

### Find your Folder ID
Open the shared folder in your web browser. Look at the URL structure:
`https://drive.google.com/drive/folders/1aBcD_2-eFgH3iJkL4-MnOpQ_5r-StUvW`
The long string at the end (`1aBcD...`) is your **Folder ID**. You will need this for the configuration file.

---

## 3. Configuring the Backup Job

Open or create your `config/jobs/job_...json` document. In the `"backends"` array, add the `google_drive` block with the paths you constructed above.

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
