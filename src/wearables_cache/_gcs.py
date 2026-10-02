# src/wearables_cache/_gcs.py
"""
Low-level GCS helpers scoped to the shared wearables cache bucket.
All paths passed to these functions are relative to CACHE_BUCKET.
"""
import os
import subprocess
import tempfile

import pandas as pd

from ._constants import CACHE_BUCKET, PIDS_PER_SHARD


# ── Path helpers ───────────────────────────────────────────────────────────────

def _bucket() -> str:
    """Return the cache bucket URI, preferring the live env var over the constant.

    WORKSPACE_CACHE is set by src/utils.py (wb resource list resolution).
    Reading it here at call time avoids import-order issues where _constants.py
    is loaded before utils.py has had a chance to set the env var.
    """
    return os.environ.get("WORKSPACE_CACHE", CACHE_BUCKET)


def cache_gcs(relative_path: str) -> str:
    """Full GCS URI under the shared cache bucket."""
    return f"{_bucket()}/{relative_path}"


def cache_exists(relative_path: str) -> bool:
    """Return True if the GCS object (or any object under a prefix) exists."""
    result = subprocess.run(
        ["gsutil", "ls", cache_gcs(relative_path)],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def cache_ls(prefix: str) -> list[str]:
    """Return sorted list of GCS URIs ending in .parquet under prefix."""
    result = subprocess.run(
        ["gsutil", "ls", cache_gcs(prefix)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(
        line.strip()
        for line in result.stdout.strip().splitlines()
        if line.strip().endswith(".parquet")
    )


# ── Parquet I/O ────────────────────────────────────────────────────────────────

def cache_load(relative_path: str) -> pd.DataFrame:
    """Download a single parquet from the cache bucket and return as DataFrame."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(
            ["gsutil", "cp", cache_gcs(relative_path), tmp],
            check=True, capture_output=True,
        )
        return pd.read_parquet(tmp)
    finally:
        os.unlink(tmp)


def cache_save(df: pd.DataFrame, relative_path: str) -> None:
    """Write a DataFrame to the cache bucket as parquet."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp = f.name
    try:
        df.to_parquet(tmp, index=False)
        subprocess.run(
            ["gsutil", "cp", tmp, cache_gcs(relative_path)],
            check=True, capture_output=True,
        )
    finally:
        os.unlink(tmp)


def cache_save_sentinel(relative_path: str) -> None:
    """Write an empty sentinel file to mark a stage as complete."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(
            ["gsutil", "cp", tmp, cache_gcs(relative_path)],
            check=True, capture_output=True,
        )
    finally:
        os.unlink(tmp)


# ── Shard naming ───────────────────────────────────────────────────────────────

def shard_name(chunk_idx: int) -> str:
    """Zero-padded shard filename, e.g. shard_00000.parquet"""
    return f"shard_{chunk_idx:05d}.parquet"


def build_pid_index(pids: list[int]) -> pd.DataFrame:
    """
    Given the full sorted pid list, return a DataFrame with columns:
        person_id  |  shard_idx
    Chunk 0 = pids[0:1000], chunk 1 = pids[1000:2000], etc.
    """
    pids_sorted = sorted(pids)
    shard_idx = [i // PIDS_PER_SHARD for i in range(len(pids_sorted))]
    return pd.DataFrame({"person_id": pids_sorted, "shard_idx": shard_idx})

