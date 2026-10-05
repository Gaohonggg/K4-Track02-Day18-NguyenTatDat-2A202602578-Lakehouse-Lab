# ---
# jupyter:
#   jupytext:
#     formats: py:percent
# ---

# %% [markdown]
# # NB4 — Medallion Pipeline (Bronze → Silver → Gold), lightweight
#
# **Use case:** LLM observability — exact schema from slide §8 (Lakehouse cho AI/ML) medallion frame.
# Maps to deliverable bullet 4 (the Milestone-1 Lakehouse artifact).
#
# Pre-req: ran `make data` — but if you jumped straight here, the cell below
# generates the Bronze sample for you rather than failing on a missing path.

# %%
import _setup  # noqa: F401  -- adds scripts/ to sys.path
from math import isclose
from pathlib import Path
from statistics import median, quantiles

import polars as pl
import duckdb
from deltalake import DeltaTable, write_deltalake
from lakehouse import path, reset

BRONZE = path("bronze", "llm_calls_raw")
SILVER = path("silver", "llm_calls")
GOLD   = path("gold",   "llm_daily_metrics")

# Self-healing pre-req (same pattern as NB7/NB8). Without this, skipping
# `make data` surfaces as a raw `Os { code: 2, kind: NotFound }` from the Rust
# layer — technically correct, useless to a student.
if not Path(BRONZE).exists():
    print("Bronze not found — running scripts/generate_data_lite.py first ...")
    import generate_data_lite

    generate_data_lite.main()

# %% [markdown]
# ## Bronze — verify raw is loaded

# %%
bronze_n = DeltaTable(BRONZE).to_pyarrow_table().num_rows
print(f"Bronze rows: {bronze_n:,}")
print(pl.from_arrow(DeltaTable(BRONZE).to_pyarrow_table().slice(0, 2)))

# %% [markdown]
# ## Silver — parse, validate, dedup
#
# Rules: drop malformed JSON, dedupe by `request_id`, project typed columns.

# %%
reset(SILVER)

# DuckDB does the JSON parse + dedup in one query — Polars also works,
# DuckDB just has nicer JSON syntax for this case.
# DuckDB reads Delta through Arrow, not through `delta_scan()`. The latter
# autoloads an extension over the network; Arrow registration is offline and
# zero-copy, so the lab works on a locked-down machine.
con = duckdb.connect()
con.register("bronze", DeltaTable(BRONZE).to_pyarrow_table())

silver_arrow = con.sql(f"""
    WITH parsed AS (
      SELECT
        request_id,
        ts,
        CAST(ts AS DATE)                            AS date,
        json_extract_string(raw_json, '$.model')          AS model,
        json_extract_string(raw_json, '$.user_id')        AS user_id,
        CAST(json_extract(raw_json, '$.usage.input')  AS INTEGER) AS prompt_tokens,
        CAST(json_extract(raw_json, '$.usage.output') AS INTEGER) AS completion_tokens,
        CAST(json_extract(raw_json, '$.latency_ms')   AS INTEGER) AS latency_ms,
        json_extract_string(raw_json, '$.status')         AS status,
        ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY ts) AS rn
      FROM bronze
    )
    SELECT request_id, ts, date, model, user_id,
           prompt_tokens, completion_tokens, latency_ms, status
    FROM parsed
    WHERE rn = 1 AND model IS NOT NULL
""").arrow()

write_deltalake(SILVER, silver_arrow, mode="overwrite", partition_by=["date"])

silver_n = DeltaTable(SILVER).to_pyarrow_table().num_rows
print(f"Silver rows: {silver_n:,}  (Bronze {bronze_n:,} → dedup dropped {bronze_n - silver_n:,})")
assert silver_n < bronze_n, (
    "Silver has the same row count as Bronze — dedup did not run. "
    "Did you regenerate Bronze with the latest generator (which injects retries)?"
)

# %% [markdown]
# ## Gold — aggregate to (date, model) metrics

# %%
reset(GOLD)

# Illustrative cost model — NOT canonical pricing.
# (input USD / 1M tokens, output USD / 1M tokens)
COST_TABLE = """
  VALUES
    ('claude-haiku-4-5',  0.80,  4.00),
    ('claude-sonnet-4-6', 3.00, 15.00),
    ('claude-opus-4-7', 15.00, 75.00)
"""

