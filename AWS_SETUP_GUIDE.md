# AWS Setup Guide for Backup Tool

This guide walks you through setting up the AWS side of the Backup Tool. AWS Identity and Access Management (IAM) has a very complex interface, so this document tracks the specific quirks and click-paths needed to get it right.

## Architecture Overview

For maximum security and easy management, we use a **Role-based architecture**:
1. You create **one Backup Role** that holds the S3 bucket permissions.
2. For each physical machine running the backup, you create **one IAM User**.
3. You give each IAM User permission to "assume" (borrow) the Backup Role. 

If a machine is compromised, you delete its user. The rest of the machines remain unaffected.

---

## 1. Creating the S3 Backup Role

When creating the role, we tell AWS that users from our own AWS account are allowed to assume it.

### Step 1: Select Trusted Entity
1. Go to the **IAM Console** -> **Rollen** (Roles) -> **Rolle erstellen** (Create role).
2. Under "Typ vertrauenswürdiger Entitäten" (Trusted entity type), select **AWS-Konto** (AWS Account).
3. Leave "Dieses Konto" (This account) selected (it will automatically fill in your Account ID).
4. Click **Weiter** (Next).

### Step 2: Skip Permissions Profile 
*⚠️ **UI Quirk Warning**: AWS does not let you create custom Inline Policies during the creation wizard.*

1. You will see a giant list of pre-made AWS policies ("Berechtigungen hinzufügen" / Add permissions).
2. **Do not check any boxes**. Scroll to the bottom and click **Weiter** (Next).

### Step 3: Name and Review
1. Name the role something recognizable, like `MyBackupToolRole`.
2. Click **Rolle erstellen** (Create role).

### Step 4: Add the S3 Inline Policy
Now that the role exists, we can inject our custom S3 rules.

1. Back on the Roles list, search for `MyBackupToolRole` and click it.
2. Go to the **Berechtigungen** (Permissions) tab.
3. Click the **Berechtigungen hinzufügen** (Add permissions) button on the right edge, and pick **Inline-Richtlinie erstellen** (Create inline policy).
4. Click the **JSON** tab in the policy editor.
5. Paste the following JSON (replace `my-backup-bucket` with your actual bucket name):

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
6. Click **Richtlinie überprüfen** (Review policy), name it `S3BackupAccess`, and save. 

🚨 **Note your Role ARN**: At the top of your Role summary page, copy the **ARN** (e.g., `arn:aws:iam::123456789012:role/MyBackupToolRole`). You will need this for your backup clients!

---

## 2. Creating an IAM User for the Backup Machine

Now we create the technical user that the backup script uses locally on the machine.

1. Go to **IAM Console** -> **Benutzer** (Users) -> **Benutzer hinzufügen** (Add users).
2. Name it something like `BackupMachine-Server1`. 
3. *Do not* give it AWS Management Console access. 
4. Click **Weiter** (Next).
5. In the permissions section, select **Richtlinien direkt anfügen** (Attach policies directly).
6. Click **Richtlinie erstellen** (Create policy). *(This will open a new tab)*.
7. Go to the **JSON** tab and paste the following policy, replacing the `Resource` with your Role ARN from earlier:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": "arn:aws:iam::YOUR_ACCOUNT_ID:role/MyBackupToolRole"
        }
    ]
}
```
8. Save this policy as `AssumeBackupRolePolicy`.
9. Go back to your Add User tab, hit refresh, find `AssumeBackupRolePolicy`, check its box, and finish creating the user.

### Final Step: Get Access Keys
1. Click on your newly created `BackupMachine-Server1` user.
2. Go to the **Sicherheitsanmeldeinformationen** (Security credentials) tab.
3. Scroll to **Zugriffsschlüssel** (Access keys) and click **Zugriffsschlüssel erstellen** (Create access key).
4. Choose **Befehlszeilenschnittstelle (CLI)** (Command Line Interface).
5. Download or copy the **Access Key** and **Secret Access Key**. 

## 3. Configure the Backup Tool
Because the tool uses a decentralized credentials architecture, your keys don't clutter up your job backups. 

Instead, locally navigate to your configurations directory and create `<config-dir>/credentials/aws_s3.json`. Paste the keys you generated as follows:

```json
{
  "aws_access_key_id": "YOUR_ACCESS_KEY_ID_HERE",
  "aws_secret_access_key": "YOUR_SECRET_ACCESS_KEY_HERE",
  "aws_region": "eu-central-1",
  "aws_bucket": "my-backup-bucket",
  "aws_assume_role_arn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/MyBackupToolRole"
}
```
*(You can also use the variable `"$ENV:AWS_ACCESS_KEY_ID"` if you prefer keeping these strings directly in your machine's environment variables instead!)*

Then, in any job where you want AWS S3 backing, you simply reference the generic backend block:
```json
  "backends": [
    {
      "backend_type": "aws_s3",
      "retention_count": 5
    }
  ]
```
