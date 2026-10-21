#!/bin/sh
# Resolve the environment relative to this skill, never relative to the caller.
set -eu
skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
skill_python="$skill_dir/.venv/bin/python"
if [ "${1:-}" = "setup" ]; then
    shift
    bootstrap_python=${CHATCUT_BOOTSTRAP_PYTHON:-python3}
    "$bootstrap_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "需要 Python 3.10 或更新版本")'
    if [ ! -x "$skill_python" ]; then
        "$bootstrap_python" -m venv "$skill_dir/.venv"
    fi
    "$skill_python" -m pip install -r "$skill_dir/scripts/requirements.txt"
    "$skill_python" -c 'import jsonschema; import sys; print("已就绪：" + sys.executable)'
    exit 0
fi
if [ ! -x "$skill_python" ] || ! "$skill_python" -c 'import jsonschema' >/dev/null 2>&1; then
    printf '运行环境尚未准备好。请先执行：\n  sh "%s/scripts/run.sh" setup\n' "$skill_dir" >&2
    exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
case "${1:-}" in
    wait-export) shift; exec "$skill_python" "$skill_dir/scripts/wait_export.py" "$@" ;;
    python) shift; exec "$skill_python" "$@" ;;
    *) exec "$skill_python" "$skill_dir/scripts/chatcut.py" "$@" ;;
esac
