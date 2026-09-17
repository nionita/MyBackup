import unittest
from unittest.mock import patch, MagicMock
from backends import aws_s3
import os

class TestAwsS3Backend(unittest.TestCase):
    def setUp(self):
        self.job_config = {"name": "test_job"}
        self.backend_config = {
            "aws_access_key_id": "ACCESS",
            "aws_secret_access_key": "SECRET",
            "aws_bucket": "test-bucket",
            "aws_prefix": "backups/"
        }
        self.backend = aws_s3.AwsS3Backend(self.job_config, self.backend_config)

    @patch('urllib.request.urlopen')
    def test_single_upload(self, mock_urlopen):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"dummy data")
            tf_path = tf.name
            
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.status = 200
        mock_resp.headers = {"ETag": "dummy"}
        mock_urlopen.return_value = mock_resp
        
        try:
            # We bypass the size check by calling _single_upload directly, but upload() would route it correctly.
            self.backend.upload(tf_path, "test_file.txt")
            self.assertTrue(mock_urlopen.called)
        finally:
            os.remove(tf_path)
            
    def test_prefix_normalization(self):
        self.assertEqual(self.backend.prefix, "backups/")

    def test_change_detection_identity_excludes_credentials(self):
        self.assertEqual(self.backend.get_change_detection_identity(), {
            "backend_type": "aws_s3",
            "bucket": "test-bucket",
            "region": "us-east-1",
            "prefix": "backups/",
        })
        
if __name__ == '__main__':
    unittest.main()
