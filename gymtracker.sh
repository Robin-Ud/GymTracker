#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -d "$DIR/.git" ] && git -C "$DIR" remote get-url origin &>/dev/null; then
    git -C "$DIR" pull --quiet --rebase 2>/dev/null || true
fi

python3 "$DIR/gymtracker.py" "$@"

if [ -d "$DIR/.git" ] && git -C "$DIR" remote get-url origin &>/dev/null; then
    git -C "$DIR" add .
    git -C "$DIR" diff --cached --quiet || git -C "$DIR" commit -m "sync: auto"
    git -C "$DIR" push --quiet
fi
