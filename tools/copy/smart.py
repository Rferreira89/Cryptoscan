"""(17/11) SMART_COPY - decisao automatica por oportunidade (nova posicao de um trader seguido):
  COPY_DIRECT       trader APROVADO de topo, sinal fresco, preco ainda viavel, negociavel na OKX EEA
  CONFIRM_AND_COPY  trader APROVADO + confirmacao (outro trader aprovado no mesmo ativo/lado ou tendencia de 1 h a favor)
  SIGNAL_ONLY       sinal registado para a inteligencia (trader em observacao, sem confirmacao, ou corretora sem execucao)
  IGNORE            trader rejeitado, copia tardia, preco fugiu, duplicado, nao negociavel
Bybit EU: avaliada a parte (so spot e sem orcamento independente autorizado -> nunca copia, so SIGNAL_ONLY/IGNORE).
Aumentos de posicao do trader NAO sao copiados (sem piramidagem/reforcos); reducao >= 50% ou fecho -> fecho da copia."""

C = {"idade_max_s": 600, "desvio_max_pct": 0.30, "desvio_max_atr": 0.25, "topo_r_validacao": 0.003, "topo_pf": 1.5,
     "k_stop_atr": 1.5, "tp_r": 2.0, "hold_h": 4, "reducao_fecho": 0.5,
     "custo_ida_volta": 0.0012}           # comissoes ida e volta + meio spread tipico na OKX EEA (fracao do nocional)


def atr14(v):
    if not v or len(v) < 16:
        return None
    tr = [max(v[i]["h"] - v[i]["l"], abs(v[i]["h"] - v[i - 1]["c"]), abs(v[i]["l"] - v[i - 1]["c"])) for i in range(1, len(v))]
    return sum(tr[-14:]) / 14


def tendencia(v, n=20):
    """+1 / -1 / 0: inclinacao da media exponencial de 20 velas de 1 h (so velas fechadas)."""
    if not v or len(v) < n + 3:
        return 0
    a, ema = 2 / (n + 1), v[0]["c"]
    hist = []
    for b in v:
        ema = a * b["c"] + (1 - a) * ema
        hist.append(ema)
    d = hist[-1] - hist[-4]
    return 1 if d > 0 else -1 if d < 0 else 0


def decidir(op, trader, ctx):
    """op: nova posicao {base, lado, px_abre, t_abre|None, t_visto}; trader: avaliacao (ranking.avaliar);
    ctx: {now, xperps, preco, velas, consenso (n traders aprovados no mesmo ativo/lado), ja_ha_copia (bool)}.
    Devolve (decisao, motivo, plano|None)."""
    now = ctx["now"]
    if trader.get("estado") == "REJEITADO":
        return "IGNORE", "trader rejeitado: " + "; ".join((trader.get("perigos") or trader.get("motivos") or [])[:2]), None
    t0 = op.get("t_abre") or op.get("t_visto")
    idade = now - int(t0) if t0 else None
    inst = ctx["xperps"].get(op["base"])
    if trader.get("estado") != "APROVADO":
        return "SIGNAL_ONLY", "trader em observacao: " + "; ".join((trader.get("motivos") or [])[:2]), None
    if idade is None or idade > C["idade_max_s"]:
        return "IGNORE", f"copia tardia ({None if idade is None else idade // 60} min depois da entrada do trader)", None
    if not inst:
        return "SIGNAL_ONLY", "ativo sem X-Perp negociavel na OKX EEA", None
    if ctx.get("ja_ha_copia"):
        return "IGNORE", "ja ha sinal de copia aberto neste ativo (sem duplicar risco)", None
    px, v = ctx.get("preco"), ctx.get("velas")
    a = atr14(v)
    if not px or not a:
        return "IGNORE", "sem preco/ATR fiaveis na OKX EEA", None
    d = 1 if op["lado"] == "LONG" else -1
    ref = op["px_abre"] * float(op.get("fator_px") or 1.0)          # Hyperliquid kPEPE e o preco de 1000 PEPE
    contra = d * (px - ref) / ref * 100          # quanto o preco ja andou a favor do trader
    if contra > C["desvio_max_pct"] or abs(px - ref) > C["desvio_max_atr"] * C["k_stop_atr"] * a:
        return "IGNORE", f"preco ja nao e viavel ({contra:+.2f}% desde a entrada do trader)", None
    v_ = trader.get("validacao") or {}
    if (v_.get("r_medio") or 0) - C["custo_ida_volta"] <= 0:
        return "SIGNAL_ONLY", f"expectativa do trader ({(v_.get('r_medio') or 0):.3%}) nao cobre os custos ({C['custo_ida_volta']:.2%})", None
    topo = (v_.get("r_medio") or 0) >= C["topo_r_validacao"] and (v_.get("profit_factor") or 0) >= C["topo_pf"]
    conf = ctx.get("consenso", 0) >= 1 or tendencia(v) == d
    plano = {"inst": inst, "ref": ref, "atr": a, "stop": px - d * C["k_stop_atr"] * a,
             "alvo": px + d * C["tp_r"] * C["k_stop_atr"] * a}
    if topo:
        return "COPY_DIRECT", "trader aprovado de topo, sinal fresco e preco viavel", plano
    if conf:
        return "CONFIRM_AND_COPY", ("confirmado por outro trader aprovado" if ctx.get("consenso", 0) >= 1
                                    else "confirmado pela tendencia de 1 h"), plano
    return "SIGNAL_ONLY", "trader aprovado mas sem confirmacao", None


def decidir_bybit(op, spot_bybit):
    if op["lado"] == "SHORT":
        return "IGNORE", "Bybit EU: so spot, sem SHORT"
    if spot_bybit is None:
        return "SIGNAL_ONLY", "Bybit EU: lista de pares spot indisponivel nesta volta"
    if op["base"] not in spot_bybit:
        return "IGNORE", "Bybit EU: ativo sem par spot"
    return "SIGNAL_ONLY", "Bybit EU: execucao bloqueada (sem orcamento independente autorizado; o capital e do executor existente)"