con.register("silver", DeltaTable(SILVER).to_pyarrow_table())
gold_arrow = con.sql(f"""
    WITH cost(model, c_in, c_out) AS ({COST_TABLE})
    SELECT
      s.date,
      s.model,
      QUANTILE_CONT(s.latency_ms, 0.50) AS p50_latency_ms,
      QUANTILE_CONT(s.latency_ms, 0.95) AS p95_latency_ms,
      SUM(s.prompt_tokens)              AS total_prompt_tokens,
      SUM(s.completion_tokens)          AS total_completion_tokens,
      AVG(CASE WHEN s.status <> 'ok' THEN 1.0 ELSE 0.0 END) AS error_rate,
      (SUM(s.prompt_tokens)     * c.c_in  / 1e6) +
      (SUM(s.completion_tokens) * c.c_out / 1e6) AS cost_usd
    FROM silver s
    JOIN cost c USING (model)
    GROUP BY s.date, s.model, c.c_in, c.c_out
    ORDER BY s.date, s.model
""").arrow()

write_deltalake(GOLD, gold_arrow, mode="overwrite", partition_by=["date"])

# Z-order for fast filter-by-model dashboards
DeltaTable(GOLD).optimize.z_order(["model"])

# %% [markdown]
# ## Verify Gold

# %%
gold_df = pl.from_arrow(DeltaTable(GOLD).to_pyarrow_table())
with pl.Config(tbl_rows=-1, tbl_cols=-1):
    print(gold_df.sort(["date", "model"]))

# Slide-5 deliverable: "Gold p50/p95/cost qua ≥ 7 ngày". Make that explicit.
n_dates = gold_df.select("date").n_unique()
n_models = gold_df.select("model").n_unique()
print(
    f"\n──── Gold deliverable metrics ────\n"
    f"  Distinct dates:   {n_dates:>3}   (target ≥ 7)\n"
    f"  Distinct models:  {n_models:>3}\n"
    f"  Total Gold rows:  {gold_df.height:>3}   (= dates × models)"
)
assert n_dates >= 7, (
    f"Gold has only {n_dates} dates — slide deliverable requires ≥ 7. "
    "Re-run `make data` (the generator spreads across 7 UTC days)."
)

# %% [markdown]
# ### Check every date/model pair and metric, not just distinct counts
#
# Expected keys come from Silver dates crossed with the three priced models.
# Missing groups, duplicate keys and unpriced models must fail explicitly.
# A zero error rate is valid; missing or out-of-range values are not.

# %%
con.register("gold", gold_df.to_arrow())
n_silver_dates = con.sql("SELECT count(DISTINCT date) FROM silver").fetchone()[0]
expected_gold_rows = n_silver_dates * 3
missing_pairs = con.sql(f"""
    WITH cost(model, c_in, c_out) AS ({COST_TABLE}),
    expected AS (
        SELECT DISTINCT s.date, c.model FROM silver s CROSS JOIN cost c
    )
    SELECT date, model FROM expected
    EXCEPT SELECT date, model FROM gold
    ORDER BY 1, 2
""").fetchall()
unpriced_rows = con.sql(f"""
    WITH cost(model, c_in, c_out) AS ({COST_TABLE})
    SELECT count(*) FROM silver s LEFT JOIN cost c USING (model)
    WHERE c.model IS NULL
""").fetchone()[0]
duplicate_keys = con.sql("""
    SELECT count(*) FROM (
        SELECT date, model FROM gold GROUP BY 1, 2 HAVING count(*) > 1
    )
""").fetchone()[0]
invalid_metrics = con.sql("""
    SELECT count(*) FROM gold
    WHERE date IS NULL OR model IS NULL
       OR p50_latency_ms IS NULL OR p95_latency_ms IS NULL
       OR NOT isfinite(p50_latency_ms) OR NOT isfinite(p95_latency_ms)
       OR p50_latency_ms < 0 OR p50_latency_ms > p95_latency_ms
       OR cost_usd IS NULL OR NOT isfinite(cost_usd) OR cost_usd <= 0
       OR error_rate IS NULL OR NOT isfinite(error_rate)
       OR error_rate NOT BETWEEN 0 AND 1
       OR total_prompt_tokens IS NULL OR total_prompt_tokens < 0
       OR total_completion_tokens IS NULL OR total_completion_tokens < 0
""").fetchone()[0]
print(f"Missing date/model pairs: {missing_pairs}")
print(f"Expected/actual Gold rows: {expected_gold_rows} / {gold_df.height}")
print(f"Silver rows without a cost model: {unpriced_rows}")
print(f"Duplicate Gold keys: {duplicate_keys}")
print(f"Gold rows with invalid metrics: {invalid_metrics}")

