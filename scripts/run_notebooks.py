#!/usr/bin/env python3
"""
Run notebooks headlessly with papermill, in order, with real-time logging.

With no notebook arguments, runs the analysis sequence 01_cohort -> 05_summary
(00_build_cache, the one-time wearable-cache build, is never run by default).
Each notebook is executed in place (outputs written back into the .ipynb), in
the repository root, under the `aou-wearable-cognition-mood` Jupyter kernel registered
from the uv environment (see README). Each notebook gets its own timestamped
log under --log-dir, written as it runs (tail -f it to watch progress). The
sequence stops at the first notebook that fails.

Usage (from the repository root, inside the uv environment):
    uv run python scripts/run_notebooks.py                     # 01 -> 05
    uv run python scripts/run_notebooks.py 04a_modelling_main.ipynb 05_summary.ipynb

Normally launched via scripts/run_notebooks.sh, which also detaches this
process from the terminal so it survives a lost connection to the workbench.
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Analysis sequence, in dependency order. 04c rewrites the outputs of 04a and 04b in place.
ANALYSIS_NOTEBOOKS = [
    "01_cohort.ipynb",
    "02_covariates.ipynb",
    "03a_wearable_pulls.ipynb",
    "03b_feature_extraction.ipynb",
    "04a_modelling_main.ipynb",
    "04b_modelling_sensitivity.ipynb",
    "04c_modelling_power.ipynb",
    "05_summary.ipynb",
]

# Kernel registered from the uv environment in the README. The notebooks' own kernelspec
# is the image's `python3`, which lacks the pinned packages, so it is never used.
DEFAULT_KERNEL = "aou-wearable-cognition-mood"


def run_one(nb_path: Path, log_dir: Path, kernel: str, timeout: int | None) -> bool:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{nb_path.stem}_{ts}.log"

    # --cwd: run the kernel in the notebook's own directory, as JupyterLab does, so the
    # notebooks' `sys.path` setup finds src/.
    cmd = [sys.executable, "-m", "papermill", str(nb_path), str(nb_path), "--kernel", kernel,
           "--cwd", str(nb_path.resolve().parent),
           "--log-output", "--no-progress-bar", "--request-save-on-cell-execute"]
    if timeout:
        cmd += ["--execution-timeout", str(timeout)]

    start = time.time()
    with open(log_path, "w") as log_f:
        def log(msg: str):
            line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
            print(line, flush=True)
            log_f.write(line + "\n")
            log_f.flush()

        log(f"START {nb_path}  (log: {log_path})")
        log(f"cmd: {' '.join(cmd)}")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:  # stream live, don't buffer until exit
            sys.stdout.write(line)
            sys.stdout.flush()
            log_f.write(line)
            log_f.flush()
        proc.wait()
        elapsed = time.time() - start

        if proc.returncode == 0:
            log(f"DONE  {nb_path}  ({elapsed:.0f}s)")
            return True
        log(f"FAILED  {nb_path}  exit code {proc.returncode}  ({elapsed:.0f}s)")
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("notebooks", nargs="*",
                        help="Notebook path(s), run in the order given (default: 01 -> 05)")
    parser.add_argument("--log-dir", default=str(REPO_ROOT / "logs" / "notebook_runs"),
                        help="Directory for per-notebook logs")
    parser.add_argument("--kernel", default=DEFAULT_KERNEL,
                        help=f"Jupyter kernel for every notebook (default: {DEFAULT_KERNEL})")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Per-cell timeout in seconds (default: no timeout)")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Keep running remaining notebooks if one fails (default: stop the sequence)")
    args = parser.parse_args()

    notebooks = [Path(nb) for nb in args.notebooks] or [REPO_ROOT / nb for nb in ANALYSIS_NOTEBOOKS]

    # Fail before anything runs if a notebook path is wrong or the kernel is not registered.
    missing = [str(nb) for nb in notebooks if not nb.exists()]
    if missing:
        sys.exit(f"Notebook(s) not found: {', '.join(missing)}")
    from jupyter_client.kernelspec import KernelSpecManager
    kernels = KernelSpecManager().find_kernel_specs()
    if args.kernel not in kernels:
        sys.exit(f"Jupyter kernel '{args.kernel}' is not registered (found: {', '.join(sorted(kernels))}). "
                 "Register it as described in the README, or pass --kernel.")

    print(f"Kernel: {args.kernel} ({kernels[args.kernel]})")
    print("Sequence: " + " -> ".join(nb.name for nb in notebooks), flush=True)

    results: dict[str, bool] = {}
    for i, nb_path in enumerate(notebooks, 1):
        print(f"\n=== [{i}/{len(notebooks)}] {nb_path.name} ===", flush=True)
        ok = run_one(nb_path, Path(args.log_dir), args.kernel, args.timeout)
        results[nb_path.name] = ok
        if not ok and not args.continue_on_error:
            print(f"Stopping sequence: {nb_path.name} failed. "
                  "Fix it, then re-run from that notebook (pass the remaining notebooks as arguments).")
            break

    print("\n=== Summary ===")
    for nb in notebooks:
        status = {True: "OK  ", False: "FAIL"}.get(results.get(nb.name), "SKIP")
        print(f"  {status}  {nb.name}")

    sys.exit(0 if len(results) == len(notebooks) and all(results.values()) else 1)


if __name__ == "__main__":
    main()
