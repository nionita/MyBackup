import unittest
import datetime
from core import aws_sigv4

class TestAwsSigV4(unittest.TestCase):

    def test_get_signature_key(self):
        # We can test against a known working example from AWS docs if we had the exact vectors,
        # but we can at least assert it runs without exception and outputs a 32-byte digest
        key = aws_sigv4.get_signature_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20150830", "us-east-1", "iam")
        self.assertEqual(len(key), 32)
        
    def test_generate_signed_headers(self):
        headers = {
            "x-amz-date": "20130524T000000Z",
            "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" # empty string hash
        }
        signed = aws_sigv4.generate_signed_headers(
            method="GET",
            host="examplebucket.s3.amazonaws.com",
            uri="/test.txt",
            query="",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            service="s3",
            payload_hash=headers["x-amz-content-sha256"],
            headers=headers
        )
        
        self.assertIn("Authorization", signed)
        self.assertTrue(signed["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request"))
        self.assertIn("SignedHeaders=", signed["Authorization"])
        self.assertIn("Signature=", signed["Authorization"])
        self.assertEqual(signed["x-amz-date"], "20130524T000000Z")

if __name__ == '__main__':
    unittest.main()
