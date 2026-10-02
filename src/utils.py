import os, re, json, subprocess, tempfile
from pathlib import Path
import pandas as pd
import numpy as np
from google.cloud import bigquery
from tqdm.auto import tqdm

# ── Attrition log ─────────────────────────────────────────────────────────────
# Every exclusion step appends a row here; notebooks save it to the bucket.
attrition_rows = []
def log_attrition(step, group, n_before, n_after, reason, task=None):
    attrition_rows.append(dict(
        step      = step,
        group     = group,
        task      = task,
        n_before  = int(n_before),
        n_dropped = int(n_before - n_after),
        n_after   = int(n_after),
        reason    = reason,
    ))
    task_tag = f' [{task}]' if task else ''
    print(f'[{step}]{task_tag} {group}: {n_before:,} → {n_after:,} '
          f'(dropped {n_before - n_after:,}) | {reason}')

# ── Workspace resources ───────────────────────────────────────────────────────
# Buckets are referenced by their Workbench resource id, not by GCS bucket name.
# Each id is resolved to its bucket through `wb resource list`, so the GCS name
# (which Workbench may prefix to make it globally unique) never appears in code.
# AOU_MAIN_BUCKET_ID overrides the output bucket without editing this file.
MAIN_BUCKET_ID  = os.environ.get("AOU_MAIN_BUCKET_ID", "aou-wearable-cognition-mood")
CACHE_BUCKET_ID = "aou-fitbit-cache"   # wearable cache written by 00_build_cache

resources = json.loads(subprocess.run(
    ["wb", "resource", "list", "--format=json"],
    capture_output=True, text=True, check=True
).stdout)

def resolve_bucket(resource_id):
    """Return 'gs://<bucket>' for a GCS_BUCKET workspace resource id."""
    for r in resources:
        if r.get("resourceType") == "GCS_BUCKET" and r.get("id") == resource_id:
            return f"gs://{r['bucketName']}"
    raise RuntimeError(
        f"No GCS_BUCKET resource with id '{resource_id}' in this workspace "
        f"(see `wb resource list`)."
    )

# WORKSPACE_CDR: CDR v9 Controlled Tier
for r in resources:
    if r.get("resourceType") in ["BQ_DATASET", "BIGQUERY_DATASET"]:
        if re.match(r"^C\d{4}Q\d+R\d+$", r.get("datasetId", "")):
            os.environ["WORKSPACE_CDR"] = f"{r['projectId']}.{r['datasetId']}"
            break

# WORKSPACE_BUCKET: output bucket; WORKSPACE_CACHE: wearable cache bucket
os.environ["WORKSPACE_BUCKET"] = resolve_bucket(MAIN_BUCKET_ID)
os.environ["WORKSPACE_CACHE"]  = resolve_bucket(CACHE_BUCKET_ID)

DATASET     = os.environ.get("WORKSPACE_CDR")
BUCKET      = os.environ.get("WORKSPACE_BUCKET")
CACHE       = os.environ.get("WORKSPACE_CACHE")
client      = bigquery.Client()

def tbl(name):
    """Fully-qualified BigQuery table reference."""
    return f"`{DATASET}.{name}`"

def gcs(path):
    """Full GCS path under the primary working bucket."""
    return f"{BUCKET}/{path}"

def gcs_cache(path):
    """Full GCS path under the wearable data cache bucket."""
    return f"{CACHE}/{path}"

def save_parquet(df, relative_path):
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        tmp = f.name
    df.to_parquet(tmp, index=False)
    subprocess.run(['gsutil', 'cp', tmp, gcs(relative_path)],
                   check=True, capture_output=True)
    os.unlink(tmp)
    print(f'Saved -> {relative_path}  ({len(df):,} rows)')

def load_parquet(relative_path):
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        tmp = f.name
    subprocess.run(['gsutil', 'cp', gcs(relative_path), tmp],
                   check=True, capture_output=True)
    df = pd.read_parquet(tmp)
    os.unlink(tmp)
    return df