# %% [markdown]
# ### Independently recompute one group's metrics from Silver
#
# Python's inclusive quantiles match continuous percentile interpolation.
# Token costs and error rate are recomputed from raw Silver rows, using the
# lab's illustrative rates. This checks a real group, not production pricing.

# %%
assert gold_df.height > 0, "Gold is empty — no group can be verified"
sample_date, sample_model = gold_df.sort(["date", "model"]).select("date", "model").row(0)
sample_rows = con.execute("""
    SELECT latency_ms, prompt_tokens, completion_tokens, status
    FROM silver WHERE date = ? AND model = ?
""", [sample_date, sample_model]).fetchall()
assert len(sample_rows) >= 2, "The reference group needs at least two latency samples"
c_in, c_out = con.execute(f"""
    WITH cost(model, c_in, c_out) AS ({COST_TABLE})
    SELECT c_in, c_out FROM cost WHERE model = ?
""", [sample_model]).fetchone()
# SQL VALUES can infer DECIMAL rates; normalize for Python arithmetic.
c_in, c_out = float(c_in), float(c_out)
latencies = [row[0] for row in sample_rows]
expected_metrics = {
    "p50_latency_ms": median(latencies),
    "p95_latency_ms": quantiles(latencies, n=100, method="inclusive")[94],
    "total_prompt_tokens": sum(row[1] for row in sample_rows),
    "total_completion_tokens": sum(row[2] for row in sample_rows),
    "error_rate": sum(row[3] is not None and row[3] != "ok" for row in sample_rows) / len(sample_rows),
    "cost_usd": (sum(row[1] for row in sample_rows) * c_in
                 + sum(row[2] for row in sample_rows) * c_out) / 1e6,
}
actual_metrics = con.execute("""
    SELECT p50_latency_ms, p95_latency_ms, total_prompt_tokens,
           total_completion_tokens, error_rate, cost_usd
    FROM gold WHERE date = ? AND model = ?
""", [sample_date, sample_model]).fetchone()
reference_checks = {}
print(f"Reference group: {sample_date} / {sample_model} ({len(sample_rows):,} Silver rows)")
for (metric, expected), actual in zip(expected_metrics.items(), actual_metrics):
    matches = actual is not None and isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    reference_checks[metric] = matches
    print(f"  [{'PASS' if matches else 'FAIL'}] {metric}: Gold={actual}, Python={expected}")

# %% [markdown]
# ## ✅ Deliverable check
# - [ ] All three tables exist under `_lakehouse/{bronze,silver,gold}/`
# - [ ] Silver has fewer rows than Bronze (dedup worked)
# - [ ] Gold spans ≥ 7 dates × 3 models (slide §8 medallion contract)
# - [ ] Unique date/model keys; no missing groups or unpriced Silver models
# - [ ] p50 ≤ p95; cost > 0; error_rate ∈ [0, 1]; metrics finite and non-null
# - [ ] One group's metrics match an independent calculation from Silver

# %%
checks = {
    "Bronze, Silver and Gold have Delta logs": all(
        (Path(table_path) / "_delta_log").is_dir() for table_path in (BRONZE, SILVER, GOLD)
    ),
    "Silver has fewer rows than Bronze": silver_n < bronze_n,
    "Gold spans at least 7 dates and exactly 3 models": n_dates >= 7 and n_models == 3,
    "Gold covers every expected date/model pair": not missing_pairs,
    "Gold has exactly the expected number of groups": gold_df.height == expected_gold_rows,
    "every Silver model has a cost model": unpriced_rows == 0,
    "Gold date/model keys are unique": duplicate_keys == 0,
    "all Gold metrics are valid": invalid_metrics == 0,
    "reference group matches Python calculation": all(reference_checks.values()),
}
for label, passed in checks.items():
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
assert all(checks.values()), "NB4 incomplete — see FAIL rows above"
print("\nNB4 complete.")
