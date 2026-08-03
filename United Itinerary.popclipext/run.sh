#!/bin/sh
# PopClip launcher.
#
# PopClip runs a `shell script file` under /bin/sh whenever the extension
# declares no `popclip version`, or whenever the filename ends in `.sh`.
# Naming this file `.sh` therefore makes the invocation unambiguous: /bin/sh
# is genuinely the right interpreter for it, and it takes responsibility for
# locating a Python and running parse.py.
#
# parse.py stays standalone and stdlib-only; this only bootstraps it.

# Guarantee the core utilities below resolve, whatever PATH PopClip hands us.
PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH
export PATH

DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
[ -n "$DIR" ] || DIR=$(pwd)
LOG=/tmp/popclip-united-debug.txt

{
    echo "=== run.sh $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo "dir:  $DIR"
    echo "pwd:  $(pwd)"
    echo "PATH: $PATH"
    echo "POPCLIP_TEXT length: ${#POPCLIP_TEXT}"
} >"$LOG" 2>&1

# Keep the exact selection PopClip handed us. Text that reaches a human by
# copy-paste gets its whitespace normalised on the way, which hides the very
# differences that break parsing.
printf '%s' "$POPCLIP_TEXT" >/tmp/popclip-united-text.txt 2>/dev/null

for PY in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    [ -x "$PY" ] || continue

    ERR=$("$PY" "$DIR/parse.py" 2>&1 >/tmp/popclip-united-out.txt)
    RC=$?
    OUT=$(cat /tmp/popclip-united-out.txt 2>/dev/null)
    echo "interpreter: $PY (rc=$RC)" >>"$LOG"
    echo "stderr: $ERR" >>"$LOG"

    if [ "$RC" -eq 0 ] && [ -n "$OUT" ]; then
        printf '%s\n' "$OUT"
        exit 0
    fi

    # Surface the failure on the clipboard rather than a bare PopClip "X",
    # which carries no information about what went wrong.
    printf 'Itinerary parse failed.\n'
    printf 'interpreter: %s (exit %s)\n' "$PY" "$RC"
    printf 'POPCLIP_TEXT length: %s\n' "${#POPCLIP_TEXT}"
    printf 'error: %s\n' "$ERR"
    exit 0
done

printf 'Itinerary parse failed: no python3 found.\n'
printf 'PATH: %s\n' "$PATH"
exit 0
