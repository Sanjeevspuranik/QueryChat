"""Spider execution-accuracy eval for the QueryChat agent.

Run from the backend directory, e.g.:
  python -m evals.run_spider --gold-check --sample 0            # no LLM, free
  python -m evals.run_spider --sample 60 --max-retries 0        # cheap pilot
  python -m evals.run_spider --sample 200 --max-retries 3 --max-cost 0.50

The agent graph is invoked directly (no HTTP/auth), so the validator and the
correction loop behave exactly as in the app. The summary LLM call is skipped:
it cannot be scored against Spider's gold SQL and costs extra tokens.
"""
import argparse
import asyncio
import json
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.adapters.base import ExecutionLimits
from app.adapters.sql import SqlAdapter
from app.agent.graph import RECURSION_LIMIT, build_agent_graph
from app.agent.llm import _FENCE, _SYSTEM, OpenAIQueryLLM
from app.agent.nodes import AgentNodes
from app.agent.state import QueryRequest
from app.core.config import Settings
from evals.scoring import CostMeter, classify, results_match, stratified_sample

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA = BACKEND_DIR.parent / "spider_data"
# The app caps results at 1000 rows; scoring needs full result sets or big gold results mismatch.
LIMITS = ExecutionLimits(max_rows=1_000_000)


class MeteredLLM(OpenAIQueryLLM):
    """Records token usage per question and skips the (unscored) summary call."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.calls = 0

    async def generate_query(self, request: QueryRequest) -> str:
        reply = await self._smart.ainvoke([("system", _SYSTEM), ("human", self._build_prompt(request))])
        usage = getattr(reply, "usage_metadata", None) or {}
        self.calls += 1
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.reasoning_tokens += (usage.get("output_token_details") or {}).get("reasoning", 0)
        return _FENCE.sub("", str(reply.content).strip()).strip().rstrip(";")

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str:
        return ""


def db_path(data: Path, db_id: str, split: str) -> Path:
    return data / split / db_id / f"{db_id}.sqlite"


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def run_gold(path: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    conn.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


async def gold_check(item: dict[str, Any], data: Path, split: str) -> dict[str, Any]:
    """Does the app's own validator + executor accept the gold SQL?"""
    record = base_record(item)
    adapter = SqlAdapter(sqlite_url(db_path(data, item["db_id"], split)), LIMITS)
    try:
        await adapter.connect()
        adapter.validate(item["query"])
        result = await adapter.execute(item["query"])
        gold = run_gold(db_path(data, item["db_id"], split), item["query"])
        record.update(status="ok", correct=results_match(gold, result.rows, item["query"]))
    except Exception as exc:  # noqa: BLE001 - every failure is a finding
        record.update(status="failed", correct=False, error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        await adapter.close()
    return record


def base_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "idx": item["_idx"],
        "db_id": item["db_id"],
        "category": classify(item["query"]),
        "question": item["question"],
        "gold": item["query"],
    }


