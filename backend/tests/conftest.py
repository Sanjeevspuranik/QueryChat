import os

from cryptography.fernet import Fernet

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("LOG_TO_FILE", "false")  # tests must not write into backend/logs
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
