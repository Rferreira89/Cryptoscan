# (17/11) Codigo bom: a producao so corre codigo que passou os testes.
#
# Causa (16/11, 03:15-12:20 UTC, 9 h sem scanner): commits diretos na main (config.json com uma chave nova sem
# suporte em engine/config.py; engine/promo.py e engine/config.py com texto cortado/UTF-8 partido) fizeram falhar
# os testes. O ciclo do scanner corria sempre a ultima main: testes vermelhos = scan parado, o acompanhamento de
# minuto a minuto rebentava em config.load() e a arena falhou 9 vezes seguidas.
#
# Agora: cada commit novo da main e testado UMA vez (compilacao de engine/ e tools/ + suite completa). Se passar,
# passa a ser o codigo bom (BOM) e fica publicado no ramo data (codigo_bom.txt), de onde os workflows de producao
# (executor, agente OKX, Europa, arena) o leem. Se falhar, o ciclo continua com o ultimo codigo bom, avisa no
# Telegram uma vez por commit e regista em erros.txt; volta a testar quando houver outro commit na main.
#
# Uso (no diretorio do repositorio):  source /tmp/codigo_bom.sh; validar_codigo
# Globais: BOM (sha validado), MAU (ultimo sha reprovado), AVISO_MAU (linha para erros.txt, a escrever pelo ciclo),
#          CODIGO_OK (1 = o codigo checked-out esta validado), NOVO (sha da main lida agora)
# Opcional: CODIGO_BOM_INICIAL (sha validado conhecido, p. ex. do ramo data), CODIGO_BOM_TESTES (comando de teste),
#           TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (aviso)

codigo_bom_avisar() {
  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] || return 0
  curl -sS -m 20 -o /dev/null "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" 2>/dev/null || true
}

validar_codigo() {
  NOVO=""
  if git fetch -q origin main 2>/dev/null; then NOVO=$(git rev-parse FETCH_HEAD); fi
  if [ -z "${BOM:-}" ] && [ -n "${CODIGO_BOM_INICIAL:-}" ]; then
    BOM=$CODIGO_BOM_INICIAL
  fi
  if [ -n "$NOVO" ] && [ "$NOVO" != "${BOM:-}" ] && [ "$NOVO" != "${MAU:-}" ]; then
    git reset -q --hard "$NOVO"
    if eval "${CODIGO_BOM_TESTES:-python -m compileall -q engine tools > /tmp/compileall.log 2>&1 && python -m unittest discover -q -s tests -t . 2> /tmp/testes.log}"; then
      BOM=$NOVO
      MAU=""
      echo "codigo validado: ${BOM:0:7}"
    else
      MAU=$NOVO
      local resumo
      resumo=$( { tail -3 /tmp/compileall.log 2>/dev/null; grep -E "^(FAILED|Ran )|Error:" /tmp/testes.log 2>/dev/null | tail -4; } | tr '\n' ' ' | cut -c1-300 || true)
      if [ -n "${BOM:-}" ]; then
        AVISO_MAU="$(date -u +%FT%TZ) codigo novo ${NOVO:0:7} reprovado nos testes; a producao continua em ${BOM:0:7}. ${resumo}"
        codigo_bom_avisar "⚠️ CryptoScan: o commit ${NOVO:0:7} da main falhou os testes. O scanner e os agentes continuam com a última versão boa (${BOM:0:7}); nada do código novo entra em produção até um commit passar os testes. ${resumo}"
      else
        AVISO_MAU="$(date -u +%FT%TZ) codigo novo ${NOVO:0:7} reprovado nos testes e nao ha versao boa conhecida: scan parado. ${resumo}"
        codigo_bom_avisar "⚠️ CryptoScan: o commit ${NOVO:0:7} da main falhou os testes e não há versão boa conhecida: o scan fica parado até a main passar os testes. ${resumo}"
      fi
      echo "codigo ${NOVO:0:7} reprovado nos testes"
    fi
  fi
  if [ -n "${BOM:-}" ]; then
    git cat-file -e "${BOM}^{commit}" 2>/dev/null || git fetch -q origin "$BOM" 2>/dev/null || true
    if git reset -q --hard "$BOM" 2>/dev/null; then
      CODIGO_OK=1
      return 0
    fi
    echo "codigo bom ${BOM:0:7} indisponivel: volta a validar a main"
    BOM=""
  fi
  # nunca houve codigo validado (ou o validado desapareceu): corre a main e o ciclo do scan volta a testar
  [ -n "$NOVO" ] && git reset -q --hard "$NOVO"
  CODIGO_OK=0
}
