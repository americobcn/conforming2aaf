#!/bin/bash
# Xcode Run Script phase: copy build/engine into the app's Resources and sign it.
set -euo pipefail

ROOT="${SRCROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SRC="$ROOT/build/engine"
DEST="$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/engine"

# Rebuild when missing or when the engine sources are newer than the build.
if [ ! -x "$SRC/python/bin/python3" ] || [ -n "$(find "$ROOT/engine/conform2aaf" "$ROOT/engine/pyproject.toml" "$ROOT/tools" -newer "$SRC/lib" -print -quit 2>/dev/null)" ]; then
  "$ROOT/scripts/build_engine.sh"
fi

mkdir -p "$DEST"
rsync -a --delete "$SRC/" "$DEST/"

IDENTITY="${EXPANDED_CODE_SIGN_IDENTITY:--}"
[ -z "$IDENTITY" ] && IDENTITY="-"
find "$DEST" -type f \( -name '*.so' -o -name '*.dylib' -o -perm -111 \) -print0 |
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q 'Mach-O'; then
      codesign --force --sign "$IDENTITY" --timestamp=none "$f"
    fi
  done
