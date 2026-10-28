import csv
import io
import json
from types import SimpleNamespace

import pytest

from app.agent.llm import OpenAIQueryLLM
from app.agent.state import QueryRequest
from app.core.errors import QueryValidationError
from app.services.chat_service import HISTORY_SQL_CHARS, HISTORY_TEXT_CHARS, build_history
from app.services.export_service import export_result, safe_filename

RESULT = {"columns": ["name", "note"], "rows": [["Ann", "=SUM(A1)"], ["Bo", None], ["Çé", "a,b\n\"c\""]]}


def test_csv_export_escapes_formulas_and_quotes():
    body, media = export_result(RESULT, "csv")
    assert media.startswith("text/csv") and body.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    assert rows[0] == ["name", "note"]
    assert rows[1] == ["Ann", "'=SUM(A1)"]  # formula neutralised
    assert rows[2] == ["Bo", ""]
    assert rows[3] == ["Çé", 'a,b\n"c"']  # quoting round-trips


def test_json_export_is_records():
    body, media = export_result(RESULT, "json")
    assert media == "application/json"
    assert json.loads(body)[0] == {"name": "Ann", "note": "=SUM(A1)"}


def test_unknown_export_format_rejected():
    with pytest.raises(QueryValidationError):
        export_result(RESULT, "xlsx")


def test_safe_filename():
    assert safe_filename('Top 5 "concerts"/../x', "csv") == "Top_5_concerts_.._x.csv"
    assert safe_filename("???", "json") == "result.json"


def _msg(role, content, query=None, status="ok"):
    return SimpleNamespace(role=role, content=content, query=query, status=status)


def test_history_includes_query_for_successful_assistant_turns_only():
    history = build_history(
        [
            _msg("user", "top singers"),
            _msg("assistant", "Here they are.", query="SELECT name FROM singer"),
            _msg("assistant", "failed", query="SELECT bad", status="failed"),
        ]
    )
    assert history[0] == ("user", "top singers")
    assert "[query used: SELECT name FROM singer]" in history[1][1]
    assert "query used" not in history[2][1]


def test_history_truncates_text_and_query():
    [(_, text)] = build_history([_msg("assistant", "x" * 1000, query="q" * 5000)])
    assert len(text) < HISTORY_TEXT_CHARS + HISTORY_SQL_CHARS + 40


def test_prompt_carries_the_previous_query_for_follow_ups():
    request = QueryRequest(
        question="only those from France",
        schema="TABLE singer (id INTEGER PK, country TEXT)",
        dialect_hint="Write SQL.",
        history=build_history([_msg("assistant", "Done.", query="SELECT * FROM singer")]),
    )
    prompt = OpenAIQueryLLM._build_prompt(request)
    assert "SELECT * FROM singer" in prompt and prompt.rstrip().endswith("only those from France")
