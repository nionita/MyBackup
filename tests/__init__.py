import sys
import os

# Add backup-tool to python path so tests can run against it natively
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backup-tool')))
