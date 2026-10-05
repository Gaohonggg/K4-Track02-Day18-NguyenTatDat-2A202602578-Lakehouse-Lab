# ---
# jupyter:
#   jupytext:
#     formats: py:percent
# ---

# %% [markdown]
# # NB1 — Delta Lake Basics (lightweight path)
#
# **Stack:** `deltalake` (delta-rs) + Polars + DuckDB. No Spark, no JVM.
# Maps to slide §2 (Delta Lake) + deliverable bullet 1.
#
# > Spark equivalent: `spark.read.format("delta").load(path)` ↔ `DeltaTable(path).to_pyarrow_table()`.
# > Same on-disk format, different binding.

# %%
import _setup  # noqa: F401  -- adds scripts/ to sys.path (file-relative)
import json
from pathlib import Path

import polars as pl
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import SchemaMismatchError
from lakehouse import path, reset

table_path = path("scratch", "users_delta")
reset(table_path)  # idempotent rerun

# %% [markdown]
# ## 1. Write a Delta table

# %%
df = pl.DataFrame({
    "id": [1, 2, 3],
    "name": ["alice", "bob", "charlie"],
    "age": [30, 25, 35],
    "city": ["Hanoi", "HCMC", "Danang"],
})
write_deltalake(table_path, df.to_arrow(), mode="overwrite")

# %% [markdown]
# ## 2. Read it back + inspect transaction log
#
# Look at `_lakehouse/scratch/users_delta/_delta_log/00000000000000000000.json` —
# that's the transaction log. Same JSON format Spark/Databricks would write.

# %%
dt = DeltaTable(table_path)
print(pl.from_arrow(dt.to_pyarrow_table()))
print("\nHistory:")
for h in dt.history():
    print(f"  v{h['version']}  {h['operation']}  {h.get('operationMetrics', {})}")

initial_log = sorted((Path(table_path) / "_delta_log").glob("*.json"))
print("\nTransaction log files:")
for commit in initial_log:
    print(f"  {commit.name}")
print(f"\nCommit JSON: {initial_log[0].name}")
for line in initial_log[0].read_text(encoding="utf-8").splitlines():
    print(json.dumps(json.loads(line), indent=2, ensure_ascii=False))

# %% [markdown]
# ## 3. Schema enforcement — try to write a wrong schema

# %%
bad = pl.DataFrame({"id": [4], "name": ["dan"], "age": ["thirty"], "city": ["Hue"]})
before_bad_write = DeltaTable(table_path)
version_before = before_bad_write.version()
rows_before = pl.from_arrow(before_bad_write.to_pyarrow_table()).sort("id")
schema_enforced = False
try:
    write_deltalake(table_path, bad.to_arrow(), mode="append")
except Exception as e:
    # Bindings can expose schema/cast failures through different exception
    # classes. Unrelated failures (e.g. I/O) must not count as enforcement.
    message = str(e)
    if not (isinstance(e, SchemaMismatchError)
            or "schema" in message.lower() or "cast" in message.lower()):
        raise
    schema_enforced = True
    print(f"BLOCKED by schema enforcement (expected): {type(e).__name__}: {message}")

after_bad_write = DeltaTable(table_path)
rows_after = pl.from_arrow(after_bad_write.to_pyarrow_table()).sort("id")
bad_write_unchanged = (
    after_bad_write.version() == version_before
    and rows_after.schema == rows_before.schema
    and rows_after.equals(rows_before)
)
print(f"Version before/after bad write: {version_before} → {after_bad_write.version()}")
print(f"Rows before/after bad write: {rows_before.height} → {rows_after.height}")
print(f"Schema and row values unchanged: {bad_write_unchanged}")
assert schema_enforced, "Bad-schema append unexpectedly succeeded"
assert bad_write_unchanged, "Rejected append changed the table version, schema or data"

# %% [markdown]
# ## 4. Schema evolution (opt-in)

# %%
new = pl.DataFrame({
    "id": [4], "name": ["dan"], "age": [28], "city": ["Hue"], "tier": ["premium"],
})
write_deltalake(table_path, new.to_arrow(), mode="append", schema_mode="merge")
dt = DeltaTable(table_path)
# Sort by id so the printout is stable across reruns — Delta does not
# preserve write-order across appends.
print(pl.from_arrow(dt.to_pyarrow_table()).sort("id"))

# %% [markdown]
# ## 5. Query with DuckDB via Arrow (part of the required notebook)

# %%
import duckdb

# We hand DuckDB an Arrow table rather than calling `delta_scan()`. delta_scan
# autoloads a DuckDB extension over the network — fine at home, a support
# ticket in a firewalled classroom. Arrow registration is zero-copy and offline.
con = duckdb.connect()
con.register("users", DeltaTable(table_path).to_pyarrow_table())
tier_counts = con.sql("SELECT tier, count(*) AS n FROM users GROUP BY 1 ORDER BY 1").fetchall()
print(tier_counts)

# %% [markdown]
# ## ✅ Deliverable check
# - [ ] `_delta_log/` contains JSON files
# - [ ] Schema enforcement blocked the bad write
# - [ ] schema_mode="merge" added the `tier` column
# - [ ] DuckDB query returned 2 tier groups
# Enforcement is checked against the actual failure and the table state
# captured immediately before and after the bad write.

# %%
_log = sorted(Path(table_path).glob("_delta_log/*.json"))
_cols = DeltaTable(table_path).schema().to_arrow().names
print("Final transaction log files:", [commit.name for commit in _log])
checks = {
    "_delta_log/ has JSON commits": len(_log) >= 2,
    "schema enforcement blocked bad write": schema_enforced,
    "rejected write left version, schema and data unchanged": bad_write_unchanged,
    "tier column added via schema_mode=merge": "tier" in _cols,
    "duckdb sees 2 tier groups": len(tier_counts) == 2,
}
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
assert all(checks.values()), "NB1 incomplete — see FAIL rows above"
print("\nNB1 complete.")
