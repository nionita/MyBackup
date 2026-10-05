import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tarfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import backup
from core import change_detection, config_loader, encryption, job_runner


RECIPIENT = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"
OTHER_RECIPIENT = "age1lggyhqrw2nlhcxprm67z43rta597azn8gknawjehu9d9dl0jq3yqqvfafg"


class TestEncryption(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = os.path.join(self.temp.name, "source.txt")
        with open(self.source, "wb") as stream:
            stream.write(b"source data")
        self.archive = os.path.join(self.temp.name, "backup.tar.gz")
        self.state_dir = os.path.join(self.temp.name, "state")
        self.job = {
            "name": "encrypted", "sources": [self.source],
            "archive": {"format": "tar.gz"},
            "encryption": {"enabled": True},
            "backends": [{"backend_type": "aws_s3", "retention_count": 2}],
        }
        self.creds = {"age": {"recipient": RECIPIENT}}

    def fake_age(self, args, **kwargs):
        stdout = kwargs["stdout"]
        if stdout != subprocess.DEVNULL:
            stdout.write(b"age-encryption.org/v1\nENCRYPTED")
        return subprocess.CompletedProcess(args, 0)

    def make_archive(self, **kwargs):
        with open(self.archive, "wb") as stream:
            stream.write(b"plaintext archive")
        return self.archive

    def test_credentials_precedence_and_preflight(self):
        self.job["encryption"].update(recipient=OTHER_RECIPIENT, executable="my-age")
        with patch.object(encryption.shutil, "which", return_value="/tools/age") as which, \
             patch.object(encryption.subprocess, "run", side_effect=self.fake_age) as run:
            settings = encryption.prepare(self.job, self.creds)
        which.assert_called_once_with("my-age")
        self.assertEqual(settings["recipient"], OTHER_RECIPIENT)
        self.assertIn(OTHER_RECIPIENT, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_missing_or_broken_executable_prevents_all_backup_operations(self):
        for failure in ("missing", "broken", "timeout", "invalid-checksum"):
            with self.subTest(failure=failure), \
                 patch.object(encryption.shutil, "which", return_value=None if failure == "missing" else "/tools/age"), \
                 patch.object(encryption.subprocess, "run") as run, \
                 patch.object(job_runner.archiver, "create_archive") as create, \
                 patch.object(job_runner, "instantiate_backend") as backend, \
                 patch.object(change_detection, "calculate_source_fingerprint") as fingerprint:
                if failure == "broken":
                    run.side_effect = OSError("cannot execute")
                elif failure == "timeout":
                    run.side_effect = subprocess.TimeoutExpired("age", 30)
                else:
                    run.return_value = subprocess.CompletedProcess([], 1)
                self.assertFalse(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
                create.assert_not_called()
                backend.assert_not_called()
                fingerprint.assert_not_called()

    def test_invalid_recipient_and_configuration(self):
        for recipient in (None, "", "ssh-ed25519 AAAA", "age1bad", [RECIPIENT]):
            with self.subTest(recipient=recipient), self.assertRaises(encryption.EncryptionError):
                encryption.prepare(self.job, {"age": {"recipient": recipient}})
        for config in ([], {"enabled": "true"}, {"enabled": True, "executable": 3}, {"recipient": ""}):
            job = copy.deepcopy(self.job)
            job["encryption"] = config
            with self.subTest(config=config), self.assertRaises(config_loader.ConfigError):
                config_loader.validate_job_config("encrypted", job)

    def test_bad_optional_credentials_do_not_break_unencrypted_or_overridden_jobs(self):
        directory = os.path.join(self.temp.name, "credentials")
        os.mkdir(directory)
        for content in ("{", '[]', '{"recipient":"$ENV:MYBACKUP_MISSING_TEST_VARIABLE"}'):
            with self.subTest(content=content):
                with open(os.path.join(directory, "age.json"), "w") as stream:
                    stream.write(content)
                with patch.dict(os.environ, {}, clear=True):
                    creds = config_loader.load_backend_credentials(self.temp.name)
                self.assertIsInstance(creds["age"], config_loader.ConfigError)
                with self.assertRaises(encryption.EncryptionError):
                    encryption.prepare(self.job, creds)
                job = copy.deepcopy(self.job)
                job["encryption"]["enabled"] = False
                self.assertIsNone(encryption.prepare(job, creds))
                job["encryption"].update(enabled=True, recipient=RECIPIENT)
                with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
                     patch.object(encryption.subprocess, "run", side_effect=self.fake_age):
                    self.assertEqual(encryption.prepare(job, creds)["recipient"], RECIPIENT)

    def test_failed_encryption_cleans_both_files_and_never_uploads(self):
        def fail(args, **kwargs):
            if kwargs["stdout"] == subprocess.DEVNULL:
                return subprocess.CompletedProcess(args, 0)
            kwargs["stdout"].write(b"partial")
            kwargs["stderr"].write(b"encryption failed")
            return subprocess.CompletedProcess(args, 1)

        backend = MagicMock()
        backend.get_change_detection_identity.return_value = {"backend_type": "aws_s3"}
        with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
             patch.object(encryption.subprocess, "run", side_effect=fail), \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive), \
             patch.object(job_runner, "instantiate_backend", return_value=backend), \
             patch.object(job_runner.retention, "run_retention") as retention:
            self.assertFalse(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
        backend.authenticate.assert_not_called()
        backend.upload.assert_not_called()
        retention.assert_not_called()
        self.assertFalse(os.path.exists(self.archive))
        self.assertFalse(os.path.exists(self.archive + ".age"))
        self.assertFalse(os.path.exists(change_detection.state_path(self.state_dir, "encrypted")))

    def test_existing_encrypted_output_is_not_deleted_or_overwritten(self):
        self.make_archive()
        with open(self.archive + ".age", "wb") as stream:
            stream.write(b"existing")
        with self.assertRaises(FileExistsError):
            encryption.encrypt_archive(self.archive, {"recipient": RECIPIENT, "executable": "age"})
        with open(self.archive + ".age", "rb") as stream:
            self.assertEqual(stream.read(), b"existing")

    def test_upload_reuse_retry_skip_and_recipient_rotation(self):
        self.job["backends"].append({"backend_type": "google_drive", "retention_count": 2})
        uploads = []
        fail_drive = True

        def instantiate(job, config, credentials):
            backend = MagicMock()
            identity = {"backend_type": config["backend_type"]}
            backend.get_change_detection_identity.return_value = identity

            def upload(path, remote_key):
                self.assertTrue(path.endswith(".age"))
                self.assertTrue(remote_key.endswith(".age"))
                self.assertFalse(os.path.exists(self.archive))
                with open(path, "rb") as stream:
                    self.assertTrue(stream.read().startswith(b"age-encryption.org/v1"))
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
                if fail_drive and config["backend_type"] == "google_drive":
                    raise RuntimeError("drive unavailable")
                uploads.append(config["backend_type"])
            backend.upload.side_effect = upload
            return backend

        with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
             patch.object(encryption.subprocess, "run", side_effect=self.fake_age) as run, \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive) as create, \
             patch.object(job_runner, "instantiate_backend", side_effect=instantiate), \
             patch.object(job_runner.retention, "run_retention") as retention:
            self.assertFalse(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
            self.assertEqual(uploads, ["aws_s3"])
            fail_drive = False
            self.assertTrue(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
            self.assertEqual(uploads, ["aws_s3", "google_drive"])
            self.assertEqual(create.call_count, 2)
            self.assertTrue(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
            self.assertEqual(create.call_count, 2)
            # Missing age still fails even with a fully current state.
            with patch.object(encryption.shutil, "which", return_value=None):
                self.assertFalse(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
            self.creds["age"]["recipient"] = OTHER_RECIPIENT
            self.assertTrue(job_runner.run_job(self.job, self.creds, state_dir=self.state_dir))
            self.assertEqual(uploads[-2:], ["aws_s3", "google_drive"])
            self.assertEqual(create.call_count, 3)
            payload_calls = [c for c in run.call_args_list if c.kwargs["stdout"] != subprocess.DEVNULL]
            self.assertEqual(len(payload_calls), 3)  # Once per archive, not per backend.
            self.assertGreaterEqual(retention.call_count, 6)
        self.assertFalse(os.path.exists(self.archive + ".age"))
        with open(change_detection.state_path(self.state_dir, "encrypted")) as stream:
            state_text = stream.read()
        self.assertNotIn(RECIPIENT, state_text)
        self.assertNotIn(OTHER_RECIPIENT, state_text)

    def test_policy_changes_for_encryption_and_key_but_not_executable(self):
        plain = change_detection.calculate_policy_fingerprint(self.job)
        first = change_detection.calculate_policy_fingerprint(self.job, {"recipient": RECIPIENT, "executable": "age"})
        same = change_detection.calculate_policy_fingerprint(self.job, {"recipient": RECIPIENT, "executable": "other"})
        changed = change_detection.calculate_policy_fingerprint(self.job, {"recipient": OTHER_RECIPIENT})
        self.assertNotEqual(plain, first)
        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)

    def test_missing_age_job_does_not_stop_other_jobs(self):
        directory = os.path.join(self.temp.name, "jobs")
        os.mkdir(directory)
        good = copy.deepcopy(self.job)
        good["name"] = "plain"
        good["encryption"]["enabled"] = False
        for job in (self.job, good):
            with open(os.path.join(directory, f"job_{job['name']}.json"), "w") as stream:
                json.dump(job, stream)
        backend = MagicMock()
        backend.get_change_detection_identity.return_value = {"backend_type": "aws_s3"}
        with patch.object(backup.logging_setup, "setup_logger"), \
             patch.object(backup.logging_setup, "get_job_logger", return_value=MagicMock()), \
             patch.object(backup.config_loader, "load_backend_credentials", return_value=self.creds), \
             patch.object(encryption.shutil, "which", return_value=None), \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive) as create, \
             patch.object(job_runner, "instantiate_backend", return_value=backend), \
             patch.object(job_runner.retention, "run_retention"), \
             patch.object(sys, "argv", ["backup.py", "--config-dir", self.temp.name, "run", "--job", "encrypted", "plain"]):
            with self.assertRaises(SystemExit) as result:
                backup.main()
        self.assertEqual(result.exception.code, 1)
        create.assert_called_once()
        backend.upload.assert_called_once()
        self.assertTrue(backend.upload.call_args.args[1].startswith("plain/"))

    def test_decrypt_failure_and_success_publish_only_verified_output(self):
        output = os.path.join(self.temp.name, "restored.tar.gz")

        def fail(args, **kwargs):
            kwargs["stdout"].write(b"unverified plaintext")
            return subprocess.CompletedProcess(args, 1)

        with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
             patch.object(encryption.subprocess, "run", side_effect=fail):
            with self.assertRaises(encryption.EncryptionError):
                encryption.decrypt(self.source, "key.txt", output)
        self.assertFalse(os.path.exists(output))
        self.assertFalse(any(n.startswith(".age-decrypt-") for n in os.listdir(self.temp.name)))
        with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
             patch.object(encryption.subprocess, "run", side_effect=self.fake_age):
            encryption.decrypt(self.source, "key.txt", output)
        with self.assertRaisesRegex(encryption.EncryptionError, "already exists"):
            encryption.decrypt(self.source, "key.txt", output)

    def test_decrypt_cli_needs_no_job_configuration(self):
        with patch.object(encryption, "decrypt") as decrypt, \
             patch.object(backup.config_loader, "load_global_config") as config, \
             patch.object(sys, "argv", ["backup.py", "decrypt", "input.age", "--identity", "key.txt", "--output", "out.tar.gz"]):
            backup.main()
        decrypt.assert_called_once_with("input.age", "key.txt", "out.tar.gz", "age")
        config.assert_not_called()

    def test_decrypt_does_not_overwrite_concurrently_created_output(self):
        output = os.path.join(self.temp.name, "restore.tar.gz")

        def concurrent(args, **kwargs):
            with open(output, "wb") as stream:
                stream.write(b"other process")
            return self.fake_age(args, **kwargs)

        with patch.object(encryption.shutil, "which", return_value="/tools/age"), \
             patch.object(encryption.subprocess, "run", side_effect=concurrent):
            with self.assertRaises(encryption.EncryptionError):
                encryption.decrypt(self.source, "key.txt", output)
        with open(output, "rb") as stream:
            self.assertEqual(stream.read(), b"other process")
        self.assertFalse(any(n.startswith(".age-decrypt-") for n in os.listdir(self.temp.name)))


class TestRealAge(unittest.TestCase):
    """Run with MYBACKUP_TEST_AGE=/path/to/age, or age installed on PATH."""

    def setUp(self):
        self.age = os.environ.get("MYBACKUP_TEST_AGE") or shutil.which("age")
        if not self.age:
            self.skipTest("age unavailable; set MYBACKUP_TEST_AGE for integration tests")
        self.keygen = os.path.join(os.path.dirname(self.age), "age-keygen.exe" if os.name == "nt" else "age-keygen")
        if not os.path.isfile(self.keygen):
            self.skipTest("matching age-keygen unavailable")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def key_pair(self, name):
        identity = os.path.join(self.temp.name, name)
        subprocess.run([self.keygen, "-o", identity], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        recipient = subprocess.check_output([self.keygen, "-y", identity], text=True).strip()
        return identity, recipient

    def test_round_trip_and_reject_wrong_key_damage_and_truncation(self):
        identity, recipient = self.key_pair("identity.txt")
        wrong_identity, _ = self.key_pair("wrong.txt")
        source = os.path.join(self.temp.name, "source.tar.gz")
        content = bytes(range(256)) * 2048  # Several authenticated age chunks.
        with open(source, "wb") as stream:
            stream.write(content)
        settings = encryption.prepare({"encryption": {"enabled": True, "recipient": recipient, "executable": self.age}})
        encrypted = encryption.encrypt_archive(source, settings)
        output = os.path.join(self.temp.name, "restored.tar.gz")
        encryption.decrypt(encrypted, identity, output, self.age)
        with open(output, "rb") as stream:
            self.assertEqual(stream.read(), content)
        with open(encrypted, "rb") as stream:
            ciphertext = stream.read()
        for name, data, key in (("wrong", ciphertext, wrong_identity),
                                ("truncated", ciphertext[:-16], identity),
                                ("tampered", ciphertext[:-1] + bytes([ciphertext[-1] ^ 1]), identity)):
            with self.subTest(name=name):
                damaged = os.path.join(self.temp.name, name + ".age")
                restored = os.path.join(self.temp.name, name + ".tar.gz")
                with open(damaged, "wb") as stream:
                    stream.write(data)
                with self.assertRaises(encryption.EncryptionError):
                    encryption.decrypt(damaged, key, restored, self.age)
                self.assertFalse(os.path.exists(restored))
                self.assertFalse(any(n.startswith(".age-decrypt-") for n in os.listdir(self.temp.name)))
        invalid = recipient[:-1] + ("q" if recipient[-1] != "q" else "p")
        with self.assertRaises(encryption.EncryptionError):
            encryption.prepare({"encryption": {"enabled": True, "recipient": invalid, "executable": self.age}})

    def test_real_backup_pipeline_for_tar_and_zip(self):
        identity, recipient = self.key_pair("identity.txt")
        source = os.path.join(self.temp.name, "files")
        os.mkdir(source)
        with open(os.path.join(source, "data.txt"), "wb") as stream:
            stream.write(b"backup content")
        for format_name in ("tar.gz", "zip"):
            with self.subTest(format=format_name):
                job = {
                    "name": "tarjob" if format_name == "tar.gz" else "zipjob",
                    "sources": [source], "archive": {"format": format_name},
                    "encryption": {"enabled": True},
                    "backends": [{"backend_type": "aws_s3", "retention_count": 2}],
                }
                encrypted = os.path.join(self.temp.name, format_name + ".age")
                staging = []

                def upload(path, remote_key):
                    self.assertTrue(remote_key.endswith("." + format_name + ".age"))
                    self.assertFalse(os.path.exists(path[:-4]))
                    staging.append(os.path.dirname(path))
                    if os.name != "nt":
                        self.assertEqual(stat.S_IMODE(os.stat(staging[-1]).st_mode), 0o700)
                    shutil.copyfile(path, encrypted)

                backend = MagicMock()
                backend.get_change_detection_identity.return_value = {"backend_type": "aws_s3"}
                backend.upload.side_effect = upload
                with patch.object(job_runner, "instantiate_backend", return_value=backend), \
                     patch.object(job_runner.retention, "run_retention"):
                    self.assertTrue(job_runner.run_job(job, {"age": {"recipient": recipient, "executable": self.age}},
                                                       state_dir=os.path.join(self.temp.name, "state")))
                self.assertFalse(os.path.exists(staging[0]))
                restored = os.path.join(self.temp.name, "restored." + format_name)
                encryption.decrypt(encrypted, identity, restored, self.age)
                if format_name == "tar.gz":
                    with tarfile.open(restored) as archive:
                        self.assertEqual(archive.extractfile(archive.getmembers()[0]).read(), b"backup content")
                else:
                    with zipfile.ZipFile(restored) as archive:
                        self.assertEqual(archive.read(archive.namelist()[0]), b"backup content")