def load_cache_parquet(relative_path):
    """Load a parquet file from the wearable cache bucket."""
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        tmp = f.name
    subprocess.run(['gsutil', 'cp', gcs_cache(relative_path), tmp],
                   check=True, capture_output=True)
    df = pd.read_parquet(tmp)
    os.unlink(tmp)
    return df

def gcs_exists(relative_path):
    """Return True if a GCS path exists in the primary bucket."""
    result = subprocess.run(
        ['gsutil', 'ls', gcs(relative_path)],
        capture_output=True, text=True
    )
    return result.returncode == 0 and result.stdout.strip() != ''

def list_shards(gcs_prefix):
    """Return sorted list of GCS parquet shard paths under a prefix."""
    result = subprocess.run(
        ['gsutil', 'ls', gcs_prefix],
        capture_output=True, text=True, check=True
    )
    return sorted([l.strip() for l in result.stdout.strip().split('\n')
                   if l.strip().endswith('.parquet')])

def read_shard(gcs_path):
    """Download a single GCS parquet shard and return as DataFrame."""
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        tmp = f.name
    subprocess.run(['gsutil', 'cp', gcs_path, tmp],
                   check=True, capture_output=True)
    df = pd.read_parquet(tmp)
    os.unlink(tmp)
    return df

def flush_shard(df, gcs_path):
    """Write a DataFrame to a GCS parquet path."""
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        tmp = f.name
    df.to_parquet(tmp, index=False)
    subprocess.run(['gsutil', 'cp', tmp, gcs_path],
                   check=True, capture_output=True)
    os.unlink(tmp)

def save_res(folder: str, path: str, overwrite: bool, res, file_type: str = 'csv', dpi: int = 150):
    """Save a DataFrame (csv/parquet) or matplotlib figure to res/<folder>/<path>.
    An existing file is kept unless overwrite is True."""
    base_res_dir = Path(__file__).resolve().parents[1] / 'res'
    base_res_dir.mkdir(exist_ok=True)

    target_folder = base_res_dir / folder
    target_folder.mkdir(parents=True, exist_ok=True)
    
    final_output_path = target_folder / path
    
    if final_output_path.exists():
        if overwrite:
            print(f"Path exists. Overwrite=True: Replacing target at {final_output_path}")
            if final_output_path.is_dir():
                import shutil
                shutil.rmtree(final_output_path)
                final_output_path.mkdir()
        else:
            print(f"Path already exists at {final_output_path} and overwrite=False. Skipping save.")
            return
    else:
        final_output_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(res, pd.DataFrame):
        if file_type.lower() == 'parquet':
            out_file = final_output_path if final_output_path.suffix == '.parquet' else final_output_path.with_suffix('.parquet')
            res.to_parquet(out_file, index=False)
        else:
            out_file = final_output_path if final_output_path.suffix == '.csv' else final_output_path.with_suffix('.csv')
            res.to_csv(out_file, index=False)
        print(f"DataFrame successfully saved to: {out_file}")
        
    elif hasattr(res, 'savefig'):
        out_file = final_output_path if final_output_path.suffix in ['.png', '.jpg', '.pdf', '.svg'] else final_output_path.with_suffix('.png')
        res.savefig(out_file, dpi=dpi, bbox_inches='tight')
        print(f"Plot successfully saved to: {out_file}")
        
    else:
        raise TypeError("Unsupported 'res' type. Must be a pandas DataFrame or a matplotlib Figure object.")

def _print_import_recap():
    print("📦 SRC.UTILS IMPORT RECAP")
    print("\n" + "=" * 50)
    print(f"Dataset    : {DATASET}")
    print(f"Bucket     : {BUCKET}")
    print(f"Cache      : {CACHE}")
    print("=" * 50)

_print_import_recap()