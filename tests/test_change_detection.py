import os
import stat
import tempfile
import unittest
from unittest.mock import MagicMock

from core import change_detection


class TestChangeDetection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sources_dir = os.path.join(self.temp_dir.name, "sources")
        os.makedirs(self.sources_dir)
        self.file_path = os.path.join(self.sources_dir, "script.sh")
        with open(self.file_path, "w", encoding="utf-8") as source_file:
            source_file.write("#!/bin/sh\necho backup\n")
        self.state_dir = os.path.join(self.temp_dir.name, "state")

    def tearDown(self):
        self.temp_dir.cleanup()

    def fingerprint(self, excludes=None):
        return change_detection.calculate_source_fingerprint(
            [self.sources_dir], excludes or []
        )

    def test_fingerprint_changes_for_content_and_rename(self):
        original = self.fingerprint()
        with open(self.file_path, "a", encoding="utf-8") as source_file:
            source_file.write("echo changed\n")
        self.assertNotEqual(original, self.fingerprint())

        changed = self.fingerprint()
        os.rename(self.file_path, os.path.join(self.sources_dir, "renamed.sh"))
        self.assertNotEqual(changed, self.fingerprint())

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics are not available on Windows")
    def test_fingerprint_changes_for_restorable_metadata(self):
        original = self.fingerprint()
        os.chmod(self.file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.assertNotEqual(original, self.fingerprint())

        changed = self.fingerprint()
        file_stat = os.stat(self.file_path)
        os.utime(
            self.file_path,
            ns=(file_stat.st_atime_ns, file_stat.st_mtime_ns + 1_000_000_000),
        )
        self.assertNotEqual(changed, self.fingerprint())

    def test_excluded_content_does_not_change_fingerprint(self):
        ignored = os.path.join(self.sources_dir, "ignored.log")
        with open(ignored, "w", encoding="utf-8") as ignored_file:
            ignored_file.write("one")
        original = self.fingerprint(["*.log"])
        with open(ignored, "w", encoding="utf-8") as ignored_file:
            ignored_file.write("two")
        self.assertEqual(original, self.fingerprint(["*.log"]))

    def test_state_round_trip_and_destination_matching(self):
        source_fingerprint = self.fingerprint()
        policy_fingerprint = "policy"
        identity = {"backend_type": "test", "destination": "one"}
        state = change_detection.record_destination_success(
            None, source_fingerprint, policy_fingerprint, identity
        )
        change_detection.save_state(self.state_dir, "test_job", state)

        loaded = change_detection.load_state(self.state_dir, "test_job", MagicMock())
        self.assertTrue(change_detection.destination_is_current(
            loaded, source_fingerprint, policy_fingerprint, identity
        ))
        self.assertFalse(change_detection.destination_is_current(
            loaded, source_fingerprint, policy_fingerprint,
            {"backend_type": "test", "destination": "two"},
        ))
        self.assertFalse(os.path.exists(os.path.join(self.state_dir, ".test_job.tmp")))

        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.state_dir).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(
                change_detection.state_path(self.state_dir, "test_job")
            ).st_mode), 0o600)

    def test_corrupt_state_is_ignored(self):
        os.makedirs(self.state_dir)
        path = change_detection.state_path(self.state_dir, "test_job")
        with open(path, "w", encoding="utf-8") as state_file:
            state_file.write("not json")
        logger = MagicMock()
        self.assertIsNone(change_detection.load_state(self.state_dir, "test_job", logger))
        logger.warning.assert_called_once()
