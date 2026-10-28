from evals.scoring import CostMeter, classify, results_match, stratified_sample


def test_match_ignores_row_order_without_order_by():
    assert results_match([(1, "a"), (2, "b")], [(2, "b"), (1, "a")], "SELECT a, b FROM t")


def test_match_respects_order_by():
    assert not results_match([(1,), (2,)], [(2,), (1,)], "SELECT a FROM t ORDER BY a")


def test_match_ignores_column_order_and_float_noise():
    assert results_match([(1, 2.00001)], [(2.0, 1)], "SELECT a, b FROM t")


def test_match_detects_wrong_values_and_shape():
    assert not results_match([(1,)], [(2,)], "SELECT a FROM t")
    assert not results_match([(1,)], [(1, 2)], "SELECT a FROM t")
    assert not results_match([(1,), (1,)], [(1,)], "SELECT a FROM t")


def test_empty_results_match():
    assert results_match([], [], "SELECT a FROM t")


def test_classify():
    assert classify("SELECT a FROM t INTERSECT SELECT a FROM u") == "set_op"
    assert classify("SELECT a FROM t WHERE b > (SELECT AVG(b) FROM t)") == "subquery"
    assert classify("SELECT * FROM a JOIN b ON a.i = b.i") == "join"
    assert classify("SELECT a, COUNT(*) FROM t GROUP BY a") == "group"
    assert classify("SELECT a FROM t") == "simple"


def test_stratified_sample_covers_databases_and_is_deterministic():
    items = [{"db_id": f"db{i % 5}", "n": i} for i in range(100)]
    first = stratified_sample(items, 10, seed=1)
    assert first == stratified_sample(items, 10, seed=1)
    assert {x["db_id"] for x in first} == {f"db{i}" for i in range(5)}
    assert len(stratified_sample(items, 0, seed=1)) == 100


def test_cost_meter():
    meter = CostMeter(0.5, 0.5)
    meter.add(1_000_000, 1_000_000)
    assert meter.cost == 1.0
