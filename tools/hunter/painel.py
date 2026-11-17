"""Painel de validacao e promocao automatica entre estados de INVESTIGACAO.

Estados: EXPLORATORIA -> EM_VALIDACAO -> PAPEL -> ELEGIVEL_REVISAO_HUMANA (ou REJEITADA, com a razao).
A promocao e automatica so entre estes estados; trading real exige sempre autorizacao explicita separada (nao
existe aqui nenhum caminho para la). O painel usa TREINO + VALIDACAO (o teste final fica intocado) e o papel
prospetivo; nunca soma papel a real.

Por estrategia: operacoes, dias distintos, acontecimentos independentes (velas de sinal distintas), media e
mediana liquidas, IC 95% por blocos de DIAS e por blocos de ACONTECIMENTOS, drawdown, profit factor, por regime
(subida/queda/lateral), por escalao de liquidez, custos medios e peso, frequencia semanal, estabilidade mensal,
dependencia das 3 melhores moedas, executabilidade dos stops, duracao e classe de horizonte, antes/depois de custos.
"""
import statistics
import time

from tools.hunter import estat as ES

MIN = {"n": 100, "dias": 30, "acontecimentos": 30, "meses_positivos": 0.6, "dd_max_r": 20.0,
       "papel_n": 30, "papel_dias": 14, "regimes_positivos": 2, "top3_quota_max": 0.5}
HORIZONTE_RAPIDO_MIN = 240


