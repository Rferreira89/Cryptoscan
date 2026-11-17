#!/usr/bin/env bash
# Publica ficheiros de <pasta>/hunter no ramo autonomo SEM apagar o que outros trabalhos escreveram: em cada
# tentativa volta a clonar o ramo, copia so os ficheiros pedidos e faz push (3 tentativas).
# uso: publicar.sh <pasta> <mensagem> <ficheiro|padrao>...
set -u
SRC=$1; MSG=$2; shift 2
# (17/11) a volta de papel publica tambem o registo por ciclo, o resumo diario e o arquivo de derivados
# (o lancador na main so passa papel_estado.json: a lista completa vive aqui, no ramo de investigacao)
if [ "$MSG" = papel ]; then set -- "$@" papel_ciclos.jsonl papel_diario.jsonl "derivados/*"; fi
if [ "$MSG" = pesquisa ]; then set -- "$@" painel.json estados.json familias_registo.json; fi
for tent in 1 2 3; do
  W=$(mktemp -d)
  git clone -q --depth 1 -b autonomo "$PUSH_URL" "$W" 2>/dev/null || { git -C "$W" init -q -b autonomo; }
  mkdir -p "$W/hunter"
  for padrao in "$@"; do
    for f in "$SRC"/hunter/$padrao; do
      [ -f "$f" ] || continue
      rel=${f#"$SRC"/hunter/}; mkdir -p "$W/hunter/$(dirname "$rel")"; cp "$f" "$W/hunter/$rel"
    done
  done
  cd "$W" && git config user.name cryptoscan-bot && git config user.email bot@users.noreply.github.com
  git add -A hunter
  if git diff --cached --quiet; then echo "nada novo"; exit 0; fi
  git commit -q -m "hunter $MSG $(date -u +%FT%TZ)"
  if git push -q "$PUSH_URL" autonomo:autonomo 2>/dev/null; then echo "publicado ($MSG)"; exit 0; fi
  cd /; rm -rf "$W"; sleep $(( tent * 7 ))
done
echo "publicacao falhou"; exit 1
