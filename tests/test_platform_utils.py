import unittest
import os
import platform
import pathlib
from core import platform_utils

class TestPlatformUtils(unittest.TestCase):

    def test_is_windows(self):
        # We can't strictly assert the platform dynamically matching without restating logic
        # but we can ensure it returns a bool.
        self.assertIsInstance(platform_utils.is_windows(), bool)

    def test_is_linux(self):
        self.assertIsInstance(platform_utils.is_linux(), bool)

    def test_get_default_paths(self):
        paths = platform_utils.get_default_paths()
        self.assertIn("temp_dir", paths)
        self.assertIn("log_dir", paths)
        self.assertIn("install_dir", paths)

    def test_check_permissions(self):
        # The current directory should be readable
        self.assertTrue(platform_utils.check_permissions("."))

    def test_resolve_home(self):
        resolved_unix = platform_utils.resolve_home("~/test_dir")
        self.assertTrue(os.path.isabs(resolved_unix))
        self.assertTrue(resolved_unix.endswith("test_dir") or resolved_unix.endswith("test_dir/") or resolved_unix.endswith("test_dir\\\\"))

        if platform_utils.is_windows():
            os.environ["USERPROFILE"] = "C:\\Users\\Test"
            resolved_win = platform_utils.resolve_home("%USERPROFILE%\\test_dir")
            self.assertTrue(os.path.isabs(resolved_win))
            self.assertIn("Test", resolved_win)

if __name__ == '__main__':
    unittest.main()
