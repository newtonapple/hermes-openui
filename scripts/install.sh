#!/bin/sh
# Alternative to `hermes plugins install newtonapple/hermes-openui --enable`, which is the recommended route.
# Copies the plugin's runtime files from a local checkout into a Hermes home. Use it offline, or to try uncommitted
# changes. It leaves no Git record, so `hermes plugins update` does not work on the copy and Hermes skips its install scan.
#
#   scripts/install.sh                      install into $HERMES_HOME (default ~/.hermes) and enable it
#   scripts/install.sh --home DIR           install into another Hermes home (a profile, or a scratch home for testing)
#   scripts/install.sh --no-enable          copy the files only
#
# Copies only what the plugin needs at run time (no build sources, no docs, no screenshots). An existing copy is moved to
# <home>/cache/hermes-openui-previous-<timestamp>, never deleted. Needs only POSIX sh and cp; `hermes` is used to enable it.
set -eu

SRC=$(cd "$(dirname "$0")/.." && pwd)
HOME_DIR=${HERMES_HOME:-$HOME/.hermes}
ENABLE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --home) [ $# -ge 2 ] || { echo "--home needs a directory" >&2; exit 2; }; HOME_DIR=$2; shift 2 ;;
    --no-enable) ENABLE=0; shift ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

FILES="plugin.yaml __init__.py schemas.py tools.py bundle.py lint.py page.py README.md LICENSE THIRD_PARTY_NOTICES.md"
DIRS="assets skills desktop"
for f in $FILES $DIRS assets/packs.json desktop/plugin.js skills/openui-render/SKILL.md; do
  [ -e "$SRC/$f" ] || { echo "incomplete checkout: $SRC/$f is missing" >&2; exit 1; }
done

DEST="$HOME_DIR/plugins/hermes-openui"
mkdir -p "$HOME_DIR/plugins" "$HOME_DIR/cache"
STAGE=$(mktemp -d "$HOME_DIR/cache/hermes-openui-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT   # a failed copy must not leave a half-built stage behind (after the final mv it no longer exists)
for f in $FILES; do cp "$SRC/$f" "$STAGE/"; done
for d in $DIRS; do cp -R "$SRC/$d" "$STAGE/"; done

if [ -e "$DEST" ]; then
  PREV="$HOME_DIR/cache/hermes-openui-previous-$(date +%Y%m%d-%H%M%S)"
  mv "$DEST" "$PREV"
  echo "previous copy kept at $PREV (delete it when you are happy)"
fi
mv "$STAGE" "$DEST"
echo "installed: $DEST"

if [ "$ENABLE" = 1 ]; then
  if command -v hermes >/dev/null 2>&1; then
    HERMES_HOME="$HOME_DIR" hermes plugins enable hermes-openui
  else
    echo "hermes is not on PATH: enable it later with: hermes plugins enable hermes-openui" >&2
  fi
fi
echo "next: start a NEW chat (or restart the Hermes gateway so it reloads plugins), then ask for a chart or a DAG."
