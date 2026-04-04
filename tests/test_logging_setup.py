import unittest
import os
import tempfile
import logging
from core import logging_setup

class TestLoggingSetup(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        # Reset the backup logger to avoid conflicts between tests
        logger = logging.getLogger("backup")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        self.temp_dir.cleanup()

    def test_setup_logger_creates_file(self):
        log_file = os.path.join(self.temp_dir.name, "test.log")
        logger = logging_setup.setup_logger(log_level="DEBUG", log_file=log_file)
        
        self.assertEqual(logger.level, logging.DEBUG)
        
        # Log a test message
        logger.info("Test message")
        
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, "r") as f:
            content = f.read()
            self.assertIn("Test message", content)
            self.assertIn("[global    ]", content) # default job name
            
    def test_get_job_logger(self):
        log_file = os.path.join(self.temp_dir.name, "test_job.log")
        logging_setup.setup_logger(log_level="INFO", log_file=log_file)
        
        job_logger = logging_setup.get_job_logger("webserver")
        job_logger.info("Job specific message")
        
        with open(log_file, "r") as f:
            content = f.read()
            self.assertIn("Job specific message", content)
            self.assertIn("[webserver ]", content)

if __name__ == '__main__':
    unittest.main()
