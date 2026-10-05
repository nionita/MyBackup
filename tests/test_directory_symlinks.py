import copy
import json
import os
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import backup
from core import archiver, change_detection, config_loader, job_runner


class TestDirectorySymlinks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = os.path.join(self.temp.name, "source")
        self.target = os.path.join(self.temp.name, "outside")
        os.mkdir(self.source)
        os.mkdir(self.target)
        self.target_file = os.path.join(self.target, "secret.txt")
        with open(self.target_file, "w") as stream:
            stream.write("original")
        self.job = {
            "name": "links", "sources": [self.source],
            "archive": {"format": "tar.gz", "preserve_directory_symlinks": True},
            "backends": [{"backend_type": "aws_s3", "retention_count": 2}],
        }

    def link(self, target, name, directory=False):
        path = os.path.join(self.source, name)
        try:
            os.symlink(target, path, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        return path

    def test_tar_preserves_links_without_traversal(self):
        links = {
            "directory": self.link(self.target, "directory", True),
            "file": self.link(self.target_file, "file"),
            "broken": self.link("missing", "broken", True),
            "loop": self.link(".", "loop", True),
        }
        self.link(self.target, "excluded", True)
        output = archiver.create_archive("links", [self.source], "tar.gz",
                                        temp_dir=self.temp.name, exclude_patterns=["excluded"],
                                        preserve_directory_symlinks=True)
        with tarfile.open(output) as archive:
            members = archive.getmembers()
            self.assertEqual({os.path.basename(m.name) for m in members}, set(links))
            for member in members:
                self.assertTrue(member.issym())
                self.assertEqual(member.linkname, os.readlink(links[os.path.basename(member.name)]))
            # Restore relative links into an isolated directory; external targets
            # require an explicit trusted extraction policy.
            relative = [m for m in members if m.linkname in ("missing", ".")]
            restored = os.path.join(self.temp.name, "restored")
            archive.extractall(restored, members=relative, filter="data")
            for member in relative:
                self.assertEqual(os.readlink(os.path.join(restored, member.name)), member.linkname)

    def test_explicit_sources_and_trailing_separator(self):
        directory = self.link(self.target, "directory", True)
        broken = self.link("missing", "broken", True)
        self.job["sources"] = [broken]
        config_loader.validate_job_config("links", self.job)
        for source in (directory + os.path.sep, broken):
            with self.subTest(source=source):
                output = archiver.create_archive("links", [source], "tar.gz",
                                                temp_dir=self.temp.name,
                                                preserve_directory_symlinks=True)
                with tarfile.open(output) as archive:
                    self.assertEqual(len(archive.getmembers()), 1)
                    self.assertTrue(archive.getmembers()[0].issym())

    def test_fingerprint_tracks_link_not_target_contents(self):
        path = self.link(self.target, "directory", True)
        fingerprint = lambda: change_detection.calculate_source_fingerprint([self.source], [], True)
        first = fingerprint()
        with open(self.target_file, "w") as stream:
            stream.write("changed")
        self.assertEqual(first, fingerprint())
        os.unlink(path)
        os.symlink("other-target", path, target_is_directory=True)
        self.assertNotEqual(first, fingerprint())

    def test_default_omits_directory_links(self):
        self.link(self.target, "directory", True)
        self.assertEqual(list(archiver.iter_included_files([self.source])), [])

    def test_invalid_format_and_type(self):
        for format_name in ("zip", "none"):
            job = copy.deepcopy(self.job)
            job["archive"]["format"] = format_name
            with self.assertRaisesRegex(config_loader.ConfigError, "requires tar.gz"):
                config_loader.validate_job_config("links", job)
            with patch.object(job_runner.archiver, "create_archive") as create:
                self.assertFalse(job_runner.run_job(job))
                create.assert_not_called()
        self.job["archive"]["preserve_directory_symlinks"] = "true"
        with self.assertRaisesRegex(config_loader.ConfigError, "preserve_directory_symlinks"):
            config_loader.validate_job_config("links", self.job)

    def test_invalid_job_isolated_and_unknown_selection_aborts(self):
        config_dir = os.path.join(self.temp.name, "config")
        os.makedirs(os.path.join(config_dir, "jobs"))
        good = copy.deepcopy(self.job)
        good["name"] = "good"
        bad = copy.deepcopy(self.job)
        bad["archive"]["format"] = "zip"
        for job in (good, bad):
            with open(os.path.join(config_dir, "jobs", f"job_{job['name']}.json"), "w") as stream:
                json.dump(job, stream)
        for selected in ([], ["--job", "links", "good"], ["--job", "unknown", "good"]):
            with self.subTest(selected=selected), \
                 patch.object(backup.logging_setup, "setup_logger"), \
                 patch.object(backup.logging_setup, "get_job_logger", return_value=MagicMock()), \
                 patch.object(job_runner, "run_job", return_value=True) as run, \
                 patch.object(sys, "argv", ["backup.py", "--config-dir", config_dir, "run", *selected]):
                with self.assertRaises(SystemExit) as result:
                    backup.main()
                self.assertEqual(result.exception.code, 1)
                self.assertEqual(run.call_count, 0 if "unknown" in selected else 1)
                if run.called:
                    self.assertEqual(run.call_args.args[0]["name"], "good")
        with patch.object(backup.logging_setup, "setup_logger"), \
             patch.object(backup.logging_setup, "get_job_logger", return_value=MagicMock()), \
             patch.object(sys, "argv", ["backup.py", "--config-dir", config_dir, "validate"]):
            with self.assertRaises(SystemExit) as result:
                backup.main()
            self.assertEqual(result.exception.code, 1)
