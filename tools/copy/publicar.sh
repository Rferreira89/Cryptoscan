#!/usr/bin/env bash
# Publica <pasta>/copy/* no ramo autonomo sem apagar o que outros trabalhos escreveram (3 tentativas).
set -u
SRC=$1
for tent in 1 2 3; do
  W=$(mktemp -d)
  git clone -q --depth 1 -b autonomo "$PUSH_URL" "$W" 2>/dev/null || { echo "clone falhou"; sleep 5; continue; }
  mkdir -p "$W/copy" && cp "$SRC"/copy/*.json "$SRC"/copy/*.jsonl "$W/copy/" 2>/dev/null
  cd "$W" && git config user.name cryptoscan-bot && git config user.email bot@users.noreply.github.com
  git add -A copy
  if git diff --cached --quiet; then echo "nada novo"; exit 0; fi
  git commit -q -m "copy $(date -u +%FT%TZ)"
  if git push -q "$PUSH_URL" autonomo:autonomo 2>/dev/null; then echo "publicado"; exit 0; fi
  cd /; rm -rf "$W"; sleep $(( tent * 5 ))
done
echo "publicacao falhou"; exit 1
