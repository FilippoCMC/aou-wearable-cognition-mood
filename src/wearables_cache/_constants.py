# src/wearables_cache/_constants.py
"""
Central configuration for the wearables cache.
All GCS paths are relative to CACHE_BUCKET root.
"""

# ── Bucket ─────────────────────────────────────────────────────────────────────
# Resolved from WORKSPACE_CACHE env var set by src/utils.py (wb resource list).
# utils.py must be imported before any cache operation.
import os as _os
CACHE_BUCKET = _os.environ.get("WORKSPACE_CACHE", "gs://aou-fitbit-cache")

# ── Shard size ─────────────────────────────────────────────────────────────────
PIDS_PER_SHARD = 1000

# ── GCS path templates (relative to CACHE_BUCKET) ─────────────────────────────
# Meta
META_PIDS_PATH        = "meta/fitbit_pids.parquet"
META_COVERAGE_PATH    = "meta/fitbit_coverage.parquet"
META_INDEX_PATH       = "meta/index.parquet"          # pid → shard_idx

# Pid-sorted cache shards
CACHE_PREFIX = {
    "hr_hourly":          "hr_hourly/",
    "steps_hourly":       "steps_hourly/",
    "sleep_summary":      "sleep_summary/",
    "sleep_onset_offset": "sleep_onset_offset/",
}

# Sentinel file written after verification passes for a modality
VERIFIED_SENTINEL = {
    m: f"{CACHE_PREFIX[m]}_VERIFIED"
    for m in CACHE_PREFIX
}

MODALITIES = list(CACHE_PREFIX.keys())

# ── Column schemas (used for dtype enforcement after load) ─────────────────────
SCHEMA = {
    "hr_hourly": {
        "person_id":        "int64",
        "date":             "datetime64[ns]",
        "hour":             "int64",
        "mean_hr":          "float64",
        "n_valid_minutes":  "int64",
    },
    "steps_hourly": {
        "person_id":        "int64",
        "date":             "datetime64[ns]",
        "hour":             "int64",
        "hourly_steps":     "int64",
    },
    "sleep_summary": {
        "person_id":              "int64",
        "sleep_date":             "datetime64[ns]",
        "minute_in_bed":          "float64",
        "minute_asleep":          "float64",
        "minute_awake":           "float64",
        "minute_wake":            "float64",
        "minute_to_fall_asleep":  "float64",
    },
    "sleep_onset_offset": {
        "person_id":        "int64",
        "sleep_date":       "datetime64[ns]",
        "night_date":       "datetime64[ns]",
        "onset_dt":         "datetime64[ns]",
        "offset_dt":        "datetime64[ns]",
    },
}