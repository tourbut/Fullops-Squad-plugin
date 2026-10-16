#!/bin/sh
# FullOps Squad directory edition: run a hook script from this plugin folder only.
case "$1" in
  caveman_start|done_gate|flow_gate|issue_mode) ;;
  *) echo "FullOps: unknown hook: $1" >&2; exit 2 ;;
esac
hook="$1"
shift
exec python3 "${CLAUDE_PLUGIN_ROOT}/scripts/${hook}.py" "$@"
