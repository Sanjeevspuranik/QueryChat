import pytest

from app.adapters.base import ExecutionLimits, sanitize_error
from app.adapters.mongo import MongoAdapter
from app.adapters.sql import SqlAdapter
from app.adapters.url_policy import UrlPolicy
from app.core.errors import QueryValidationError, SecurityViolationError, UnsupportedDatabaseError

LIMITS = ExecutionLimits()
sql = SqlAdapter("sqlite:///x.db", LIMITS)
mongo = MongoAdapter("mongodb://localhost/db", LIMITS)


@pytest.mark.parametrize("query", [
    "SELECT * FROM t",
    "WITH a AS (SELECT 1) SELECT * FROM a",
    "SELECT 1 UNION SELECT 2",
])
def test_sql_allows_reads(query):
    sql.validate(query)


@pytest.mark.parametrize("query", [
    "DROP TABLE t",
    "DELETE FROM t",
    "UPDATE t SET a=1",
    "INSERT INTO t VALUES (1)",
    "WITH a AS (DELETE FROM t RETURNING *) SELECT * FROM a",
    "SELECT * INTO new_t FROM t",
    "PRAGMA writable_schema=1",
])
def test_sql_blocks_writes(query):
    with pytest.raises(SecurityViolationError):
        sql.validate(query)


def test_sql_rejects_multiple_statements():
    with pytest.raises(QueryValidationError):
        sql.validate("SELECT 1; SELECT 2")


def test_mongo_allows_read_pipeline():
    mongo.validate('{"collection": "c", "pipeline": [{"$match": {"a": 1}}, {"$group": {"_id": "$a"}}]}')


@pytest.mark.parametrize("query", [
    '{"collection": "c", "pipeline": [{"$out": "x"}]}',
    '{"collection": "c", "pipeline": [{"$match": {"$where": "sleep(1)"}}]}',
    '{"collection": "c", "pipeline": [{"$merge": {"into": "x"}}]}',
])
def test_mongo_blocks_dangerous_operators(query):
    with pytest.raises(SecurityViolationError):
        mongo.validate(query)


def test_mongo_rejects_bad_shape():
    with pytest.raises(QueryValidationError):
        mongo.validate("not json")
    with pytest.raises(QueryValidationError):
        mongo.validate('{"collection": "c"}')


def test_sanitize_error_hides_credentials():
    msg = sanitize_error("failed postgresql://user:secret@host/db", "")
    assert "secret" not in msg


async def test_policy_rejects_vector_stores_and_private_hosts():
    policy = UrlPolicy(allow_private_hosts=False)
    with pytest.raises(UnsupportedDatabaseError):
        await policy.check("pinecone://key@index")
    with pytest.raises(UnsupportedDatabaseError):
        await policy.check("postgresql://u:p@127.0.0.1/db")
    with pytest.raises(UnsupportedDatabaseError):
        await policy.check("sqlite:///x.db")  # no allowed dir configured
    with pytest.raises(UnsupportedDatabaseError):
        await policy.check("not-a-url")


async def test_policy_dev_mode_allows_local():
    await UrlPolicy(allow_private_hosts=True).check("postgresql://u:p@127.0.0.1/db")
