"""Print fresh SECRET_KEY and ENCRYPTION_KEY values for the .env file."""
import secrets

from cryptography.fernet import Fernet

print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
print(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")
