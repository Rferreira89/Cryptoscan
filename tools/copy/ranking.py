"""(17/11) Avaliacao e ranking de traders (nunca so pelo ROI), com validacao fora da amostra temporal.

Retorno por operacao = retorno sobre o NOCIONAL (OKX: pnlRatio / alavancagem; Hyperliquid: PnL liquido de comissoes /
nocional), para comparar traders com alavancagens diferentes. Historico dividido no tempo: os primeiros 2/3 escolhem,
o ultimo 1/3 valida (a decisao so usa o que o trader ja fez antes de cada periodo: sem look-ahead).
Estados: APROVADO (pode ser copiado), OBSERVAR (so sinal), REJEITADO; com os motivos."""
import statistics

C = {"ops_min": 30, "dias_min": 14, "pf_min": 1.2, "pf_validacao_min": 1.1, "alav_max": 25, "top3_quota_max": 0.5,
     "ativo_quota_max": 0.6, "dur_min_h": 0.25, "dur_max_h": 48, "martingale_max": 0.25, "media_min": 0.0005}


def _ret(o):
    if o.get("retorno_nocional") is not None:
        return float(o["retorno_nocional"])
    return float(o.get("pnl_ratio") or 0) / max(1.0, float(o.get("alav") or 1))


def metricas(ops):
    if not ops:
        return {"n": 0}
    ops = sorted(ops, key=lambda o: o["t_fecha"])
    rs = [_ret(o) for o in ops]
    g, p = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    eq = pk = dd = 0.0
    for x in rs:
        eq += x
        pk, dd = max(pk, eq), max(dd, pk - eq)
    ganhos, perdas = [x for x in rs if x > 0], [x for x in rs if x < 0]
    por_ativo = {}
    for o in ops:
        por_ativo[o["base"]] = por_ativo.get(o["base"], 0) + 1
    top3 = sum(sorted(rs, reverse=True)[:3])
    dur = [(o["t_fecha"] - o["t_abre"]) / 3600 for o in ops if o.get("t_abre")]
    dias = max(1.0, (ops[-1]["t_fecha"] - ops[0]["t_abre"]) / 86400)
    alav = [float(o["alav"]) for o in ops if o.get("alav")]
    # martingale / reforco de perdedoras: operacao seguinte maior depois de uma perda, ou varias entradas na mesma posicao
    tam = [float(o.get("margem") or 0) * float(o.get("alav") or 1) for o in ops]
    maior_apos_perda = sum(1 for i in range(1, len(ops)) if rs[i - 1] < 0 and tam[i - 1] > 0 and tam[i] > 1.5 * tam[i - 1])
    reforcos = sum(1 for o in ops if (o.get("entradas") or 1) >= 3 and _ret(o) < 0)
    return {"n": len(ops), "dias": round(dias, 1), "r_medio": round(statistics.mean(rs), 5),
            "pnl_total": round(sum(rs), 4), "profit_factor": round(g / p, 3) if p else None,
            "acerto": round(len(ganhos) / len(rs), 3), "ganho_perda": round(statistics.mean(ganhos) / -statistics.mean(perdas), 3)
            if ganhos and perdas else None, "drawdown": round(dd, 4), "freq_dia": round(len(ops) / dias, 2),
            "duracao_media_h": round(statistics.mean(dur), 2) if dur else None,
            "alav_media": round(statistics.mean(alav), 1) if alav else None, "alav_max": max(alav) if alav else None,
            "quota_ativo": round(max(por_ativo.values()) / len(ops), 3), "ativos": len(por_ativo),
            "quota_top3": round(top3 / sum(rs), 3) if sum(rs) > 0 else None,
            "martingale": round((maior_apos_perda + reforcos) / len(ops), 3),
            "recente_r": round(statistics.mean(rs[-10:]), 5), "por_lado": {l: round(sum(_ret(o) for o in ops if o["lado"] == l), 4)
                                                                         for l in ("LONG", "SHORT")}}


def avaliar(trader, ops, posicoes=None):
    """Metricas completas + selecao/validacao temporal + comportamentos perigosos -> estado e motivos."""
    ops = sorted(ops or [], key=lambda o: o["t_fecha"])
    m = metricas(ops)
    corte = len(ops) * 2 // 3
    sel, val = metricas(ops[:corte]), metricas(ops[corte:])
    motivos, perigos = [], []
    if m["n"] < C["ops_min"] or (m.get("dias") or 0) < C["dias_min"]:
        motivos.append(f"historico insuficiente ({m['n']} operacoes, {m.get('dias')} dias)")
    if (m.get("martingale") or 0) > C["martingale_max"]:
        perigos.append(f"martingale/reforco de perdedoras em {m['martingale']:.0%} das operacoes")
    if (m.get("alav_max") or 0) > C["alav_max"]:
        perigos.append(f"alavancagem excessiva (ate {m['alav_max']:g}x)")
    if m.get("quota_top3") is not None and m["quota_top3"] > C["top3_quota_max"]:
        perigos.append(f"resultado depende de 3 operacoes ({m['quota_top3']:.0%})")
    if (m.get("quota_ativo") or 0) > C["ativo_quota_max"]:
        perigos.append(f"concentracao extrema num ativo ({m['quota_ativo']:.0%})")
    if m.get("drawdown") is not None and m.get("pnl_total") and m["drawdown"] > max(0.0, m["pnl_total"]):
        perigos.append("drawdown maior que o resultado total")
    if posicoes:
        rep = {}
        for p in posicoes:
            rep[(p["base"], p["lado"])] = rep.get((p["base"], p["lado"]), 0) + 1
        if max(rep.values()) >= 3:
            perigos.append("varias posicoes abertas no mesmo ativo e lado (reforcos/averaging)")
    ok_sel = sel.get("n", 0) >= 20 and (sel.get("r_medio") or 0) > C["media_min"] and (sel.get("profit_factor") or 0) >= C["pf_min"]
    ok_val = val.get("n", 0) >= 10 and (val.get("r_medio") or 0) > 0 and (val.get("profit_factor") or 0) >= C["pf_validacao_min"]
    if not ok_sel:
        motivos.append("periodo de selecao sem expectativa/PF suficientes")
    if not ok_val:
        motivos.append("validacao fora da amostra (ultimo terco) sem expectativa positiva/PF")
    if (m.get("recente_r") or 0) < 0:
        motivos.append("degradacao recente (ultimas 10 operacoes negativas em media)")
    dur = m.get("duracao_media_h")
    curto = dur is not None and C["dur_min_h"] <= dur <= C["dur_max_h"]
    if dur is not None and not curto:
        motivos.append(f"duracao media {dur:.1f} h fora de 15 min - 48 h")
    if perigos:
        estado = "REJEITADO"
    elif not motivos:
        estado = "APROVADO"
    elif m["n"] >= C["ops_min"] and ok_sel:
        estado = "OBSERVAR"
    else:
        estado = "REJEITADO" if m["n"] >= C["ops_min"] else "OBSERVAR"
    score = 0.0
    if m["n"]:
        score = ((val.get("r_medio") or 0) * 100 + min(2.0, (val.get("profit_factor") or 0)) * 0.5
                 + min(1.0, m["n"] / 100) * 0.3 - (m.get("drawdown") or 0) * 2 + (0.2 if curto and dur <= 4 else 0))
    return {**{k: trader.get(k) for k in ("fonte", "id", "nome")}, "estado": estado, "motivos": motivos, "perigos": perigos,
            "score": round(score, 4), "metricas": m, "selecao": sel, "validacao": val,
            "aviso": "validacao temporal simples; amostras pequenas nao provam vantagem"}
