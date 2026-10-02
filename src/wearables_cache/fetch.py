# src/wearables_cache/fetch.py
"""
Project-facing API for reading from the wearables cache.

Usage
-----
    from src.wearables_cache import fetch_wearables

    hr = fetch_wearables(
        pids       = my_cohort_pids,          # list[int]
        modality   = "hr_hourly",
        date_range = ("2020-01-01", "2022-12-31"),   # optional
    )

The function:
  1. Loads the pid→shard_idx index from GCS (cached in RAM for the session)
  2. Identifies the minimal set of shard files needed for the requested pids
  3. Downloads only those shards (parallel gsutil -m cp, in batches)
  4. Uses DuckDB to filter pids and date range directly on local parquet files,
     never materialising the full dataset in pandas RAM
  5. Returns a clean, typed DataFrame

No BigQuery is touched.
"""

import os
import subprocess
import tempfile
from typing import Iterator, Optional

import duckdb
import pandas as pd
from tqdm.auto import tqdm

from ._constants import (
    CACHE_BUCKET,
    CACHE_PREFIX,
    META_INDEX_PATH,
    MODALITIES,
    SCHEMA,
)
from ._gcs import cache_gcs, cache_load, shard_name


# ── Index cache (loaded once per Python session) ───────────────────────────────

_INDEX: Optional[pd.DataFrame] = None

def _load_index() -> pd.DataFrame:
    global _INDEX
    if _INDEX is None:
        print("Loading pid→shard index from GCS (once per session) ...")
        _INDEX = cache_load(META_INDEX_PATH)
    return _INDEX


# ── Core fetch ─────────────────────────────────────────────────────────────────

def fetch_wearables(
    pids: list[int],
    modality: str,
    date_range: Optional[tuple] = None,
    batch_size: int = 10,
) -> pd.DataFrame:
    """
    Fetch wearables data for a list of pids from the shared cache.

    Parameters
    ----------
    pids        : list of person_id integers
    modality    : one of 'hr_hourly', 'steps_hourly',
                          'sleep_summary', 'sleep_onset_offset'
    date_range  : optional (start, end) tuple of date strings or datetime-likes.
                  Applied to 'date' column for hourly modalities,
                  'night_date' for sleep_onset_offset,
                  'sleep_date' for sleep_summary.
    batch_size  : number of shards per gsutil -m cp call (default 10).

    Returns
    -------
    pd.DataFrame with columns per SCHEMA[modality], filtered to exact pids.

    Memory notes
    ------------
    DuckDB reads and filters the local parquet files without ever loading all
    shards into Python/pandas RAM. Only the final filtered result is
    materialised as a DataFrame. This keeps peak RAM proportional to the
    *output* size, not to the total size of all downloaded shards.
    """
    if modality not in MODALITIES:
        raise ValueError(f"Unknown modality '{modality}'. Choose from {MODALITIES}")

    pids_set = set(pids)
    if not pids_set:
        raise ValueError("pids list is empty.")

    # ── Resolve shard indices for requested pids ───────────────────────────────
    index_df = _load_index()
    matched = index_df[index_df["person_id"].isin(pids_set)]

    unmatched = pids_set - set(matched["person_id"].tolist())
    if unmatched:
        print(
            f"  ⚠️  {len(unmatched):,} requested pids not found in index "
            f"(no fitbit data). They will be absent from the result."
        )

    shard_indices = sorted(matched["shard_idx"].unique().tolist())
    print(
        f"  Fetching {modality} for {len(pids_set):,} pids "
        f"→ {len(shard_indices)} shard(s)"
    )

    if not shard_indices:
        return _empty_df(modality)

    # ── Download required shards in parallel batches ───────────────────────────
    cache_prefix = CACHE_PREFIX[modality]
    gcs_paths = [
        cache_gcs(f"{cache_prefix}{shard_name(idx)}")
        for idx in shard_indices
    ]

    with tempfile.TemporaryDirectory() as tmpdir:

        # Download in batches to avoid gsutil stdin truncation issues
        for i in range(0, len(gcs_paths), batch_size):
            batch = gcs_paths[i : i + batch_size]
            subprocess.run(
                ["gsutil", "-m", "-q", "cp"] + batch + [tmpdir],
                check=True,
                capture_output=True,
            )

        # ── Filter with DuckDB — no full-dataset materialisation in pandas ─────
        df = _duckdb_filter(
            tmpdir      = tmpdir,
            shard_indices = shard_indices,
            pids_set    = pids_set,
            modality    = modality,
            date_range  = date_range,
        )

    if df.empty:
        return _empty_df(modality)

    # ── Enforce schema dtypes ──────────────────────────────────────────────────
    df = _cast_schema(df, modality)

    print(f"  Returned {len(df):,} rows for {df['person_id'].nunique():,} pids.")
    return df.reset_index(drop=True)


# ── Streaming shard iterator ───────────────────────────────────────────────────

