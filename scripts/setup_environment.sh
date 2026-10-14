#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
env_name="${1:-.venv}"
case "$env_name" in .venv|.venv-*) ;; *) echo '环境目录请使用 .venv 或 .venv-名称' >&2; exit 2 ;; esac
if [[ "$env_name" == *'/'* ]]; then echo '环境目录名称不能包含 /' >&2; exit 2; fi
cd "$project_root"
python_candidate=''
if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_candidate="$PYTHON_BIN"
else
  if [[ -x .venv/bin/python ]]; then
    python_candidate="$(.venv/bin/python -c 'import sys; from pathlib import Path; print(Path(sys.base_prefix) / "bin/python3")')"
  fi
  if [[ ! -x "$python_candidate" ]]; then
    python_candidate="$(command -v python3.12 || true)"
  fi
  if [[ ! -x "$python_candidate" ]]; then
    python_candidate="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  fi
fi
if [[ ! -x "$python_candidate" ]]; then
  echo '未找到 Python 3.12。安装 Python 3.12 后，用 PYTHON_BIN=/完整路径/python3 bash scripts/setup_environment.sh 重试。' >&2
  exit 2
fi
"$python_candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "需要 Python 3.12，当前为 " + sys.version.split()[0])'
if [[ -d "$env_name" && ! -x "$env_name/bin/python" ]]; then
  echo '现有目录不是可用虚拟环境，请使用新的 .venv-名称。' >&2; exit 2
fi
if [[ ! -x "$env_name/bin/python" ]]; then "$python_candidate" -m venv "$env_name"; fi
"$env_name/bin/python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "现有虚拟环境需要 Python 3.12")'
export PIP_CACHE_DIR="$project_root/.cache/pip"
export PYTHONNOUSERSITE=1
"$env_name/bin/python" -m pip install -r requirements.txt
"$env_name/bin/python" -m pip check
echo "环境已准备好：$project_root/$env_name"
