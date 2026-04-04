import unittest
import os
import tempfile
import zipfile
import tarfile
from core import archiver

class TestArchiver(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sources_dir = os.path.join(self.temp_dir.name, "sources")
        os.makedirs(self.sources_dir, exist_ok=True)
        
        # Create some dummy files
        self.files = ["file1.txt", "file2.log", "test.tmp"]
        for f in self.files:
            with open(os.path.join(self.sources_dir, f), "w") as fp:
                fp.write("dummy content")
                
        self.sub_dir = os.path.join(self.sources_dir, "__pycache__")
        os.makedirs(self.sub_dir, exist_ok=True)
        with open(os.path.join(self.sub_dir, "cache.pyc"), "w") as fp:
            fp.write("dummy")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_should_exclude(self):
        patterns = ["*.tmp", "*.log", "__pycache__"]
        self.assertTrue(archiver.should_exclude("file2.log", patterns))
        self.assertTrue(archiver.should_exclude("__pycache__/cache.pyc", patterns))
        self.assertFalse(archiver.should_exclude("file1.txt", patterns))

    def test_create_zip_archive(self):
        output = archiver.create_archive(
            job_name="testjob",
            sources=[self.sources_dir],
            archive_format="zip",
            temp_dir=self.temp_dir.name,
            exclude_patterns=["*.tmp", "__pycache__"]
        )
        self.assertTrue(os.path.exists(output))
        self.assertTrue(output.endswith(".zip"))
        
        # Check contents
        with zipfile.ZipFile(output, "r") as zf:
            files_in_zip = zf.namelist()
            # It shouldn't contain .tmp or cache.pyc
            for f in files_in_zip:
                self.assertNotIn(".tmp", f)
                self.assertNotIn("__pycache__", f)

    def test_create_targz_archive(self):
        output = archiver.create_archive(
            job_name="testjob",
            sources=[self.sources_dir],
            archive_format="tar.gz",
            temp_dir=self.temp_dir.name,
            exclude_patterns=["*.tmp"]
        )
        self.assertTrue(os.path.exists(output))
        self.assertTrue(output.endswith(".tar.gz"))
        
        with tarfile.open(output, "r:gz") as tar:
            files_in_tar = tar.getnames()
            for f in files_in_tar:
                self.assertNotIn(".tmp", f)
                
if __name__ == '__main__':
    unittest.main()