async def evaluate(
    item: dict[str, Any], settings: Settings, args: argparse.Namespace, data: Path, meter: CostMeter
) -> dict[str, Any]:
    record = base_record(item)
    path = db_path(data, item["db_id"], args.split)
    adapter = SqlAdapter(sqlite_url(path), LIMITS)
    llm = MeteredLLM(settings.openai_api_key, args.model, args.model, settings.llm_timeout_seconds)
    started = time.monotonic()
    try:
        await adapter.connect()
        graph = build_agent_graph(AgentNodes(llm, adapter, args.max_retries))
        state = await asyncio.wait_for(
            graph.ainvoke(
                {"question": item["question"], "history": [], "attempts": [], "retry_count": 0},
                config={"recursion_limit": RECURSION_LIMIT},
            ),
            timeout=args.question_timeout,
        )
        attempts = state.get("attempts", [])
        record.update(
            status=state.get("status", "failed"),
            pred=state.get("query", ""),
            attempts=len(attempts),
            failures=[a["stage"] for a in attempts if a["stage"] != "executed"],
        )
        if state.get("status") == "ok":
            gold = run_gold(path, item["query"])
            record["correct"] = results_match(gold, state["result"]["rows"], item["query"])
        else:
            record["correct"] = False
            record["error"] = (state.get("failure") or {}).get("error", "")[:300]
    except Exception as exc:  # noqa: BLE001 - one bad question must not kill the batch
        record.update(status="error", correct=False, error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        await adapter.close()
    meter.add(llm.input_tokens, llm.output_tokens)
    record.update(
        input_tokens=llm.input_tokens,
        output_tokens=llm.output_tokens,
        reasoning_tokens=llm.reasoning_tokens,
        llm_calls=llm.calls,
        ms=int((time.monotonic() - started) * 1000),
    )
    return record


def load_done(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    done = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            done[rec["idx"]] = rec
    return done


def report(records: list[dict[str, Any]], meter: CostMeter, gold_mode: bool) -> None:
    total = len(records)
    if not total:
        print("No results.")
        return
    correct = sum(r["correct"] for r in records)
    print(f"\nQuestions: {total}   Accuracy: {correct}/{total} = {correct / total:.1%}")

    def table(title: str, key: str) -> None:
        groups: dict[str, list[bool]] = defaultdict(list)
        for r in records:
            groups[r[key]].append(r["correct"])
        print(f"\nBy {title}:")
        for name, vals in sorted(groups.items()):
            print(f"  {name:<32} {sum(vals):>4}/{len(vals):<4} {sum(vals) / len(vals):.0%}")

    table("category", "category")
    table("database", "db_id")
    if gold_mode:
        errors = [r for r in records if r["status"] != "ok"]
        print(f"\nGold SQL rejected/failed by the app: {len(errors)}")
        for r in errors[:15]:
            print(f"  [{r['db_id']}] {r.get('error', '')[:140]}")
        return

    attempts = Counter(r.get("attempts", 0) for r in records)
    print(f"\nAttempts per question: {dict(sorted(attempts.items()))}")
    stages = Counter(s for r in records for s in r.get("failures", []))
    print(f"Failed-attempt stages: {dict(stages)}")
    print(f"Final status: {dict(Counter(r['status'] for r in records))}")
    retried = [r for r in records if r.get("attempts", 0) > 1]
    if retried:
        fixed = sum(r["correct"] for r in retried)
        print(f"Retried questions: {len(retried)}, ended correct: {fixed}")
    print(f"Median latency: {statistics.median(r['ms'] for r in records) / 1000:.1f}s")
    reasoning = sum(r.get("reasoning_tokens", 0) for r in records)
    print(
        f"\nTokens in/out: {meter.input_tokens:,} / {meter.output_tokens:,} "
        f"(reasoning included in out: {reasoning:,})"
    )
    print(f"Avg tokens/question: {(meter.input_tokens + meter.output_tokens) / total:,.0f}")
    print(f"Cost (this run's records): ${meter.cost:.4f}")
    wrong = [r for r in records if not r["correct"]]
    print(f"\nWrong answers ({len(wrong)}); first 5 for review:")
    for r in wrong[:5]:
        print(f"  [{r['db_id']}] {r['question']}\n    gold: {r['gold']}\n    pred: {r.get('pred', '')}")


async def main(args: argparse.Namespace) -> None:
    settings = Settings()
    data = Path(args.data).resolve()
    questions = json.loads((data / args.file).read_text(encoding="utf-8"))
    for i, item in enumerate(questions):
        item["_idx"] = i
    if args.db:
        questions = [q for q in questions if q["db_id"] in args.db]
    items = stratified_sample(questions, args.sample, args.seed)
    gold_mode = args.gold_check
    if not gold_mode and not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set in backend/.env")

    model = args.model or settings.llm_model
    args.model = model
    out = Path(args.out or BACKEND_DIR / "evals" / "results" / f"spider_{'gold' if gold_mode else model}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out) if args.resume else {}
    if not args.resume and out.exists():
        out.unlink()
    todo = [i for i in items if i["_idx"] not in done]
    print(
        f"{'Gold check' if gold_mode else f'Model {model}, max_retries={args.max_retries}'}: "
        f"{len(items)} questions ({len(done)} resumed, {len(todo)} to run) -> {out}"
    )

    meter = CostMeter(args.price_in, args.price_out)
    for rec in done.values():
        meter.add(rec.get("input_tokens", 0), rec.get("output_tokens", 0))
    results = list(done.values())
    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()
    stopped = False

    async def worker(item: dict[str, Any]) -> None:
        nonlocal stopped
        async with sem:
            if not gold_mode and meter.cost >= args.max_cost:
                stopped = True
                return
            rec = await (gold_check(item, data, args.split) if gold_mode else evaluate(item, settings, args, data, meter))
        async with lock:
            results.append(rec)
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
            if len(results) % 10 == 0:
                print(f"  {len(results)}/{len(items)}  acc so far {sum(r['correct'] for r in results) / len(results):.1%}  spend ${meter.cost:.4f}")

    await asyncio.gather(*(worker(i) for i in todo))
    if stopped:
        print(f"\nStopped early: --max-cost ${args.max_cost:.2f} reached (small overshoot possible with concurrency).")
    report(sorted(results, key=lambda r: r["idx"]), meter, gold_mode)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(DEFAULT_DATA), help="Spider directory")
    p.add_argument("--file", default="dev.json", help="question file inside --data")
    p.add_argument("--split", default="database", help="database folder (database | test_database)")
    p.add_argument("--sample", type=int, default=60, help="stratified sample size; 0 = all")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--db", nargs="*", help="only these db_ids")
    p.add_argument("--model", default="", help="defaults to LLM_MODEL from .env")
    p.add_argument("--max-retries", type=int, default=0, help="agent correction retries (0-5)")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--question-timeout", type=int, default=180, help="seconds per question")
    p.add_argument("--max-cost", type=float, default=0.50, help="stop starting new questions past this USD spend")
    p.add_argument("--price-in", type=float, default=0.5, help="USD per 1M input tokens")
    p.add_argument("--price-out", type=float, default=0.5, help="USD per 1M output tokens")
    p.add_argument("--gold-check", action="store_true", help="validate/execute gold SQL through the app; no LLM calls")
    p.add_argument("--resume", action="store_true", help="append to --out, skipping finished questions")
    p.add_argument("--out", default="", help="JSONL results path")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
