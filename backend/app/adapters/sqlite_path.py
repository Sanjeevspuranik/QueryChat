"""Locating the file behind a sqlite:// URL, with errors a person can act on.

SQLite itself only says "unable to open database file", and it silently *creates* an
empty database when the folder exists but the file does not. We resolve and check
the path up front, and open the file read-only afterwards."""
import re
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]
_WINDOWS_DRIVE_AFTER_SLASH = re.compile(r"^/[A-Za-z]:[\\/]")


class SqliteFileError(ValueError):
    """The URL does not lead to a readable SQLite file."""


def resolve_sqlite_file(url: str) -> Path:
    try:
        database = make_url(url).database
    except ArgumentError as exc:
        raise SqliteFileError("Malformed SQLite URL. Example: sqlite:///C:/data/my.db") from exc
    if not database or database == ":memory:":
        raise SqliteFileError("SQLite URL must point to a database file.")

    raw = database.strip().strip("\"'")
    if _WINDOWS_DRIVE_AFTER_SLASH.match(raw):  # sqlite:////C:/x.db has one slash too many on Windows
        raw = raw[1:]
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()

    if path.is_dir():
        raise SqliteFileError(f"'{path}' is a folder. Point the URL at the database file itself.")
    if not path.is_file():
        hint = "" if Path(raw).is_absolute() else f" Relative paths are resolved from {Path.cwd()}; use an absolute path."
        raise SqliteFileError(f"SQLite file not found: {path}.{hint}")
    return path


def read_only_url(path: Path) -> str:
    """SQLAlchemy URL that opens the file read-only, so a bad path can never create a database."""
    return f"sqlite:///{path.as_uri()}?mode=ro&uri=true"
