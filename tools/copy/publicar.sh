#!/usr/bin/env bash
# Publica so os ficheiros pedidos de <pasta>/copy no ramo autonomo (o observador e o ranking correm em paralelo e
# nao se podem sobrepor), sem apagar o que outros trabalhos escreveram. 4 tentativas.
# uso: publicar.sh <pasta> <ficheiro>...
set -u
SRC=$1; shift
for tent in 1 2 3 4; do
  W=$(mktemp -d)
  git clone -q --depth 1 -b autonomo "$PUSH_URL" "$W" 2>/dev/null || { echo "clone falhou"; sleep 5; continue; }
  mkdir -p "$W/copy"
  for f in "$@"; do [ -f "$SRC/copy/$f" ] && cp "$SRC/copy/$f" "$W/copy/$f"; done
  cd "$W" && git config user.name cryptoscan-bot && git config user.email bot@users.noreply.github.com
  git add -A copy
  if git diff --cached --quiet; then echo "nada novo"; exit 0; fi
  git commit -q -m "copy $(date -u +%FT%TZ)"
  if git push -q "$PUSH_URL" autonomo:autonomo 2>/dev/null; then echo "publicado"; exit 0; fi
  cd /; rm -rf "$W"; sleep $(( tent * 4 ))
done
echo "publicacao falhou"; exit 1
