import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND = Path(__file__).resolve().parents[2]


def upgrade_to_head(url: str) -> None:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # configparser interpolation
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")


async def migrate(url: str) -> None:
    """Alembic's async env starts its own event loop, so it must run off the server's loop."""
    await asyncio.to_thread(upgrade_to_head, url)
