# src/wearables_cache/_bq_pulls.py
"""
Per-shard BigQuery fetch functions.

Each call to export_shard() queries one shard's person_ids (~1000 pids)
directly from a CDR clustered table, then writes the result as a single
parquet shard to the GCS cache bucket.

Because all CDR wearable tables are clustered by person_id, BQ reads only
the relevant cluster blocks — not the full table — keeping per-query cost
low and avoiding large VM data movement or egress.
"""

import os
import subprocess
import tempfile

from google.cloud import bigquery

from ._constants import CACHE_BUCKET, CACHE_PREFIX
from ._gcs import shard_name


# ── Modality-specific SELECT queries ──────────────────────────────────────────

def _query_hr_hourly(dataset: str, pids_str: str,
                     global_min: str, global_max: str) -> str:
    return f"""
    WITH per_min AS (
        SELECT
            person_id,
            DATE(datetime)                AS date,
            EXTRACT(HOUR   FROM datetime) AS hour,
            EXTRACT(MINUTE FROM datetime) AS minute,
            AVG(heart_rate_value)         AS min_avg_hr
        FROM `{dataset}.heart_rate_intraday`
        WHERE person_id IN ({pids_str})
          AND DATE(datetime) BETWEEN '{global_min}' AND '{global_max}'
        GROUP BY person_id, date, hour, minute
    )
    SELECT
        person_id, date, hour,
        ROUND(AVG(min_avg_hr), 2) AS mean_hr,
        COUNT(*)                  AS n_valid_minutes
    FROM per_min
    GROUP BY person_id, date, hour
    ORDER BY person_id, date, hour
    """


def _query_steps_hourly(dataset: str, pids_str: str,
                        global_min: str, global_max: str) -> str:
    return f"""
    SELECT
        person_id,
        DATE(datetime)              AS date,
        EXTRACT(HOUR FROM datetime) AS hour,
        SUM(steps)                  AS hourly_steps
    FROM `{dataset}.steps_intraday`
    WHERE person_id IN ({pids_str})
      AND DATE(datetime) BETWEEN '{global_min}' AND '{global_max}'
    GROUP BY person_id, date, hour
    ORDER BY person_id, date, hour
    """


def _query_sleep_summary(dataset: str, pids_str: str) -> str:
    return f"""
    SELECT
        person_id,
        sleep_date,
        minute_in_bed,
        minute_asleep,
        minute_awake,
        minute_wake,
        minute_to_fall_asleep
    FROM `{dataset}.sleep_daily_summary`
    WHERE CAST(is_main_sleep AS STRING) = 'true'
      AND person_id IN ({pids_str})
    ORDER BY person_id, sleep_date
    """


def _query_sleep_onset_offset(dataset: str, pids_str: str) -> str:
    return f"""
    SELECT
        person_id,
        sleep_date,
        DATE_SUB(sleep_date, INTERVAL 1 DAY)                               AS night_date,
        MIN(start_datetime)                                                 AS onset_dt,
        MAX(DATETIME_ADD(
            start_datetime,
            INTERVAL CAST(ROUND(duration_in_min) AS INT64) MINUTE
        ))                                                                  AS offset_dt
    FROM `{dataset}.sleep_level`
    WHERE CAST(is_main_sleep AS STRING) = 'true'
      AND person_id IN ({pids_str})
    GROUP BY person_id, sleep_date
    ORDER BY person_id, sleep_date
    """


def _build_query(
    modality: str,
    dataset: str,
    pids_str: str,
    global_min: str = None,
    global_max: str = None,
) -> str:
    if modality == "hr_hourly":
        return _query_hr_hourly(dataset, pids_str, global_min, global_max)
    elif modality == "steps_hourly":
        return _query_steps_hourly(dataset, pids_str, global_min, global_max)
    elif modality == "sleep_summary":
        return _query_sleep_summary(dataset, pids_str)
    elif modality == "sleep_onset_offset":
        return _query_sleep_onset_offset(dataset, pids_str)
    else:
        raise ValueError(f"Unknown modality: {modality!r}")


# ── Per-shard export: BQ query → local temp → GCS ────────────────────────────

def export_shard(
    client: bigquery.Client,
    modality: str,
    shard_idx: int,
    pids: list,
    dataset: str,
    global_min: str = None,
    global_max: str = None,
) -> int:
    """
    Query BQ for one shard's pids and write the result to GCS.

    Returns the number of rows written (0 is valid — some pids have no data
    for a given modality). An empty parquet is still written so the GCS
    sentinel check works correctly on re-run.
    """
    pids_str = ", ".join(str(p) for p in pids)
    sql = _build_query(modality, dataset, pids_str, global_min, global_max)
    df  = client.query(sql).to_dataframe()

    gcs_path = f"{CACHE_BUCKET}/{CACHE_PREFIX[modality]}{shard_name(shard_idx)}"

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp = f.name
    try:
        df.to_parquet(tmp, index=False, compression="snappy")
        subprocess.run(
            ["gsutil", "-q", "cp", tmp, gcs_path],
            check=True, capture_output=True,
        )
    finally:
        os.unlink(tmp)

    return len(df)
