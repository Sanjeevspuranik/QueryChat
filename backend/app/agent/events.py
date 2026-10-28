from typing import Any


def to_events(node: str, update: dict[str, Any], max_retries: int) -> list[dict[str, Any]]:
    """Translate a graph node update into UI-facing stream events."""
    failure = update.get("failure")
    if node == "load_schema" and not failure:
        return [{"type": "status", "message": "Reading database schema"}]
    if node == "generate":
        return [{"type": "query", "query": update["query"]}]
    if node in {"validate", "execute", "load_schema"} and failure:
        attempts = update.get("attempts") or [{}]
        return [{
            "type": "attempt_failed",
            "n": attempts[-1].get("n"),
            "stage": failure["stage"],
            "error": failure["error"],
        }]
    if node == "retry_gate" and update.get("status") == "retrying":
        return [{
            "type": "retrying",
            "retry": update["retry_count"],
            "max_retries": max_retries,
            "message": f"Fixing query (retry {update['retry_count']} of {max_retries})",
        }]
    if node == "execute":
        return [{"type": "status", "message": "Query succeeded, summarizing"}]
    return []
