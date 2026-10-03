import unittest

from backends.google_drive import GoogleDriveBackend


class TestGoogleDriveBackend(unittest.TestCase):
    def test_change_detection_identity_excludes_credentials(self):
        backend = GoogleDriveBackend(
            {"name": "test_job"},
            {
                "gd_folder_id": "target-folder",
                "gd_client_id": "client-id",
                "gd_client_secret": "client-secret",
                "gd_refresh_token": "refresh-token",
            },
        )
        self.assertEqual(backend.get_change_detection_identity(), {
            "backend_type": "google_drive",
            "folder_id": "target-folder",
        })
