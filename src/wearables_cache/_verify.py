# src/wearables_cache/_verify.py
"""
Verification stage: confirm that the pid-sorted cache shards are complete.

Two checks per modality
-----------------------
1. Row count    : total rows across all cache shards (informational)
2. PID coverage : every pid in index_df appears in at least one cache shard,
                  and no unexpected pids are present
"""

import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import duckdb
import gcsfs
import pandas as pd
import pyarrow.parquet as pq
from tqdm.auto import tqdm

from ._constants import CACHE_PREFIX, VERIFIED_SENTINEL
from ._gcs import cache_exists, cache_gcs, cache_save_sentinel

_GCS_THREADS = 64


def _count_rows_via_footers(gcs_prefix_uri: str, label: str) -> int:
    """
    Count parquet rows by reading only file footers — no column data downloaded.
    """
    fs    = gcsfs.GCSFileSystem()
    files = fs.glob(f"{gcs_prefix_uri}*.parquet")

    if not files:
        print(f"  {label}: 0 rows (no files found)")
        return 0

    def _row_count(path: str) -> int:
        with fs.open(path, "rb") as fh:
            return pq.read_metadata(fh).num_rows

    total = 0
    with ThreadPoolExecutor(max_workers=_GCS_THREADS) as pool:
        for n in tqdm(
            pool.map(_row_count, files),
            total=len(files),
            desc=f"  {label} footers",
            leave=False,
        ):
            total += n

    print(f"  {label}: {total:,} rows ({len(files):,} files)")
    return total


def _get_cache_pids(cache_prefix_uri: str, tmpdir: str) -> set:
    """Download all cache shards and return the set of distinct person_ids."""
    subprocess.run(
        ["gsutil", "-m", "-q", "cp", f"{cache_prefix_uri}*.parquet", tmpdir],
        check=True, capture_output=True,
    )
    pattern = os.path.join(tmpdir, "*.parquet")
    con  = duckdb.connect()
    rows = con.execute(
        f"SELECT DISTINCT person_id FROM read_parquet('{pattern}')"
    ).fetchall()
    con.close()
    return {r[0] for r in rows}


def verify_modality(
    modality: str,
    index_df: pd.DataFrame,
    force: bool = False,
) -> bool:
    """
    Run verification for one modality.  Returns True if both checks pass.
    Writes a sentinel file to GCS on success so re-runs skip this stage.
    """
    sentinel = VERIFIED_SENTINEL[modality]

    if not force and cache_exists(sentinel):
        print(f"[{modality}] Verification sentinel found — skipping.")
        return True

    print(f"[{modality}] Running verification ...")

    cache_prefix_gcs = cache_gcs(CACHE_PREFIX[modality])

    # ── Check 1: row count (informational) ────────────────────────────────────
    print("  Counting rows in cache shards ...")
    cache_count = _count_rows_via_footers(cache_prefix_gcs, "cache")

    # ── Check 2: PID coverage ──────────────────────────────────────────────────
    print("  Checking PID coverage ...")
    expected_pids = set(index_df["person_id"].tolist())

    with tempfile.TemporaryDirectory() as cache_tmpdir:
        try:
            cache_pids = _get_cache_pids(cache_prefix_gcs, cache_tmpdir)
        except subprocess.CalledProcessError as e:
            print(f"[{modality}] ❌ Failed to download cache shards: {e}")
            return False

    phantom = cache_pids - expected_pids
    if phantom:
        print(
            f"[{modality}] ❌ {len(phantom):,} unexpected pids in cache."
        )
        return False

    missing          = expected_pids - cache_pids
    missing_fraction = len(missing) / len(expected_pids)
    print(
        f"  PIDs in cache : {len(cache_pids):,} / {len(expected_pids):,}  "
        f"({100 * (1 - missing_fraction):.1f}% coverage)"
    )

    if modality in ("hr_hourly", "steps_hourly") and missing_fraction > 0.02:
        print(
            f"[{modality}] ⚠️  More than 2% of pids missing from cache — investigate."
        )

    print(f"  ✓ No phantom pids.  Total cache rows: {cache_count:,}")
    cache_save_sentinel(sentinel)
    print(f"[{modality}] ✅ Verification passed. Sentinel written.")
    return True
