# src/wearables_cache/build_cache.py
"""
Orchestrator for the one-time wearables cache build.

Usage (from notebook 00_build_cache.ipynb)
------------------------------------------
    from src.wearables_cache import run_pipeline
    from src.utils import client, DATASET

    for modality in ["sleep_summary", "sleep_onset_offset", "steps_hourly", "hr_hourly"]:
        run_pipeline(modality=modality, client=client, dataset=DATASET)

Architecture
------------
For each modality, one BQ query per shard (~1000 pids) fetches data directly
from the CDR clustered table and writes a parquet shard to the GCS cache.
Because CDR tables are clustered by person_id, BQ reads only the relevant
cluster blocks — not the full table.

Crash-safety
------------
Each shard is checkpointed: if it already exists in GCS it is skipped on
re-run.  Bootstrap meta files are also checkpointed.  The verify sentinel
prevents re-verification on clean re-runs.
"""

import json
import os
import subprocess

import pandas as pd
from google.cloud import bigquery
from tqdm.auto import tqdm

from ._constants import (
    META_PIDS_PATH,
    META_COVERAGE_PATH,
    META_INDEX_PATH,
    CACHE_PREFIX,
    VERIFIED_SENTINEL,
    MODALITIES,
    PIDS_PER_SHARD,
)
from ._gcs import (
    cache_exists,
    cache_load,
    cache_ls,
    cache_save,
    build_pid_index,
    shard_name,
    _bucket,
)
from ._bq_pulls import export_shard
from ._verify import verify_modality


# ── Meta bootstrap (run once, shared by all modalities) ───────────────────────

