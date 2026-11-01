#!/bin/bash
# Build a self-contained Python engine in build/engine:
#   build/engine/python  relocatable CPython 3.12 (python-build-standalone, via uv)
#   build/engine/lib     conform2aaf + pyaaf2
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/engine"
PY_VERSION="3.12.13"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

command -v uv >/dev/null || { echo "error: uv no está instalado (https://docs.astral.sh/uv/)"; exit 1; }
uv python install "$PY_VERSION" >/dev/null
PY_BIN="$(uv python find "$PY_VERSION")"
PY_HOME="$(cd "$(dirname "$PY_BIN")/.." && pwd -P)"

rm -rf "$OUT"
mkdir -p "$OUT"
rsync -a \
  --exclude 'lib/python3.12/test' --exclude 'lib/python3.12/idlelib' \
  --exclude 'lib/python3.12/tkinter' --exclude 'lib/python3.12/turtledemo' \
  --exclude 'lib/python3.12/ensurepip' --exclude 'lib/python3.12/lib2to3' \
  --exclude 'lib/python3.12/site-packages/*' --exclude 'lib/tcl*' --exclude 'lib/tk*' \
  --exclude 'lib/itcl*' --exclude 'lib/thread*' --exclude 'lib/python3.12/lib-dynload/_tkinter*' \
  --exclude 'include' --exclude 'share' --exclude '__pycache__' \
  "$PY_HOME/" "$OUT/python/"

uv pip install --quiet --python "$OUT/python/bin/python3" --target "$OUT/lib" "$ROOT/engine"
PYTHONPATH="$OUT/lib" "$OUT/python/bin/python3" -c "import aaf2, conform2aaf.cli; print('engine ok')"
"$OUT/python/bin/python3" -m compileall -q "$OUT/lib" >/dev/null || true
du -sh "$OUT"
