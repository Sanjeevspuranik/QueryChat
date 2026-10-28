from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ConflictError
from app.core.security import PasswordHasher, TokenService
from app.db.models import User


class AuthService:
    def __init__(self, db: AsyncSession, hasher: PasswordHasher, tokens: TokenService) -> None:
        self._db = db
        self._hasher = hasher
        self._tokens = tokens

    async def register(self, email: str, password: str) -> tuple[User, str]:
        user = User(email=email.lower(), password_hash=self._hasher.hash(password))
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise ConflictError("An account with this email already exists.") from exc
        return user, self._tokens.issue(user.id)

    async def authenticate(self, email: str, password: str) -> tuple[User, str]:
        user = await self._db.scalar(select(User).where(User.email == email.lower()))
        # Same error for unknown user and bad password to avoid account enumeration.
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")
        return user, self._tokens.issue(user.id)

    async def get_user(self, token: str) -> User:
        user_id = self._tokens.verify(token)
        user = await self._db.get(User, user_id) if user_id else None
        if user is None:
            raise AuthenticationError("Not authenticated.")
        return user
