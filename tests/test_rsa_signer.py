import unittest
import subprocess
from core import rsa_signer

import os
import shutil

class TestRsaSigner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        openssl_exe = shutil.which("openssl")
        if not openssl_exe and os.path.exists("C:\\Program Files\\Git\\usr\\bin\\openssl.exe"):
            openssl_exe = "C:\\Program Files\\Git\\usr\\bin\\openssl.exe"
            
        try:
            if not openssl_exe:
                raise FileNotFoundError()
                
            # Dynamically generate a genuine RSA private key using OpenSSL to prevent hardcoded key reliance
            res = subprocess.run(
                [openssl_exe, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:1024"],
                capture_output=True, check=True
            )
            cls.test_pem = res.stdout.decode('utf-8')
            cls.has_openssl = True
            cls.openssl_exe = openssl_exe
        except (FileNotFoundError, subprocess.CalledProcessError):
            cls.test_pem = None
            cls.has_openssl = False
            cls.openssl_exe = "openssl"
            
        cls.test_payload = b"This is a mocked JWT authentication header layout structure meant for signing constraints tests."

    def test_rsa_implementations_match(self):
        """Cross-verifies the output of the native math algorithm directly against the C-compiled OpenSSL output."""
        if not self.has_openssl:
            self.skipTest("OpenSSL is not installed locally on this test agent, skipping comparative evaluation.")
            
        sig_openssl = rsa_signer.sign_openssl(self.test_payload, self.test_pem)
        
        # 2. Sign via our Pure-Python AST parser and custom modPows
        sig_python = rsa_signer.sign_pure_python(self.test_payload, self.test_pem)
        
        # 3. Mathematically equivalent assertion
        self.assertEqual(sig_openssl, sig_python, "The pure-python mathematical signature diverted from the OpenSSL compiled engine!")
        
    def test_force_python_config_flag(self):
        if not self.has_openssl:
            self.skipTest("Need OpenSSL to mock keys")
            
        # Check that the wrapper layer accurately bounces down to python when strictly flagged
        sig_manual = rsa_signer.sign_rsa_sha256(self.test_payload, self.test_pem, force_pure_python=True)
        # Verify it works
        self.assertEqual(len(sig_manual), 128) # 1024 bit key = 128 byte signature

if __name__ == '__main__':
    unittest.main()
