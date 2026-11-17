"""(17/11, ordem do Rui: isolamento do piloto OKX) Quem e o dono de uma posicao na OKX?

A OKX NAO poe o clOrdId no objeto da posicao (account/positions so tem instId, posId, pos, cTime...). A origem
confirma-se pelo que a propria OKX guarda das ordens:
  1. ordens condicionais pendentes do instrumento (stop/objetivo): o piloto anexa-as com attachAlgoClOrdId "pil...",
     que a OKX devolve como algoClOrdId;
  2. execucoes (trade/fills, ultimos 3 dias; trade/fills-history, 3 meses) desde a abertura da posicao (cTime): a
     execucao da ordem de entrada traz o clOrdId da ordem ("pil..." no piloto, "cs..." no executor antigo);
  3. ordens normais pendentes do instrumento com clOrdId "pil..." (entrada do piloto ainda por executar).
Resposta: True (do piloto), False (nao e do piloto) ou None (a OKX nao respondeu: nao se sabe). Quem chama trata
None como "nao mexer nesta volta": nunca adotar nem fechar o que pode ser do outro executor.
Em modo net a OKX junta no mesmo instrumento as posicoes dos dois executores; por isso nenhum dos dois abre num
instrumento que o outro tem (okx_exec.abrir e piloto_okx.procurar)."""
PREFIXO = "pil"


def _dados(r, inst=None):
    """Linhas da resposta; com inst, so as desse instrumento (defesa: a OKX ja filtra pelo instId pedido)."""
    return [x for x in (r or {}).get("data") or [] if inst is None or x.get("instId", inst) == inst]


def _ok(r):
    return (r or {}).get("code") == "0"


def do_piloto(privado, inst, desde_ms=None):
    """A posicao/ordens deste instrumento sao do piloto? desde_ms = cTime da posicao (ms) para as execucoes."""
    a1 = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
    a2 = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
    if not (_ok(a1) and _ok(a2)):
        return None
    if any(str(x.get("algoClOrdId") or "").startswith(PREFIXO) for x in _dados(a1, inst) + _dados(a2, inst)):
        return True
    pend = privado("GET", f"/api/v5/trade/orders-pending?instId={inst}")
    if not _ok(pend):
        return None
    if any(str(x.get("clOrdId") or "").startswith(PREFIXO) for x in _dados(pend, inst)):
        return True
    for caminho in ("fills", "fills-history"):
        f = privado("GET", f"/api/v5/trade/{caminho}?instType=FUTURES&instId={inst}&limit=100")
        if not _ok(f):
            return None
        fl = [x for x in _dados(f) if x.get("instId", inst) == inst and (desde_ms is None or int(x.get("ts") or 0) >= int(desde_ms))]
        if any(str(x.get("clOrdId") or "").startswith(PREFIXO) for x in fl):
            return True
        if fl:                                   # ha execucoes desde a abertura e nenhuma e do piloto
            return False
    return False


def instrumento_do_piloto(privado, inst):
    """Antes de abrir no instrumento: o piloto tem la posicao ou ordens? (sem posicao, so ordens pendentes contam;
    execucoes antigas de uma posicao ja fechada nao bloqueiam). True / False / None (sem resposta)."""
    pos = privado("GET", f"/api/v5/account/positions?instId={inst}")
    if not _ok(pos):
        return None
    aberta = next((x for x in _dados(pos) if float(x.get("pos") or 0)), None)
    if aberta:
        return do_piloto(privado, inst, int(aberta.get("cTime") or 0) - 1000 if aberta.get("cTime") else None)
    a1 = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
    a2 = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
    pend = privado("GET", f"/api/v5/trade/orders-pending?instId={inst}")
    if not (_ok(a1) and _ok(a2) and _ok(pend)):
        return None
    return (any(str(x.get("algoClOrdId") or "").startswith(PREFIXO) for x in _dados(a1, inst) + _dados(a2, inst))
            or any(str(x.get("clOrdId") or "").startswith(PREFIXO) for x in _dados(pend, inst)))
