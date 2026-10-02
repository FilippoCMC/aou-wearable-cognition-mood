#!/usr/bin/env bash
# Launch a background, disconnect-proof run of the analysis notebooks on the
# Verily Workbench.
#
# Usage (from anywhere in the repository):
#   bash scripts/run_notebooks.sh                       # 01_cohort -> 05_summary
#   bash scripts/run_notebooks.sh 04a_modelling_main.ipynb 05_summary.ipynb
#   bash scripts/run_notebooks.sh --continue-on-error   # any run_notebooks.py option
#
# What this does:
#   - Runs scripts/run_notebooks.py inside the uv environment (`uv run --locked`),
#     under `setsid` + `nohup`, detached from this shell, so the job keeps going
#     if you close the terminal tab or lose the browser connection.
#   - A running notebook keeps its kernel busy and the VM's CPU above zero, which
#     is what the workbench's "stop after idle time" autopause watches, so a live
#     run generally is not autopaused. This is a side effect of how autopause
#     detects idleness, not a guarantee: for a long run, also raise "Stop after
#     an idle time of" in the app's compute settings.
#   - Prints a log path to tail and a process id to check on later.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found on PATH (it ships with the Verily Workbench image); see README.md." >&2
  exit 1
fi
if ! command -v setsid >/dev/null 2>&1; then
  echo "setsid not found (it ships with util-linux on the workbench VM)." >&2
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG_DIR="logs/notebook_runs"
mkdir -p "$RUN_LOG_DIR"
DRIVER_LOG="$RUN_LOG_DIR/driver_${TS}.log"
PID_FILE="$RUN_LOG_DIR/driver_${TS}.pid"

# setsid makes the driver the leader of a new process group (group id = its pid),
# so the whole run (driver, papermill, kernel) can be stopped with one kill.
nohup setsid uv run --locked python scripts/run_notebooks.py "$@" > "$DRIVER_LOG" 2>&1 &
DRIVER_PID=$!
echo "$DRIVER_PID" > "$PID_FILE"
disown

echo "Started in background (process $DRIVER_PID)."
echo "Driver log:        $DRIVER_LOG"
echo "Per-notebook logs: $RUN_LOG_DIR/<notebook>_<timestamp>.log"
echo
echo "Watch progress:    tail -f $DRIVER_LOG"
echo "Is it still alive: kill -0 $DRIVER_PID 2>/dev/null && echo running || echo finished"
echo "Stop it early:     kill -- -$DRIVER_PID"
