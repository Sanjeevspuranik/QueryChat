import csv
import io
import json
import re
from typing import Any

from app.core.errors import QueryValidationError

_FORMULA_START = re.compile(r"^[=+\-@\t\r]")
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, str) and _FORMULA_START.match(value):
        return "'" + value  # stops spreadsheets from evaluating user-controlled data as formulas
    return value


def to_csv(result: dict[str, Any]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([_csv_cell(c) for c in result.get("columns", [])])
    for row in result.get("rows", []):
        writer.writerow([_csv_cell(v) for v in row])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")  # BOM so Excel detects UTF-8


def to_json(result: dict[str, Any]) -> bytes:
    columns = result.get("columns", [])
    records = [dict(zip(columns, row)) for row in result.get("rows", [])]
    return json.dumps(records, default=str, ensure_ascii=False, indent=2).encode("utf-8")


_EXPORTERS = {
    "csv": (to_csv, "text/csv; charset=utf-8"),
    "json": (to_json, "application/json"),
}


def export_result(result: dict[str, Any], fmt: str) -> tuple[bytes, str]:
    """Serialise a stored query result. Returns (body, media_type)."""
    exporter = _EXPORTERS.get(fmt)
    if exporter is None:
        raise QueryValidationError(f"Unsupported export format: {fmt}. Use one of: {', '.join(_EXPORTERS)}.")
    render, media_type = exporter
    return render(result), media_type


def safe_filename(title: str, fmt: str) -> str:
    stem = _FILENAME_UNSAFE.sub("_", title).strip("_")[:50] or "result"
    return f"{stem}.{fmt}"
