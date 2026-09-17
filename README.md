# Python Backup-Tool

A cross-platform backup utility written entirely in Python (>= 3.12) using only the standard library. It safely compresses and uploads directories/files directly to cloud storage (currently AWS S3), applying retention policies without any third-party dependencies.

## Setup Requirements

- **Python**: Version 3.12 or newer.
- **Operating Systems**: Windows 10/11, Unix/Linux Distributions.

## AWS S3 Backend Setup

1. **Create an S3 Bucket**: In the AWS Management Console, create a new bucket (e.g., `my-backup-bucket`).
2. **Create an IAM Role** (Recommended for `STS AssumeRole` delegation):
   Create a role with an inline policy allowing access to your bucket:
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
3. **IAM User**: Create an IAM user and generate Access Keys manually. Apply a policy that allows this user to assume the role `sts:AssumeRole`. 
   If you aren't using the AssumeRole strategy, simply assign the S3 permissions directly to the user (Option A).

## Google Drive Backend Setup

For Google Drive integrations via OAuth2 Server-to-Server Service Accounts utilizing our custom RS256 signature algorithm constraints, please refer to the dedicated [GDRIVE_SETUP_GUIDE.md](GDRIVE_SETUP_GUIDE.md) document for a complete step-by-step setup walkthrough.

## Configuring a Backup Job

Jobs are configured in `backup-tool/config/jobs/`. Create a JSON file (e.g., `job_webserver.json`):

```json
{
  "name": "webserver",
  "description": "Daily web files backup",
  "enabled": true,
  "sources": [
    "/var/www/html",
    "/etc/nginx"
  ],
  "exclude_patterns": [
    "*.log",
    "__pycache__"
  ],
  "archive": {
    "format": "tar.gz",
    "compression_level": 6
  },
  "change_detection": {
    "enabled": true
  },
  "backends": [
    {
      "backend_type": "aws_s3",
      "aws_access_key_id": "$ENV:AWS_ACCESS_KEY_ID",
      "aws_secret_access_key": "$ENV:AWS_SECRET_ACCESS_KEY",
      "aws_role_arn": "arn:aws:iam::123456789012:role/BackupRole",
      "aws_region": "eu-central-1",
      "aws_bucket": "my-backup-bucket",
      "aws_prefix": "backups/webserver/",
      "retention_count": 7
    }
  ]
}
```

*Note: For Windows local paths use double backslashes (e.g., `C:\\Users\\...`). You can securely inject credentials from strings via the explicit `$ENV:VARIABLE` format.*

## Running the Backup Manually

Run all configured jobs natively:
```sh
python backup-tool/backup.py run
```

Run a specific job:
```sh
python backup-tool/backup.py run --job webserver
```

Validate JSON Job format schemas structurally:
```sh
python backup-tool/backup.py validate
```

## Changed-source backups

Change detection is enabled by default. Before creating an archive, the tool
hashes the files that would be archived, together with their archive paths and
restorable metadata. If every configured backend already has that source
fingerprint, archive creation and uploads are skipped; retention still runs.

The first run after upgrading always creates a normal backup, then writes
owner-only state under `<config-dir>/state/`. State stores aggregate hashes and
destination identities only, never credentials or file contents. If state is
missing or corrupt, the tool safely creates a fresh backup. A state write
failure makes the job fail after logging that the upload completed.

Set `"change_detection": { "enabled": false }` in a job to retain the former
always-upload behaviour. Use `--force` for a one-off fresh snapshot:

```sh
python backup-tool/backup.py run --job webserver --force
```

## Scheduling the Backup

### Linux (via cron)
Edit your crontab using `crontab -e`:
```bash
# Run daily at 03:00 AM (Ensure Environment variables are populated inside Cron!)
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=wJalr...
0 3 * * * /usr/bin/python3 /opt/backup-tool/backup.py run >> /opt/backup-tool/logs/cron.log 2>&1
```

### Windows (via Task Scheduler)
Ensure you set your environment variables on the machine using Windows GUI System Settings.
You can use the built-in scheduler helper via CMD (run as Administrator):
```cmd
python C:\backup-tool\backup.py install-scheduler --all --schedule daily --time 03:00
```
Alternatively, you can schedule the background task manually through the standard `taskschd.msc` interface.
