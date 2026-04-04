import unittest
import os
import tempfile
import json
from core import config_loader

class TestConfigLoader(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = os.path.join(self.temp_dir.name, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.jobs_dir = os.path.join(self.config_dir, "jobs")
        os.makedirs(self.jobs_dir, exist_ok=True)
        
        # Add a dummy source path that exists
        self.dummy_source = os.path.join(self.temp_dir.name, "source")
        os.makedirs(self.dummy_source, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_global_config_defaults(self):
        config = config_loader.load_global_config(self.config_dir)
        self.assertEqual(config["version"], "1.0")
        self.assertEqual(config["log_level"], "INFO")

    def test_load_global_config_custom(self):
        custom_global = {
            "version": "1.1",
            "log_level": "DEBUG",
            "log_file": "custom.log",
            "log_max_bytes": 1000,
            "log_backup_count": 3,
            "temp_dir": "/tmp/custom"
        }
        with open(os.path.join(self.config_dir, "global.json"), "w") as f:
            json.dump(custom_global, f)
            
        config = config_loader.load_global_config(self.config_dir)
        self.assertEqual(config["log_level"], "DEBUG")
        self.assertEqual(config["temp_dir"], "/tmp/custom")

    def test_validate_job_config_valid(self):
        data = {
            "name": "test_job",
            "sources": [self.dummy_source],
            "backends": [{"backend_type": "aws_s3", "retention_count": 5}]
        }
        validated = config_loader.validate_job_config("test_job", data)
        self.assertEqual(validated["archive"]["compression_level"], 6)

    def test_validate_job_config_invalid_name(self):
        data = {"name": "wrong_name", "sources": [self.dummy_source], "backends": [{"backend_type": "aws_s3", "retention_count": 5}]}
        with self.assertRaisesRegex(config_loader.ConfigError, "does not match filename"):
            config_loader.validate_job_config("test_job", data)

    def test_validate_job_config_missing_sources(self):
        data = {"name": "test_job", "backends": [{"backend_type": "aws_s3", "retention_count": 5}]}
        with self.assertRaisesRegex(config_loader.ConfigError, "at least one source"):
            config_loader.validate_job_config("test_job", data)

    def test_validate_job_config_no_existing_sources(self):
        data = {"name": "test_job", "sources": ["/path/that/does/not/exist/ever"], "backends": [{"backend_type": "aws_s3", "retention_count": 5}]}
        with self.assertRaisesRegex(config_loader.ConfigError, "None of the sources.*exist"):
            config_loader.validate_job_config("test_job", data)

    def test_env_var_resolution(self):
        os.environ["TEST_ENV_VAR"] = "test_value"
        data = {"key1": "$ENV:TEST_ENV_VAR", "key2": ["$ENV:TEST_ENV_VAR"]}
        resolved = config_loader.resolve_env_vars(data)
        self.assertEqual(resolved["key1"], "test_value")
        self.assertEqual(resolved["key2"][0], "test_value")

    def test_load_job_configs(self):
        job_data = {
            "name": "test_job",
            "sources": [self.dummy_source],
            "backends": [{"backend_type": "aws_s3", "retention_count": 5}]
        }
        with open(os.path.join(self.jobs_dir, "job_test_job.json"), "w") as f:
            json.dump(job_data, f)
            
        jobs = config_loader.load_job_configs(self.config_dir)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["name"], "test_job")

    def test_load_backend_credentials(self):
        creds_dir = os.path.join(self.config_dir, "credentials")
        os.makedirs(creds_dir, exist_ok=True)
        
        # Mock global credential
        gd_creds = {
            "gd_client_id": "GLOBAL_ID",
            "gd_client_secret": "GLOBAL_SECRET",
            "gd_refresh_token": "GLOBAL_TOKEN"
        }
        with open(os.path.join(creds_dir, "google_drive.json"), "w") as f:
            json.dump(gd_creds, f)
            
        creds = config_loader.load_backend_credentials(self.config_dir)
        self.assertIn("google_drive", creds)
        self.assertEqual(creds["google_drive"]["gd_client_id"], "GLOBAL_ID")
        
        # Test instantiation merging
        from core import job_runner
        
        job_config = {"name": "test_job"}
        # Backend defines local overrides
        backend_config = {
            "backend_type": "google_drive",
            "gd_folder_id": "LOCAL_FOLDER",
            # Intentionally overriding a global constraint to test override priority
            "gd_client_id": "OVERRIDDEN_ID"
        }
        
        # Passing mock credential array into instantiator to mock job_runner natively
        combined_backend = job_runner.instantiate_backend(job_config, backend_config, creds)
        
        # Assert local configs took priority
        self.assertEqual(combined_backend.client_id, "OVERRIDDEN_ID")
        # Assert global configs passed down correctly
        self.assertEqual(combined_backend.refresh_token, "GLOBAL_TOKEN")
        # Assert local unique configs persist
        self.assertEqual(combined_backend.folder_id, "LOCAL_FOLDER")

if __name__ == '__main__':
    unittest.main()