def metricas(ops):
    if not ops:
        return {"n": 0}
    rs = [o["r"] for o in ops]
    m_d, ic_d, p_d = ES.bootstrap_blocos([{"t": o["t"], "x": o["r"]} for o in ops], "x")
    m_e, ic_e, p_e = ES.bootstrap_blocos([{"t": o["t"], "x": o["r"]} for o in ops], "x", bloco=1)   # por vela
    ganhos, perdas = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    eq = pk = dd = 0.0
    for o in sorted(ops, key=lambda o: o["t"]):
        eq += o["r"]
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    por = lambda k: {g: [len(v), round(sum(o["r"] for o in v) / len(v), 3)] for g, v in _grupo(ops, k).items()}
    meses = _grupo(ops, lambda o: time.strftime("%Y-%m", time.gmtime(o["t"])))
    moedas = sorted(((sum(o["r"] for o in v), b) for b, v in _grupo(ops, "b").items()), reverse=True)
    top3 = sum(x for x, _ in moedas[:3])
    total = sum(rs)
    stops = [o for o in ops if o.get("saida") == "stop"]
    semanas = max(1.0, (max(o["t"] for o in ops) - min(o["t"] for o in ops)) / (7 * 86400))
    custo = statistics.mean(o.get("custos_r", 0) for o in ops)
    bruto = statistics.mean(o.get("bruto_r", o["r"]) for o in ops)
    minutos = statistics.mean(o.get("minutos", 0) for o in ops)
    return {
        "n": len(ops), "dias": len({o["t"] // 86400 for o in ops}), "acontecimentos": len({o["t"] for o in ops}),
        "moedas": len(moedas), "r_medio": round(statistics.mean(rs), 4), "r_mediana": round(statistics.median(rs), 4),
        "ic95_blocos_dia": ic_d, "ic95_blocos_acontecimento": ic_e, "p_blocos_dia": round(p_d, 4),
        "drawdown_r": round(dd, 2), "profit_factor": round(ganhos / perdas, 3) if perdas else None,
        "por_regime": por("regime3"), "por_tier": por("tier"),
        "custo_medio_r": round(custo, 4), "bruto_medio_r": round(bruto, 4),
        "peso_custos": round(custo / abs(bruto), 3) if bruto else None,
        "rentavel_antes_mas_nao_depois_dos_custos": bool(bruto > 0 >= statistics.mean(rs)),
        "operacoes_por_semana": round(len(ops) / semanas, 2),
        "meses": {k: [len(v), round(sum(o["r"] for o in v), 2)] for k, v in sorted(meses.items())},
        "fracao_meses_positivos": round(sum(1 for v in meses.values() if sum(o["r"] for o in v) > 0) / len(meses), 2),
        "top3_moedas": [b for _, b in moedas[:3]], "quota_top3": round(top3 / total, 3) if total > 0 else None,
        "r_sem_top3_moedas": round((total - top3) / max(1, len(rs) - sum(len(_grupo(ops, "b")[b]) for _, b in moedas[:3])), 4),
        "stop_medio_pct": round(statistics.mean(o.get("stop_pct", 0) for o in ops), 3),
        "stops_com_gap_pct": round(100 * sum(1 for o in stops if o["r"] < -1.15 - o.get("custos_r", 0)) / len(stops), 1)
        if stops else 0.0,
        "duracao_media_min": round(minutos), "horizonte": "rapido (30 min - 4 h)" if minutos <= HORIZONTE_RAPIDO_MIN
        else "HORIZONTE SUPERIOR (> 4 h): nao e oportunidade rapida",
    }


def _grupo(ops, k):
    out = {}
    for o in ops:
        out.setdefault(k(o) if callable(k) else o.get(k), []).append(o)
    return out


def criterios(m, p_holm, teste, papel):
    """[(criterio, ok, detalhe)] para ELEGIVEL_REVISAO_HUMANA."""
    c = []
    c.append(("amostra >= 100 operacoes", m.get("n", 0) >= MIN["n"], m.get("n")))
    c.append(("dias distintos >= 30", m.get("dias", 0) >= MIN["dias"], m.get("dias")))
    c.append(("acontecimentos independentes >= 30", m.get("acontecimentos", 0) >= MIN["acontecimentos"], m.get("acontecimentos")))
    c.append(("expectativa liquida > 0", (m.get("r_medio") or 0) > 0, m.get("r_medio")))
    ic = m.get("ic95_blocos_acontecimento") or m.get("ic95_blocos_dia")
    c.append(("IC 95% (blocos) acima de 0", bool(ic and ic[0] > 0 and (m.get("ic95_blocos_dia") or [0])[0] > 0), ic))
    c.append(("sobrevive a Holm cumulativo", p_holm is not None and p_holm < 0.05, p_holm))
    c.append(("resultado fora da amostra (teste final)", bool(teste and teste.get("n", 0) >= 30 and (teste.get("r_medio") or 0) > 0
                                                         and teste.get("p_r_positivo", 1) < 0.05), (teste or {}).get("r_medio")))
    c.append(("estabilidade mensal >= 60% meses positivos", (m.get("fracao_meses_positivos") or 0) >= MIN["meses_positivos"],
              m.get("fracao_meses_positivos")))
    reg = [v for k, v in (m.get("por_regime") or {}).items() if k != "?" and v[0] >= 20]
    c.append(("positiva em >= 2 regimes (n >= 20)", sum(1 for v in reg if v[1] > 0) >= MIN["regimes_positivos"], m.get("por_regime")))
    c.append(("custos realistas: positiva depois de custos por escalao", not m.get("rentavel_antes_mas_nao_depois_dos_custos")
              and (m.get("r_medio") or 0) > 0, m.get("peso_custos")))
    c.append(("nao depende de 3 moedas (quota < 50% e R sem elas > 0)", m.get("quota_top3") is not None
              and m["quota_top3"] < MIN["top3_quota_max"] and (m.get("r_sem_top3_moedas") or 0) > 0, m.get("quota_top3")))
    c.append(("drawdown <= 20R", (m.get("drawdown_r") or 99) <= MIN["dd_max_r"], m.get("drawdown_r")))
    pa = papel or {}
    c.append(("papel prospetivo: >= 30 fechadas em >= 14 dias com media > 0",
              pa.get("n", 0) >= MIN["papel_n"] and pa.get("dias", 0) >= MIN["papel_dias"] and (pa.get("r_medio") or 0) > 0,
              {k: pa.get(k) for k in ("n", "dias", "r_medio")}))
    return c


def estado(m, crit, em_papel, rejeitar_papel=None):
    """Maquina de estados (so investigacao)."""
    if rejeitar_papel:
        return "REJEITADA", rejeitar_papel
    ok = {k: v for k, v, _ in crit}
    if all(ok.values()):
        return "ELEGIVEL_REVISAO_HUMANA", "todos os criterios cumpridos (passagem a real exige autorizacao explicita)"
    base = ok["amostra >= 100 operacoes"] and ok["dias distintos >= 30"] and ok["expectativa liquida > 0"]
    if base and em_papel:
        return "PAPEL", "em validacao prospetiva"
    if base:
        return "EM_VALIDACAO", "amostra minima e expectativa > 0; faltam significancia/estabilidade"
    return "EXPLORATORIA", "amostra ou expectativa insuficientes"


def rejeicao_papel(pa):
    """Rejeita com dados prospetivos suficientes e resultado claramente negativo, ou degradada pela sobrevivencia."""
    if not pa:
        return None
    if pa.get("n", 0) >= MIN["papel_n"] and pa.get("dias", 0) >= MIN["papel_dias"] and (pa.get("r_medio") or 0) < -0.1:
        return f"papel prospetivo negativo: {pa['n']} op., media {pa['r_medio']:+.3f}R"
    if pa.get("novas_entradas") is False:
        return "degradada no papel (motor de sobrevivencia): " + "; ".join(pa.get("motivos") or [])
    return None
