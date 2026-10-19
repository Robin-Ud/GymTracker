#!/data/data/com.termux/files/usr/bin/bash
# código e dados são repos separados: o pessoal/ é o clone dos seus dados
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DADOS="$DIR/pessoal"

tem_remote() { git -C "$1" rev-parse --is-inside-work-tree &>/dev/null && git -C "$1" remote get-url origin &>/dev/null; }

tem_remote "$DIR" && { git -C "$DIR" pull --quiet --rebase 2>/dev/null || true; }
tem_remote "$DADOS" && { git -C "$DADOS" pull --quiet --rebase 2>/dev/null || true; }

python3 "$DIR/gymtracker.py" "$@"

if tem_remote "$DADOS"; then
    git -C "$DADOS" add .
    git -C "$DADOS" diff --cached --quiet || git -C "$DADOS" commit -m "sync: auto"
    git -C "$DADOS" push --quiet
fi
