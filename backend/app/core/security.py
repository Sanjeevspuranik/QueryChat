import time

import jwt
from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = _Argon2()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError):
            return False


class TokenService:
    """Issues and verifies short-lived JWT access tokens."""

    _ALGORITHM = "HS256"

    def __init__(self, secret_key: str, ttl_minutes: int) -> None:
        self._secret = secret_key
        self._ttl_seconds = ttl_minutes * 60

    def issue(self, user_id: str) -> str:
        now = int(time.time())
        payload = {"sub": user_id, "iat": now, "exp": now + self._ttl_seconds}
        return jwt.encode(payload, self._secret, algorithm=self._ALGORITHM)

    def verify(self, token: str) -> str | None:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._ALGORITHM])
        except jwt.PyJWTError:
            return None
        return payload.get("sub")

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds


class CredentialCipher:
    """Encrypts database URLs at rest (Fernet / AES-128-CBC + HMAC)."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored credential cannot be decrypted") from exc