def bootstrap_meta(
    client: bigquery.Client,
    dataset: str,
    overwrite: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Ensure fitbit_pids, fitbit_coverage, and shard index are in GCS meta/.
    Returns (pids_df, coverage_df, index_df).
    """
    if not overwrite and cache_exists(META_PIDS_PATH):
        print("meta/fitbit_pids.parquet found — loading.")
        pids_df = cache_load(META_PIDS_PATH)
    else:
        print("Querying all Fitbit pids from BQ ...")
        pids_df = client.query(f"""
            SELECT DISTINCT person_id
            FROM `{dataset}.cb_search_person`
            WHERE has_fitbit_activity_summary = 1
        """).to_dataframe()
        cache_save(pids_df, META_PIDS_PATH)
        print(f"  Saved {len(pids_df):,} pids → {META_PIDS_PATH}")

    pids    = sorted(pids_df["person_id"].tolist())
    pids_bq = ", ".join(str(p) for p in pids)

    if not overwrite and cache_exists(META_COVERAGE_PATH):
        print("meta/fitbit_coverage.parquet found — loading.")
        coverage_df = cache_load(META_COVERAGE_PATH)
    else:
        print("Querying Fitbit coverage dates from BQ ...")
        coverage_df = client.query(f"""
            SELECT
                person_id,
                MIN(date) AS fitbit_start,
                MAX(date) AS fitbit_end
            FROM `{dataset}.activity_summary`
            WHERE person_id IN ({pids_bq})
            GROUP BY person_id
        """).to_dataframe()
        coverage_df["fitbit_start"] = pd.to_datetime(coverage_df["fitbit_start"])
        coverage_df["fitbit_end"]   = pd.to_datetime(coverage_df["fitbit_end"])
        cache_save(coverage_df, META_COVERAGE_PATH)
        print(f"  Saved {len(coverage_df):,} rows → {META_COVERAGE_PATH}")

    global_min = coverage_df["fitbit_start"].min().date()
    global_max = coverage_df["fitbit_end"].max().date()
    print(f"  Date window: {global_min} → {global_max}")

    if not overwrite and cache_exists(META_INDEX_PATH):
        print("meta/index.parquet found — loading.")
        index_df = cache_load(META_INDEX_PATH)
    else:
        print("Building pid→shard index ...")
        index_df = build_pid_index(pids)
        cache_save(index_df, META_INDEX_PATH)
        n = index_df["shard_idx"].max() + 1
        print(f"  Saved index: {len(index_df):,} pids → {n} shards of ≤1000")

    return pids_df, coverage_df, index_df


# ── Per-modality pipeline ──────────────────────────────────────────────────────

def run_pipeline(
    modality: str,
    client: bigquery.Client,
    dataset: str,
    overwrite_meta: bool = False,
) -> None:
    """
    Run the full build pipeline for one modality.

    Stages
    ------
    0. Bootstrap meta (pids, coverage, shard index) — shared, idempotent
    1. Per-shard BQ queries → GCS cache shards (per-shard checkpoint)
    2. Verify (skipped if sentinel exists)
    """
    if modality not in MODALITIES:
        raise ValueError(f"Unknown modality {modality!r}. Choose from {MODALITIES}")

    print(f"\n{'='*60}")
    print(f"  PIPELINE: {modality}")
    print(f"{'='*60}")

    # ── Stage 0: meta ──────────────────────────────────────────────────────────
    pids_df, coverage_df, index_df = bootstrap_meta(
        client, dataset, overwrite=overwrite_meta
    )

    global_min = str(coverage_df["fitbit_start"].min().date())
    global_max = str(coverage_df["fitbit_end"].max().date())

    # ── Stage 1: per-shard BQ → GCS ───────────────────────────────────────────
    print(f"\n[{modality}] Stage 1 — per-shard BQ queries → GCS")

    n_shards   = int(index_df["shard_idx"].max()) + 1
    shard_pids = index_df.groupby("shard_idx")["person_id"].apply(list).to_dict()

    skipped = 0
    for shard_idx in tqdm(range(n_shards), desc=modality):
        gcs_shard = f"{CACHE_PREFIX[modality]}{shard_name(shard_idx)}"
        if cache_exists(gcs_shard):
            skipped += 1
            continue

        pids = shard_pids.get(shard_idx, [])
        if not pids:
            continue

        export_shard(
            client     = client,
            modality   = modality,
            shard_idx  = shard_idx,
            pids       = pids,
            dataset    = dataset,
            global_min = global_min,
            global_max = global_max,
        )

    if skipped:
        print(f"  ({skipped}/{n_shards} shard(s) already in GCS — skipped)")

    # ── Stage 2: Verify ───────────────────────────────────────────────────────
    print(f"\n[{modality}] Stage 2 — Verify")
    passed = verify_modality(modality, index_df)

    status = "✅ DONE" if passed else "❌ FAILED VERIFICATION"
    print(f"\n[{modality}] {status}")


# ── Informational helpers ──────────────────────────────────────────────────────

def _wb_stewardship(gcs_uris: list[str]) -> dict[str, str]:
    """
    Map each GCS URI to its stewardship label from wb resource list.
    Returns a dict keyed by URI. Runs wb exactly once.
    """
    try:
        raw = subprocess.run(
            ["wb", "resource", "list", "--format=json"],
            capture_output=True, text=True, check=True,
        ).stdout
        resources = json.loads(raw)
    except Exception as e:
        return {uri: f"⚠️ wb lookup failed ({e})" for uri in gcs_uris}

    out = {}
    for uri in gcs_uris:
        bucket_name = uri.removeprefix("gs://").rstrip("/")
        match = next(
            (r for r in resources
             if r.get("resourceType") == "GCS_BUCKET"
             and r.get("bucketName") == bucket_name),
            None,
        )
        if match:
            st = match.get("stewardshipType", "UNKNOWN")
            out[uri] = "CONTROLLED ✅" if st == "CONTROLLED" else f"{st} ⚠️"
        else:
            out[uri] = "not found in wb resource list ⚠️"
    return out


def cache_tree() -> None:
    """
    Print the intended GCS path structure for the cache and main buckets,
    and verify each is a CONTROLLED (workspace-owned) resource.

    This is a static description — it does not require anything to exist in GCS yet.
    """
    cache_bucket = _bucket()
    main_bucket  = os.environ.get("WORKSPACE_BUCKET", "(WORKSPACE_BUCKET not set — import src.utils first)")

    ownership = _wb_stewardship([cache_bucket, main_bucket])
    cache_own = ownership[cache_bucket]
    main_own  = ownership[main_bucket]

    print(f"""
CACHE BUCKET  {cache_bucket}/
              [{cache_own}]
│
├── meta/
│   ├── fitbit_pids.parquet          all Fitbit PIDs in CDR
│   ├── fitbit_coverage.parquet      per-PID fitbit_start / fitbit_end
│   └── index.parquet                pid → shard_idx mapping
│
├── hr_hourly/
│   ├── shard_00000.parquet  ┐       ~{PIDS_PER_SHARD:,} pids each
│   ├── shard_00001.parquet  │       columns: person_id, date, hour,
│   ├── ...                  ┘         mean_hr, n_valid_minutes
│   └── _VERIFIED                    sentinel — written on successful verification
│
├── steps_hourly/
│   ├── shard_NNNNN.parquet          columns: person_id, date, hour, hourly_steps
│   └── _VERIFIED
│
├── sleep_summary/
│   ├── shard_NNNNN.parquet          columns: person_id, sleep_date,
│   └── _VERIFIED                      minute_in_bed/asleep/awake/wake
│
└── sleep_onset_offset/
    ├── shard_NNNNN.parquet          columns: person_id, sleep_date, night_date,
    └── _VERIFIED                      onset_dt, offset_dt


MAIN BUCKET   {main_bucket}/
              [{main_own}]
│
├── raw_pulls/                       cached BigQuery pulls (01, 02) and valid days/nights (03a)
├── cohort/
│   ├── cohort_master.parquet        01, 02 — one row per participant
│   └── attrition.parquet            01, 02, 03b — attrition log
├── covariates/
│   └── covariates.parquet           02 — age, sex, education, BMI, CCI, latitude, medications
├── features/
│   └── wearable_features.parquet    03b — per-task steps, WASO, sleep duration, STV, photoperiod
└── results/                         04a, 04b, 04c, 05 — model results and reported tables
""")


def cache_status() -> None:
    """
    Report the current build state of the cache bucket.

    Checks GCS for which meta files and cache shards exist, and whether
    each modality has passed verification. Reads only GCS object listings
    and (if the index exists) the index parquet — no column data downloaded.
    """
    cache_bucket = _bucket()
    print(f"\nCache bucket : {cache_bucket}\n")

    # ── Meta files ─────────────────────────────────────────────────────────────
    meta_items = [
        ("fitbit_pids",    META_PIDS_PATH),
        ("fitbit_coverage", META_COVERAGE_PATH),
        ("index",          META_INDEX_PATH),
    ]
    meta_flags = {name: cache_exists(path) for name, path in meta_items}
    meta_str   = "  ".join(
        f"{name} {'✅' if ok else '❌'}" for name, ok in meta_flags.items()
    )

    n_pids = n_shards_expected = None
    if meta_flags["index"]:
        try:
            index_df = cache_load(META_INDEX_PATH)
            n_pids = len(index_df)
            n_shards_expected = int(index_df["shard_idx"].max()) + 1
        except Exception:
            pass

    pid_info = f"  ({n_pids:,} pids, {n_shards_expected} shards)" if n_pids else ""
    print(f"Meta         : {meta_str}{pid_info}\n")

    # ── Per-modality table ─────────────────────────────────────────────────────
    col_w = 22
    print(f"{'Modality':<{col_w}} {'Shards':>12}  Verified")
    print("─" * (col_w + 24))

    for modality in MODALITIES:
        n_existing = len(cache_ls(CACHE_PREFIX[modality]))
        expected   = str(n_shards_expected) if n_shards_expected is not None else "?"
        shard_str  = f"{n_existing} / {expected}"

        verified = cache_exists(VERIFIED_SENTINEL[modality])
        if verified:
            v_str = "✅"
        elif n_existing == 0:
            v_str = "—"
        else:
            v_str = "❌ not verified"

        print(f"{modality:<{col_w}} {shard_str:>12}  {v_str}")

    print()
