import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import backup
from backup import get_parser
from core import change_detection, job_runner


class FakeBackend:
    def __init__(self, identity, fail_upload=False):
        self.identity = identity
        self.fail_upload = fail_upload
        self.authenticated = 0
        self.uploads = []

    def get_change_detection_identity(self):
        return self.identity

    def authenticate(self):
        self.authenticated += 1

    def upload(self, local_path, remote_key):
        if self.fail_upload:
            raise RuntimeError("upload failed")
        self.uploads.append((local_path, remote_key))


class TestJobRunnerChangeDetection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_dir = os.path.join(self.temp_dir.name, "source")
        os.makedirs(self.source_dir)
        with open(os.path.join(self.source_dir, "file.txt"), "w", encoding="utf-8") as source_file:
            source_file.write("content")
        self.state_dir = os.path.join(self.temp_dir.name, "state")
        self.archive_path = os.path.join(self.temp_dir.name, "archive.tar.gz")
        self.job = {
            "name": "test_job",
            "sources": [self.source_dir],
            "exclude_patterns": [],
            "archive": {"format": "tar.gz", "compression_level": 1},
            "change_detection": {"enabled": True},
            "backends": [
                {"backend_type": "aws_s3", "retention_count": 3, "target": "aws"},
                {"backend_type": "google_drive", "retention_count": 3, "target": "drive"},
            ],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_archive(self, **_kwargs):
        with open(self.archive_path, "wb") as archive_file:
            archive_file.write(b"archive")
        return self.archive_path

    def test_run_parser_accepts_force(self):
        args = get_parser().parse_args(["run", "--job", "test_job", "--force"])
        self.assertTrue(args.force)
        self.assertEqual(args.job, "test_job")

    def test_main_run_uses_module_os_for_state_directory(self):
        logger = MagicMock()
        with patch.object(backup.config_loader, "load_global_config", return_value={}), \
             patch.object(backup.logging_setup, "setup_logger"), \
             patch.object(backup.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(backup.config_loader, "load_backend_credentials", return_value={}), \
             patch.object(backup.config_loader, "load_job_configs", return_value=[self.job]), \
             patch.object(job_runner, "run_job", return_value=True) as run_job, \
             patch.object(sys, "argv", ["backup.py", "--config-dir", self.temp_dir.name, "run"]):
            backup.main()

        run_job.assert_called_once_with(
            self.job,
            {},
            state_dir=os.path.join(self.temp_dir.name, "state"),
            force=False,
        )

    def backends_for(self, failures=()):
        created = []

        def instantiate(_job, backend_config, _creds):
            target = backend_config["target"]
            backend = FakeBackend(
                {"backend_type": backend_config["backend_type"], "target": target},
                fail_upload=target in failures,
            )
            created.append(backend)
            return backend

        return created, instantiate

    def test_first_run_then_unchanged_run_skips_uploads(self):
        first_backends, first_factory = self.backends_for()
        second_backends, second_factory = self.backends_for()
        logger = MagicMock()
        with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(job_runner.retention, "run_retention") as retention, \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive) as create_archive, \
             patch.object(job_runner, "instantiate_backend", side_effect=first_factory):
            self.assertTrue(job_runner.run_job(self.job, state_dir=self.state_dir))
            self.assertEqual([len(backend.uploads) for backend in first_backends], [1, 1])

        with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(job_runner.retention, "run_retention") as retention, \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive) as create_archive, \
             patch.object(job_runner, "instantiate_backend", side_effect=second_factory):
            self.assertTrue(job_runner.run_job(self.job, state_dir=self.state_dir))
            create_archive.assert_not_called()
            self.assertEqual([len(backend.uploads) for backend in second_backends], [0, 0])
            self.assertEqual(retention.call_count, 2)

    def test_failed_destination_is_retried_without_reuploading_successful_one(self):
        first_backends, first_factory = self.backends_for(failures=("drive",))
        second_backends, second_factory = self.backends_for()
        logger = MagicMock()
        with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(job_runner.retention, "run_retention"), \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive), \
             patch.object(job_runner, "instantiate_backend", side_effect=first_factory):
            self.assertFalse(job_runner.run_job(self.job, state_dir=self.state_dir))
            self.assertEqual([len(backend.uploads) for backend in first_backends], [1, 0])

        with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(job_runner.retention, "run_retention"), \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive), \
             patch.object(job_runner, "instantiate_backend", side_effect=second_factory):
            self.assertTrue(job_runner.run_job(self.job, state_dir=self.state_dir))
            self.assertEqual([len(backend.uploads) for backend in second_backends], [0, 1])

    def test_force_uploads_all_destinations(self):
        initial_backends, initial_factory = self.backends_for()
        forced_backends, forced_factory = self.backends_for()
        logger = MagicMock()
        for factory, backends, force in (
            (initial_factory, initial_backends, False),
            (forced_factory, forced_backends, True),
        ):
            with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
                 patch.object(job_runner.retention, "run_retention"), \
                 patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive), \
                 patch.object(job_runner, "instantiate_backend", side_effect=factory):
                self.assertTrue(job_runner.run_job(self.job, state_dir=self.state_dir, force=force))
        self.assertEqual([len(backend.uploads) for backend in forced_backends], [1, 1])

    def test_state_write_failure_marks_job_failed_after_upload(self):
        backends, factory = self.backends_for()
        logger = MagicMock()
        with patch.object(job_runner.logging_setup, "get_job_logger", return_value=logger), \
             patch.object(job_runner.retention, "run_retention"), \
             patch.object(job_runner.archiver, "create_archive", side_effect=self.make_archive), \
             patch.object(job_runner, "instantiate_backend", side_effect=factory), \
             patch.object(change_detection, "save_state", side_effect=change_detection.StateError("no state")):
            self.assertFalse(job_runner.run_job(self.job, state_dir=self.state_dir))
        self.assertEqual([len(backend.uploads) for backend in backends], [1, 1])
