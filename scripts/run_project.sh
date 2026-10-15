#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
mkdir -p "$project_root/.cache/sqlite"
export SQLITE_TMPDIR="$project_root/.cache/sqlite"
if [[ ! -x .venv/bin/python ]]; then
  echo '请先运行 bash scripts/setup_environment.sh' >&2; exit 2
fi
export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONNOUSERSITE=1
exec .venv/bin/python -m user_behavior_analysis "$@"
