"""Pure helpers for the Spider eval: result comparison, sampling, difficulty buckets, cost."""
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

_SET_OPS = re.compile(r"\b(INTERSECT|EXCEPT|UNION)\b", re.IGNORECASE)
_ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)


def _norm(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, str):
        return value.strip()
    return value


def _sort_key(value: Any) -> tuple[str, str]:
    return (type(value).__name__, repr(value))


def results_match(gold_rows: Sequence[Sequence[Any]], pred_rows: Sequence[Sequence[Any]], gold_sql: str) -> bool:
    """Execution accuracy. Column order and aliases are ignored; row order only
    matters when the gold query has an ORDER BY."""
    if len(gold_rows) != len(pred_rows):
        return False
    if gold_rows and len(gold_rows[0]) != len(pred_rows[0]):
        return False

    def columns(rows: Sequence[Sequence[Any]]) -> list[list[Any]]:
        cols = [[_norm(v) for v in col] for col in zip(*rows)] if rows else []
        if not _ORDER_BY.search(gold_sql):
            cols = [sorted(col, key=_sort_key) for col in cols]
        return sorted(cols, key=lambda c: [_sort_key(v) for v in c])

    return columns(gold_rows) == columns(pred_rows)


def classify(gold_sql: str) -> str:
    upper = gold_sql.upper()
    if _SET_OPS.search(gold_sql):
        return "set_op"
    if upper.count("SELECT") > 1:
        return "subquery"
    if "JOIN" in upper:
        return "join"
    if "GROUP BY" in upper:
        return "group"
    return "simple"


def stratified_sample(items: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    """Round-robin across databases (shuffled with a fixed seed) so small samples
    still cover many schemas. size <= 0 returns everything."""
    if size <= 0 or size >= len(items):
        return list(items)
    rng = random.Random(seed)
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_db[item["db_id"]].append(item)
    for group in by_db.values():
        rng.shuffle(group)
    order = sorted(by_db)
    rng.shuffle(order)
    picked: list[dict[str, Any]] = []
    while len(picked) < size:
        progressed = False
        for db in order:
            if by_db[db] and len(picked) < size:
                picked.append(by_db[db].pop())
                progressed = True
        if not progressed:
            break
    return picked


@dataclass
class CostMeter:
    """Accumulates token usage and prices it. Reasoning tokens are already part of
    output_tokens in OpenAI usage, so they are not added twice."""

    price_in_per_m: float
    price_out_per_m: float
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def cost(self) -> float:
        return (self.input_tokens * self.price_in_per_m + self.output_tokens * self.price_out_per_m) / 1_000_000