def iter_wearables_shards(
    pids: list[int],
    modality: str,
) -> Iterator[pd.DataFrame]:
    """
    Yield one filtered DataFrame per shard (memory-safe alternative to fetch_wearables).

    Downloads one shard at a time, applies pyarrow predicate pushdown to extract
    only the requested pids, then deletes the shard file before yielding. Peak RAM
    per iteration = one shard's worth of data for the matched pids (typically a few
    MB), regardless of how many shards exist in total.

    Use this instead of fetch_wearables for large modalities (steps_hourly,
    hr_hourly) when aggregating to a lower resolution immediately after loading:

        chunks = []
        for shard_df in iter_wearables_shards(pids, 'hr_hourly'):
            chunks.append(aggregate(shard_df))
            del shard_df; gc.collect()
        result = pd.concat(chunks, ignore_index=True)

    Pyarrow predicate pushdown is effective here because shards are sorted by
    person_id, so matched row groups cluster at the start/end of each shard file.
    """
    if modality not in MODALITIES:
        raise ValueError(f"Unknown modality '{modality}'. Choose from {MODALITIES}")

    pids_set = set(pids)
    if not pids_set:
        return

    index_df   = _load_index()
    matched    = index_df[index_df["person_id"].isin(pids_set)]
    shard_idxs = sorted(matched["shard_idx"].unique().tolist())

    unmatched = pids_set - set(matched["person_id"].tolist())
    if unmatched:
        print(f"  ⚠️  {len(unmatched):,} pids not in cache index — absent from results.")

    print(f"  Streaming {modality} for {len(pids_set):,} pids "
          f"→ {len(shard_idxs)} shard(s)")

    cache_prefix = CACHE_PREFIX[modality]
    pids_sorted  = sorted(pids_set)

    skipped = 0
    for idx in tqdm(shard_idxs, desc=modality):
        gcs_path = cache_gcs(f"{cache_prefix}{shard_name(idx)}")
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp = f.name
        try:
            subprocess.run(
                ["gsutil", "-q", "cp", gcs_path, tmp],
                check=True, capture_output=True,
            )
            shard_df = pd.read_parquet(
                tmp,
                filters=[("person_id", "in", pids_sorted)],
            )
        except subprocess.CalledProcessError:
            # Shard absent from GCS (PID space extends beyond what was populated
            # during cache build, or transient error). Skip and warn.
            skipped += 1
            tqdm.write(f"  ⚠️  shard_{idx:05d} not found — skipping.")
            continue
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

        if shard_df.empty:
            continue

        yield _cast_schema(shard_df, modality)

    if skipped:
        print(f"  ⚠️  {skipped} shard(s) were absent from the cache and skipped.")


# ── DuckDB filter (RAM-efficient) ──────────────────────────────────────────────

def _duckdb_filter(
    tmpdir: str,
    shard_indices: list[int],
    pids_set: set,
    modality: str,
    date_range: Optional[tuple],
) -> pd.DataFrame:
    """
    Use DuckDB to read, filter, and return only the rows we need.

    DuckDB streams the parquet files from local disk — it never pulls all
    shards into Python heap simultaneously. Peak RAM = size of filtered output.
    """
    # Build the glob pattern covering only the shards we downloaded
    pattern = os.path.join(tmpdir, "*.parquet")

    # Pass the pid list to DuckDB as a small in-memory relation
    pids_df = pd.DataFrame({"person_id": sorted(pids_set)})

    con = duckdb.connect()
    con.register("wanted_pids", pids_df)

    # Build optional date predicate
    date_predicate = ""
    if date_range is not None:
        col   = _date_col(modality)
        start = pd.to_datetime(date_range[0]).date()
        end   = pd.to_datetime(date_range[1]).date()
        date_predicate = f"AND CAST(raw.{col} AS DATE) BETWEEN '{start}' AND '{end}'"

    sql = f"""
        SELECT raw.*
        FROM read_parquet('{pattern}') AS raw
        INNER JOIN wanted_pids
            ON raw.person_id = wanted_pids.person_id
        WHERE 1=1
        {date_predicate}
    """

    df = con.execute(sql).df()
    con.close()
    return df


# ── Helpers ────────────────────────────────────────────────────────────────────

def _date_col(modality: str) -> str:
    return {
        "hr_hourly":          "date",
        "steps_hourly":       "date",
        "sleep_summary":      "sleep_date",
        "sleep_onset_offset": "night_date",
    }[modality]


def _cast_schema(df: pd.DataFrame, modality: str) -> pd.DataFrame:
    schema = SCHEMA[modality]
    for col, dtype in schema.items():
        if col not in df.columns:
            continue
        if "datetime" in dtype:
            df[col] = pd.to_datetime(df[col]).astype(dtype)
        else:
            df[col] = df[col].astype(dtype)
    return df


def _empty_df(modality: str) -> pd.DataFrame:
    return pd.DataFrame(columns=list(SCHEMA[modality].keys()))