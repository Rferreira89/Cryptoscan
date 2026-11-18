"""(ordem do Rui de 10/11, ponto 1) Confirmacao COMPLETA do stop de uma posicao: a verificacao atual do executor da
OKX (_tem_stop_na_okx) so confirma que existe algum stop pendente no contrato; nao confirma o lado, a quantidade nem
o preco. Esta funcao recebe o que a OKX devolve (orders-algo-pending e positions) e diz se o stop cobre a posicao
TODA, do lado certo e abaixo/acima da entrada. So leitura e calculo: nao esta ligada ao executor."""


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def stop_cobre(algos, pos, lado="LONG", entrada=None):
    """algos: lista de ordens algo pendentes da OKX (conditional/oco) desse contrato.
    pos: quantidade aberta (contratos). Devolve (ok, motivos)."""
    motivos = []
    q = _f(pos)
    if not q:
        return False, ["posicao sem quantidade"]
    fecho = "sell" if lado == "LONG" else "buy"
    validos, cobertura = [], 0.0
    for a in algos or []:
        sl = _f(a.get("slTriggerPx"))
        if not sl:
            continue
        if a.get("side") != fecho:
            motivos.append(f"stop do lado errado ({a.get('side')})"); continue
        if entrada and ((lado == "LONG" and sl >= entrada) or (lado == "SHORT" and sl <= entrada)):
            motivos.append("stop do lado errado da entrada"); continue
        if str(a.get("closeFraction") or "") == "1":
            cobertura = q
        else:
            cobertura += _f(a.get("sz")) or 0.0
        validos.append(a)
    if not validos:
        return False, motivos or ["sem stop ativo"]
    if cobertura + 1e-12 < q:
        return False, motivos + [f"stop cobre {cobertura:g} de {q:g} contratos"]
    return True, motivos


# ---------------------------------------------------------------- Bybit UE (18/11): representacao da protecao
# So leitura e calculo, para monitorizacao e relatorios. Nao cria, altera nem cancela ordens.
# A Bybit UE guarda o TP/SL anexado a uma ordem spot como UMA ordem 'BidirectionalTpslOrder' (triggerPrice 0, stop em
# stopLoss, objetivo em takeProfit), que so aparece em /v5/order/realtime SEM orderFilter. O campo 'protecao' do
# registo real vem do historico de ordens TERMINADAS: fica vazio enquanto o stop esta ativo, e isso nao quer dizer
# que a posicao esteja desprotegida.
BYBIT_LEITURA_MAX_S = 1800          # leitura das ordens abertas mais antiga do que isto: nao verificada
BYBIT_ATIVAS = {"New", "Untriggered", "PartiallyFilled", "Active"}
BYBIT_DISPARADAS = {"Triggered", "Filled", "PartiallyFilledCanceled"}
BYBIT_CANCELADAS = {"Cancelled", "Deactivated", "Rejected"}
BYBIT_DESVIO_PLANO = 0.01           # stop na corretora mais de 1% diferente do plano: assinalado


def _lado_fecho(lado):
    return "Sell" if lado == "LONG" else "Buy"


def _protege(o):
    return bool(o.get("stopOrderType")) or (_f(o.get("triggerPrice")) or 0) > 0 or (_f(o.get("stopLoss")) or 0) > 0


def estado_protecao_bybit(simbolo, lado, abertas, leitura_ok, lida_em, agora, plano_stop=None, historico=None,
                          estado_interno=None):
    """Estado da protecao de uma posicao spot da Bybit UE a partir do que a CORRETORA devolveu.

    abertas: ordens de /v5/order/realtime (todas as do par ou da conta); leitura_ok: a leitura SEM orderFilter
    respondeu (e a unica que traz as BidirectionalTpslOrder); lida_em: hora dessa leitura (s); historico: ordens
    de protecao terminadas do par ([{"tipo", "estado", ...}] ou None se nao houver leitura); estado_interno: o que o
    registo do executor diz ("aberta", "fechada"...), so para assinalar divergencias.

    estado: ATIVA | DISPARADA | CANCELADA | INEXISTENTE | NAO_VERIFICADA. Nunca ATIVA so pelo plano do executor."""
    out = {"simbolo": simbolo, "lado": lado, "estado": "NAO_VERIFICADA", "fonte": "corretora (ordens abertas)",
           "lida_em": int(lida_em) if lida_em else None, "ordens": [], "divergencias": [], "motivo": None}
    if not leitura_ok:
        out["motivo"] = "a Bybit nao respondeu a leitura das ordens abertas (sem filtro)"
        return out
    if not lida_em:
        out["motivo"] = "leitura sem hora"
        return out
    if agora - lida_em > BYBIT_LEITURA_MAX_S:
        out["motivo"] = f"leitura com {int((agora - lida_em) // 60)} min"
        return out
    fecho = _lado_fecho(lado)
    minhas = [o for o in abertas or [] if o.get("symbol") == simbolo and o.get("side") == fecho and _protege(o)]
    ativas = [o for o in minhas if (o.get("orderStatus") or "Untriggered") in BYBIT_ATIVAS]
    for o in ativas:
        out["ordens"].append({
            "orderId": o.get("orderId"), "tipo": o.get("stopOrderType") or o.get("orderType") or None,
            "estado": o.get("orderStatus") or None, "lado": o.get("side"),
            "stop": _f(o.get("stopLoss")) or _f(o.get("triggerPrice")) or None,
            "objetivo": _f(o.get("takeProfit")) or None, "quantidade": _f(o.get("qty")),
            "criada": int(_f(o.get("createdTime")) / 1000) if _f(o.get("createdTime")) else None,
            "atualizada": int(_f(o.get("updatedTime")) / 1000) if _f(o.get("updatedTime")) else None})
    if ativas:
        out["estado"] = "ATIVA"
        sts = [x["stop"] for x in out["ordens"] if x["stop"]]
        out["stop"] = (max(sts) if lado == "LONG" else min(sts)) if sts else None
        tps = [x["objetivo"] for x in out["ordens"] if x["objetivo"]]
        out["objetivo"] = (min(tps) if lado == "LONG" else max(tps)) if tps else None
        out["quantidade"] = round(sum(x["quantidade"] or 0 for x in out["ordens"]), 12)
        if plano_stop and out["stop"] and abs(out["stop"] / plano_stop - 1) > BYBIT_DESVIO_PLANO:
            out["divergencias"].append(f"stop na corretora {out['stop']:g} difere do plano {plano_stop:g}")
        if estado_interno and estado_interno != "aberta":
            out["divergencias"].append(f"registo interno diz '{estado_interno}' mas a corretora tem protecao ativa")
        return out
    # sem protecao ativa: o historico diz se disparou ou foi cancelada; sem historico, so se sabe que nao ha ativa
    hist = historico if historico is not None else None
    estados = {h.get("estado") for h in hist or []}
    if estados & BYBIT_DISPARADAS:
        out["estado"] = "DISPARADA"
    elif estados & BYBIT_CANCELADAS:
        out["estado"] = "CANCELADA"
    else:
        out["estado"] = "INEXISTENTE"
    if hist is None:
        out["motivo"] = "sem ordem ativa; historico nao lido (nao se sabe se disparou)"
    if estado_interno == "aberta":
        out["divergencias"].append(f"registo interno diz 'aberta' e a corretora nao tem protecao ativa ({out['estado']})")
    return out
