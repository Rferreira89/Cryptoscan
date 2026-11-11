"""(2026-11-11, missao rentabilidade, Fase 1) Auditoria de rentabilidade das estrategias EXISTENTES, por corretora.

So le copias publicas (state.json, scan.json, okx.json, forma.json, longo.json, contabilidade_okx.json), as operacoes
de backtest com hora e ativo (backtest/quant --com-ativo) e as velas publicas (ramo history). Nao chama corretoras,
nao escreve estado de estrategias, nao muda filtros. So R: nunca dinheiro.

Ambientes NUNCA se misturam: BACKTEST, ARENA (re-simulacao de 90/365 dias, so agregados), PAPEL, SOMBRA, REAL.
Acontecimento independente = dia UTC de entrada (as operacoes do mesmo dia mexem-se juntas). A expectativa por
acontecimento e a media, entre dias, do R medio desse dia; o intervalo vem de bootstrap por dias.

Classificacao (regras escritas antes de olhar para a tabela final; ver classificar()):
  A  vantagem demonstrada: REAL com >= 30 dias, media liquida > 0 e limite inferior (90%) > 0, e o backtest fora
     da amostra no mesmo sentido. Backtest sozinho NUNCA chega para A.
  E  manter suspensa: resultado liquido negativo em REAL ou PAPEL (>= 10 operacoes) E backtest/arena sem vantagem
     fora da amostra (ou negativa).
  B  promissora inconclusiva: liquido > 0 fora da amostra (backtest ou arena), acima do acaso, sem prova suficiente
     em dinheiro real; inclui "so num regime".
  D  tecnicamente bloqueada: ha sinais e o problema e de execucao (ordem por preencher, contrato, minimo, dados).
     Marcada como bandeira em qualquer classe e como classe quando nao ha prova contra a estrategia.
  C  sem vantagem demonstrada: o resto.
Uso: python3 -m tools.auditoria_rentabilidade <pasta_publica> <bt_ops_ativo.json> <pasta_history> <saida.json>"""
import datetime as _dt
import json
import math
import os
import random
import sys
from collections import defaultdict

DAY = 86400
H4 = 14400
CORTE = 1778198400            # 2026-05-08: inicio da reserva (contaminada: o que se valida ali fica em PARA PAPEL)
DESENHO_ATE = 1719792000      # 2024-07-01: walk-forward desenha antes, valida depois (ate CORTE)
CUSTO_BASE = {"okx_perp": 0.20, "bybit_spot": 0.70}          # % ida e volta ja incluidos no R do backtest
ATR_N = 42                    # stop das H40/H45/H46: 2 x ATR42 de 4H (engine/papel_panico, tools/okx_recuo)


def _r(x, k=4):
    return None if x is None else round(x, k)


def _ano(t):
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).year


# ---------------------------------------------------------------- metricas
def por_dia(ops):
    d = defaultdict(list)
    for o in ops:
        d[int(o["t_entrada"]) // DAY].append(o["R"])
    return d


def bootstrap_dias(ops, reps=2000, rng=None, q=(0.05, 0.95)):
    """Intervalo da expectativa por acontecimento (media dos dias), sorteando dias com reposicao."""
    dias = [sum(v) / len(v) for v in por_dia(ops).values()]
    if len(dias) < 5:
        return None, None
    rng = rng or random.Random(11)
    ms = sorted(sum(rng.choice(dias) for _ in dias) / len(dias) for _ in range(reps))
    return ms[int(q[0] * reps)], ms[int(q[1] * reps) - 1]


def bootstrap_op_agrupado(ops, reps=2000, rng=None, q=(0.05, 0.95)):
    """Intervalo da expectativa POR OPERACAO quando as operacoes do mesmo dia nao sao independentes: sorteiam-se
    dias inteiros (soma de R e numero de operacoes do dia) e a estatistica e soma / numero."""
    g = [(sum(v), len(v)) for v in por_dia(ops).values()]
    if len(g) < 5:
        return None, None
    rng = rng or random.Random(13)
    ms = []
    for _ in range(reps):
        s = n = 0
        for _ in g:
            a, b = rng.choice(g)
            s += a
            n += b
        ms.append(s / n)
    ms.sort()
    return ms[int(q[0] * reps)], ms[int(q[1] * reps) - 1]


def limitar_por_dia(ops, k):
    """O que um limite de k posicoes por dia deixaria entrar: as k primeiras pela hora de entrada (empates pelo ativo,
    ordem fixa e sem olhar para o resultado)."""
    d = defaultdict(list)
    for o in sorted(ops, key=lambda o: (o["t_entrada"], str(o.get("ativo")))):
        d[o["t_entrada"] // DAY].append(o)
    return [o for xs in d.values() for o in xs[:k]]


def limitar_simultaneas(ops, k, rng=None):
    """O que um teto de k posicoes ABERTAS ao mesmo tempo deixaria entrar (como risco_total_max / risco por operacao).
    Empates na mesma hora: ordem fixa pelo ativo, ou ao acaso com rng (para tirar o efeito da ordem)."""
    chave = (lambda o: (o["t_entrada"], rng.random())) if rng else (lambda o: (o["t_entrada"], str(o.get("ativo"))))
    abertas, out = [], []
    for o in sorted(ops, key=chave):
        abertas = [t for t in abertas if t > o["t_entrada"]]
        if len(abertas) < k:
            out.append(o)
            abertas.append(o.get("t_saida") or o["t_entrada"])
    return out


def teto_ao_acaso(ops, k, reps=200, rng=None):
    """Media e intervalo 5-95% da expectativa por operacao com o teto de k abertas, sorteando a ordem dos empates."""
    rng = rng or random.Random(17)
    ms = []
    for _ in range(reps):
        xs = limitar_simultaneas(ops, k, rng)
        if xs:
            ms.append(sum(o["R"] for o in xs) / len(xs))
    if not ms:
        return {}
    ms.sort()
    return {"media_op": _r(sum(ms) / len(ms)), "p05": _r(ms[int(0.05 * len(ms))]), "p95": _r(ms[int(0.95 * len(ms)) - 1]),
            "n_tipico": len(limitar_simultaneas(ops, k, random.Random(1)))}


def metricas(ops, rng=None, reps=2000):
    if not ops:
        return {"n": 0}
    rs = [o["R"] for o in ops]
    n = len(rs)
    g, p = [x for x in rs if x > 0], [x for x in rs if x <= 0]
    pd = por_dia(ops)
    dias = [sum(v) / len(v) for v in pd.values()]
    md = sum(dias) / len(dias)
    sd = math.sqrt(sum((x - md) ** 2 for x in dias) / (len(dias) - 1)) if len(dias) > 1 else 0.0
    eq = pico = dd = 0.0
    for o in sorted(ops, key=lambda o: o.get("t_saida") or o["t_entrada"]):
        eq += o["R"]
        pico = max(pico, eq)
        dd = min(dd, eq - pico)
    lo, hi = bootstrap_dias(ops, reps, rng)
    lo_o, hi_o = bootstrap_op_agrupado(ops, reps, rng)
    return {"n": n, "dias": len(pd), "media_op": _r(sum(rs) / n), "media_dia": _r(md), "soma": _r(sum(rs), 2),
            "pf": _r(sum(g) / -sum(p), 3) if p and sum(p) < 0 else None, "win": _r(len(g) / n, 3),
            "payoff": _r((sum(g) / len(g)) / (-sum(p) / len(p)), 3) if g and p and sum(p) < 0 else None,
            "max_dd_r": _r(dd, 2), "t_dia": _r(md / (sd / math.sqrt(len(dias))), 2) if sd > 0 else None,
            "ic90_dia": [_r(lo), _r(hi)], "ic90_op_agrupado": [_r(lo_o), _r(hi_o)],
            "dias_maiores_5_pct_do_r": _r(sum(sorted((sum(v) for v in pd.values()), reverse=True)[:max(1, len(pd) // 20)]) / sum(rs), 3)
            if sum(rs) > 0 else None}


# ---------------------------------------------------------------- regime e stops a partir das velas publicas
def btc_regime(btc_4h):
    """dia -> True se o fecho diario do BTC do DIA ANTERIOR estava acima da SMA50 diaria (sem retrospetiva)."""
    fecho = {}
    for t, c in btc_4h:
        fecho[int(t) // DAY] = c                     # a ultima vela de 4H do dia fica como fecho
    ds = sorted(fecho)
    out = {}
    for i in range(49, len(ds)):
        sma = sum(fecho[d] for d in ds[i - 49:i + 1]) / 50   # SMA50 ate ao dia ds[i], inclusive
        out[ds[i] + 1] = fecho[ds[i]] > sma                  # vale para o dia SEGUINTE
    return out


def stop_pct(barras, t):
    """Distancia do stop (2 x ATR42 de 4H) em % do preco, com as velas FECHADAS antes de t."""
    if not barras:
        return None
    lo, hi = 0, len(barras)
    while lo < hi:
        m = (lo + hi) // 2
        if barras[m]["t"] + H4 <= t:
            lo = m + 1
        else:
            hi = m
    i = lo                                            # barras[:i] fechadas antes de t
    if i < ATR_N + 1:
        return None
    trs = [max(barras[k]["h"], barras[k - 1]["c"]) - min(barras[k]["l"], barras[k - 1]["c"]) for k in range(i - ATR_N, i)]
    c = barras[i - 1]["c"]
    return 2 * (sum(trs) / ATR_N) / c * 100 if c else None


def sensibilidade(ops, extra=(0.1, 0.2, 0.5)):
    """Expectativa por operacao com custos extra (% ida e volta) e o custo extra que a anula. Precisa de stop_pct."""
    com = [o for o in ops if o.get("stop_pct")]
    if not com:
        return {"cobertura": 0}
    base = sum(o["R"] for o in com) / len(com)
    inv = sum(1 / o["stop_pct"] for o in com) / len(com)       # R perdido por cada 1% de custo extra
    return {"cobertura": _r(len(com) / len(ops), 3), "stop_pct_mediano": _r(sorted(o["stop_pct"] for o in com)[len(com) // 2], 2),
            "r_por_0_1pct": _r(0.1 * inv), "media_op": _r(base),
            **{f"media_op_mais_{x}pct": _r(base - x * inv) for x in extra},
            "custo_extra_que_anula_pct": _r(base / inv, 3) if inv else None}


# ---------------------------------------------------------------- BACKTEST (operacoes com hora e ativo)
def auditar_backtest(ops, regime, barras=None, rng=None, reps=2000):
    barras = barras or {}
    out = {}
    por = defaultdict(list)
    for o in ops:
        por[o["estrategia"]].append(dict(o))
    for est, xs in sorted(por.items()):
        for o in xs:
            o["stop_pct"] = stop_pct(barras.get(o.get("ativo")), o["t_entrada"])
        sub = lambda f: metricas([o for o in xs if f(o)], rng, reps)
        anos = sorted({_ano(o["t_entrada"]) for o in xs})
        por_ativo = defaultdict(list)
        for o in xs:
            por_ativo[o.get("ativo")].append(o["R"])
        melhor = max(por_ativo, key=lambda a: sum(por_ativo[a])) if por_ativo else None
        out[est] = {
            "nota": xs[0].get("nota"), "tudo": metricas(xs, rng, reps),
            "desenho_ate_2024_06": sub(lambda o: o["t_entrada"] < DESENHO_ATE),
            "validacao_2024_07_a_reserva": sub(lambda o: DESENHO_ATE <= o["t_entrada"] < CORTE),
            "reserva_contaminada": sub(lambda o: o["t_entrada"] >= CORTE),
            "por_regime": {"btc_acima_sma50": sub(lambda o: regime.get(o["t_entrada"] // DAY) is True),
                           "btc_abaixo_sma50": sub(lambda o: regime.get(o["t_entrada"] // DAY) is False)},
            "por_ano": {a: sub(lambda o, a=a: _ano(o["t_entrada"]) == a) for a in anos},
            "sem_melhor_moeda": {"moeda": melhor, **sub(lambda o: o.get("ativo") != melhor)},
            "moedas": len(por_ativo),
            "custos": sensibilidade(xs),
            "limite_3_por_dia": metricas(limitar_por_dia(xs, 3), rng, reps),
            "limite_1_por_dia": metricas(limitar_por_dia(xs, 1), rng, reps),
            "teto_3_abertas_ao_acaso": teto_ao_acaso([o for o in xs if o["t_entrada"] < CORTE], 3)}
    return out


# ---------------------------------------------------------------- REAL / PAPEL / SOMBRA
def auditar_ambientes(ops, rng=None, reps=2000):
    por = defaultdict(list)
    for o in ops:
        por[(o["ambiente"], o["estrategia"])].append(o)
    return {f"{a}|{e}": metricas(xs, rng, reps) for (a, e), xs in sorted(por.items())}


# ---------------------------------------------------------------- ARENA Bybit (agregados publicos)
def auditar_arena(forma, longo, scan, state, real_ok):
    lf = (forma or {}).get("lutadores") or {}
    ll = (longo or {}).get("lutadores") or {}
    cls = {x["id"]: x for x in (((scan or {}).get("arena") or {}).get("classificacao") or [])}
    desl = (scan or {}).get("disabled_strategies") or {}
    susp = (state or {}).get("suspensos") or {}
    clones = (longo or {}).get("clones") or {}
    out = {}
    for k in sorted(set(lf) | set(ll) | set(cls)):
        f, l, c = lf.get(k) or {}, ll.get(k) or {}, cls.get(k) or {}
        val = l.get("validacao") or {}
        reg = {}
        for nome, r in (l.get("por_regime") or {}).items():
            q = r.get("qualidade") or {}
            reg[nome] = {"n": r.get("n"), "avg_r": r.get("avg_r"), "acaso_p95": r.get("acaso_p95"), "dias": q.get("dias"),
                         "ic_inf_dia": q.get("ic_inf"), "antes": (q.get("antes") or {}).get("avg_r"),
                         "reservado": (q.get("reservado") or {}).get("avg_r"), "sem_melhor_moeda": q.get("sem_melhor_moeda"),
                         "passa_novo": r.get("passa_novo")}
        out[k] = {"estado_arena": c.get("estado"), "motivo_arena": c.get("motivo"), "real_ok": k in real_ok,
                  "desligada": (desl.get(k) or {}).get("motivo"), "suspensa": susp.get(k),
                  "clone_de": (clones.get(k) or {}).get("de"),
                  "d90": {"n": f.get("n"), "avg_r": f.get("avg_r"), "acaso_p95": f.get("acaso_p95"),
                          "fora_n": ((f.get("validacao") or {}).get("fora") or {}).get("n"),
                          "fora_liq": ((f.get("validacao") or {}).get("fora") or {}).get("avg_r_liq")},
                  "d365": {"n": l.get("n"), "avg_r": l.get("avg_r"), "avg_r_liq": val.get("avg_r_liq"), "acaso_p95": l.get("acaso_p95"),
                           "dentro_liq": (val.get("dentro") or {}).get("avg_r_liq"),
                           "fora_n": (val.get("fora") or {}).get("n"), "fora_liq": (val.get("fora") or {}).get("avg_r_liq")},
                  "por_regime": reg,
                  # (t, R) dos ultimos 45 dias: mostra quantos DIAS independentes estao por tras do n de operacoes
                  "ultimos_45d": metricas([{"t_entrada": t, "R": r_} for t, r_ in (l.get("recentes") or [])], reps=500)}
    return out


# ---------------------------------------------------------------- execucao OKX (D)
def execucao_okx(O):
    real = (O or {}).get("real") or {}
    papel = {f"{f['asset']}:{f['t_sig']}": f for f in (O or {}).get("fechadas") or []}
    linhas = []
    for h in real.get("hist") or []:
        ch = f"{h.get('asset')}:{h.get('t_sig')}"
        p = papel.get(ch) or {}
        r_real = (h["saida"] - h["entrada"]) / (h["entrada"] - h["stop"]) if h.get("saida") and h.get("entrada") and h.get("stop") and h["entrada"] != h["stop"] else None
        linhas.append({"chave": ch, "estado": h.get("estado"), "tipo_papel": p.get("tipo"), "r_papel": p.get("r"),
                       "r_real_bruto": _r(r_real, 3), "atraso_ordem_min": _r(((h.get("criado") or 0) - (h.get("t_sig") or 0) - H4) / 60, 1),
                       "papel_preencheu": ch in papel})
    feitas = [x for x in linhas if x["estado"] == "fechada"]
    canc = [x for x in linhas if x["estado"] == "cancelada"]
    div = [x for x in canc if x["papel_preencheu"]]
    return {"ordens": len(linhas), "preenchidas": len(feitas), "canceladas_sem_executar": len(canc),
            "papel_preencheu_mas_real_nao": [x["chave"] for x in div],
            "preenchidas_por_tipo": dict(_conta(x["tipo_papel"] for x in feitas)),
            "canceladas_por_tipo": dict(_conta(x["tipo_papel"] for x in canc)),
            "r_papel_das_canceladas": [x["r_papel"] for x in canc if x["r_papel"] is not None],
            "r_real_das_preenchidas": [x["r_real_bruto"] for x in feitas],
            "linhas": linhas}


def _conta(it):
    c = defaultdict(int)
    for x in it:
        c[x or "?"] += 1
    return c


# ---------------------------------------------------------------- sinais bloqueados da Bybit (state.promo_lost)
def bloqueados_bybit(promo_lost, barras, horas=72, custo=CUSTO_BASE["bybit_spot"] / 100, juros_dia=0.0003):
    """Resultado hipotetico das promocoes perdidas, SEM retrospetiva: entra na abertura da primeira vela de 4H que
    abre depois do sinal, sai no fecho ao fim de 'horas'; SHORT_* vende (paga juros de margem); custos Bybit.
    O registo nao guarda stop/objetivo: e um substituto em % (nao R) e diz so se o bloqueio deixou passar dinheiro."""
    n_velas = horas * 3600 // H4
    g = defaultdict(list)
    sem = 0
    for x in promo_lost or []:
        c = barras.get(x.get("asset"))
        i = next((k for k, b in enumerate(c) if b["t"] >= x["t"]), None) if c else None
        if i is None or i + n_velas > len(c):
            sem += 1
            continue
        r = c[i + n_velas - 1]["c"] / c[i]["o"] - 1
        short = str(x.get("strategy")).startswith("SHORT")
        liq = (-r - custo - juros_dia * horas / 24) if short else (r - custo)
        g[(("SHORT_*" if short else x.get("strategy")), (x.get("reason") or "").split(":")[0])].append((liq, x["t"] // DAY))
    out = {f"{k[0]} | {k[1]}": {"n": len(v), "dias": len({d for _, d in v}), "liquido_medio_pct": _r(100 * sum(a for a, _ in v) / len(v), 2),
                                 "positivos": sum(1 for a, _ in v if a > 0)} for k, v in sorted(g.items())}
    return {"grupos": out, "sem_dados": sem, "nota": f"substituto: {horas} h, entrada na abertura seguinte, custos Bybit, sem stop"}


# ---------------------------------------------------------------- classificacao
def classificar(e):
    """e: {real, papel, bt_fora, bt_fora_ic_inf, arena_fora_liq, arena_fora_n, acima_acaso, regime_b, bloqueio}."""
    real, papel = e.get("real") or {}, e.get("papel") or {}
    porque = []
    if real.get("dias", 0) >= 30 and (real.get("media_dia") or 0) > 0 and ((real.get("ic90_dia") or [None])[0] or -1) > 0 \
            and (e.get("bt_fora") or 0) > 0:
        return "A", ["real com >= 30 dias, positivo e com limite inferior > 0; backtest fora da amostra concorda"]
    neg_vivo = [nm for nm, m in (("real", real), ("papel", papel)) if m.get("n", 0) >= 10 and (m.get("media_op") or 0) < 0]
    sem_fora = (e.get("bt_fora") is None or e["bt_fora"] <= 0) and (e.get("arena_fora_liq") is None or e["arena_fora_liq"] <= 0
                                                                   or (e.get("arena_fora_n") or 0) < 5)
    if neg_vivo and sem_fora:
        return "E", [f"negativa em {', '.join(neg_vivo)} e sem vantagem fora da amostra"]
    bt_ok = (e.get("bt_fora") or 0) > 0 and (e.get("bt_fora_ic_inf") or -1) > 0
    ar_ok = (e.get("arena_fora_liq") or 0) > 0 and (e.get("arena_fora_n") or 0) >= 5 and e.get("acima_acaso") \
        and (e.get("arena_liq") or 0) > 0                 # o ano inteiro tambem tem de ser liquido positivo
    if bt_ok or ar_ok or e.get("regime_b"):
        if bt_ok:
            porque.append("backtest fora da amostra (2024-07 a 2026-05) positivo com limite inferior > 0")
        if ar_ok:
            porque.append("arena: liquido fora da amostra > 0 e acima do acaso")
        if e.get("regime_b"):
            porque.append(f"so em {e['regime_b']}: acima do acaso e limite inferior por dia > 0")
        if neg_vivo:
            porque.append(f"MAS negativa em {', '.join(neg_vivo)}")
        porque.append("sem 30 dias independentes em dinheiro real")
        return ("D" if e.get("bloqueio") and not neg_vivo else "B"), porque + ([f"bloqueio: {e['bloqueio']}"] if e.get("bloqueio") else [])
    tem_prova = e.get("bt_fora") is not None or e.get("arena_liq") is not None
    if e.get("bloqueio") and not tem_prova:
        return "D", [f"bloqueio tecnico: {e['bloqueio']}", "sem prova de vantagem nem contra"]
    return "C", ["sem vantagem demonstrada fora da amostra" + (f"; negativa em {', '.join(neg_vivo)}" if neg_vivo else "")]


# ---------------------------------------------------------------- tabela por estrategia e corretora
def _fecho_tipo(O, tipo):
    return [{"t_entrada": f["t_sig"], "t_saida": f.get("t_fim"), "R": f["r"]} for f in (O or {}).get("fechadas") or []
            if f.get("tipo") == tipo and f.get("r") is not None]


def tabela(r, O, St, S):
    bt, amb, ar, exe = r["backtest"], r["ambientes"], r["arena_bybit"], r["execucao_okx"]
    linhas = []

    def bt_e(nome):
        x = bt.get(nome) or {}
        v = x.get("validacao_2024_07_a_reserva") or {}
        return {"bt_fora": v.get("media_dia"), "bt_fora_ic_inf": (v.get("ic90_dia") or [None])[0]}

    def add(corretora, est, e, notas, fontes):
        c, porque = classificar(e)
        band = ["D: " + e["bloqueio"]] if e.get("bloqueio") else []
        linhas.append({"corretora": corretora, "estrategia": est, "classe": c, "porque": porque, "bandeiras": band,
                       "notas": notas, "fontes": fontes})

    papel_m = metricas(_fecho_tipo(O, "mercado"), reps=500)
    papel_i = metricas(_fecho_tipo(O, "isolado"), reps=500)
    m_bt = bt.get("H40 (panico do mercado)") or {}
    add("OKX", "H40 panico do MERCADO (real desligado desde 10/11)",
        {**bt_e("H40 (panico do mercado)"), "papel": papel_m, "real": {},
         "bloqueio": (f"{exe['canceladas_sem_executar']} de {exe['ordens']} ordens reais canceladas sem executar, todas do tipo "
                      f"mercado ou sem tipo; o papel preencheu {len(exe['papel_preencheu_mas_real_nao'])} delas")},
        [f"backtest: {m_bt.get('tudo', {}).get('media_op')}R por operacao mas {m_bt.get('tudo', {}).get('media_dia')}R por dia "
         f"({m_bt.get('tudo', {}).get('dias')} dias); com o limite de 3 posicoes por dia "
         f"{(m_bt.get('limite_3_por_dia') or {}).get('media_op')}R por operacao"],
        ["backtest", "papel", "real"])
    add("OKX", "H40 panico ISOLADO",
        {**bt_e("H40 (panico isolado = todos menos mercado)"), "papel": papel_i, "real": amb.get("OKX_REAL|H40") or {}},
        ["as 4 operacoes reais fechadas foram todas deste tipo (todas no stop)"], ["backtest", "papel", "real"])
    rec = (O or {}).get("recuo") or {}
    add("OKX", "H46 recuo RSI<30 (real ligado, 1%)",
        {**bt_e("H46 (RSI<30)"), "papel": metricas([{"t_entrada": f.get("t_sig") or f.get("t"), "R": f["r"]} for f in rec.get("fechadas") or []
                                                    if f.get("r") is not None], reps=500), "real": {}},
        ["0 sinais desde 04/11: exige BTC acima da SMA50 e a subir (regime, nao bloqueio tecnico)"], ["backtest", "papel"])
    t = _j_ok(r.get("_tfshort"))
    add("OKX", "TF-SHORT U2 (so papel)", {"papel": {"n": 0}, "real": {}},
        ["0 operacoes fechadas no registo 'conta'; o backtest citado no codigo (+0,166R) nao tem operacoes publicas para auditar"],
        ["papel"])
    mac = (O or {}).get("macro") or {}
    rs = [f.get("ret_pct") for f in mac.get("fechadas") or [] if f.get("ret_pct") is not None]
    add("OKX", "MACRO acoes/indices/materias-primas (so papel)",
        {"papel": {"n": len(rs), "media_op": (sum(rs) / len(rs)) if rs else None}, "real": {}},
        [f"papel em % (nao R): {len(rs)} fechadas, media {round(sum(rs) / len(rs), 2) if rs else None}%"], ["papel"])
    add("Bybit", "H45 panico do mercado (custos Bybit)", {**bt_e("H45 (panico do mercado, custos Bybit)"),
                                                         "papel": amb.get("PAPEL|H45") or {}, "real": {}}, [], ["backtest", "papel"])
    add("Bybit", "FASES_LATERAL (so papel)", {"papel": amb.get("PAPEL|FASES_LATERAL") or {}, "real": {}},
        ["as 20 operacoes de papel sao de 1 so dia"], ["papel"])
    for k, x in sorted(ar.items()):
        d3, u = x["d365"], x["ultimos_45d"]
        regime_b = None
        for nome, g in (x.get("por_regime") or {}).items():
            if (g.get("n") or 0) >= 15 and g.get("avg_r") is not None and g.get("acaso_p95") is not None \
                    and g["avg_r"] > g["acaso_p95"] and (g.get("ic_inf_dia") or -1) > 0:
                regime_b = nome
        concentrado = (u.get("n") or 0) >= 10 and (u.get("dias") or 0) < 10
        e = {"arena_fora_liq": d3.get("fora_liq") if not concentrado else None, "arena_fora_n": d3.get("fora_n"),
             "arena_liq": d3.get("avg_r_liq"),
             "acima_acaso": d3.get("avg_r") is not None and d3.get("acaso_p95") is not None and d3["avg_r"] > d3["acaso_p95"],
             "regime_b": regime_b, "real": amb.get(f"BYBIT_REAL|{k}") or {}, "papel": {}}
        notas = []
        if concentrado:
            notas.append(f"concentrada: {u.get('n')} operacoes em {u.get('dias')} dias nos ultimos 45 dias")
        if x.get("clone_de"):
            notas.append(f"clone de {x['clone_de']}")
        if x.get("suspensa"):
            notas.append("suspensa pelo criterio mensal de custos")
        if x.get("desligada"):
            notas.append(f"desligada ({x['desligada']})")
        notas.append(f"arena {x.get('estado_arena')}; real_ok={x['real_ok']}")
        add("Bybit", k, e, notas, ["arena"] + (["real"] if e["real"].get("n") else []))
    return linhas


def _j_ok(x):
    return x or {}


# ---------------------------------------------------------------- walk-forward de melhorias (so filtros sobre operacoes)
def walk_forward(ops, regime, filtros, rng=None, reps=2000):
    """Cada filtro escolhe o subconjunto; escolhe-se no DESENHO (< 2024-07) e julga-se na VALIDACAO (2024-07..CORTE),
    contra a estrategia sem filtro no mesmo periodo. Diferenca por dia com bootstrap; Holm sobre os filtros."""
    from tools import estatistica_multipla as EM
    rng = rng or random.Random(5)
    antes = sorted({o["t_entrada"] // DAY for o in ops if o["t_entrada"] < CORTE})
    corte_wf = antes[len(antes) // 2] * DAY if antes else CORTE        # metade dos DIAS antes da reserva
    des = [o for o in ops if o["t_entrada"] < corte_wf]
    val = [o for o in ops if corte_wf <= o["t_entrada"] < CORTE]
    out, ps = {}, []
    for nome, f in filtros.items():
        dd, dv = [o for o in des if f(o, regime)], [o for o in val if f(o, regime)]
        md, mv = metricas(dd, rng, reps), metricas(dv, rng, reps)
        b_d, b_v = metricas(des, rng, reps), metricas(val, rng, reps)
        ganho_d = (md.get("media_dia") or 0) - (b_d.get("media_dia") or 0) if md.get("n") else None
        ganho_v = (mv.get("media_dia") or 0) - (b_v.get("media_dia") or 0) if mv.get("n") else None
        p = None
        if mv.get("n") and mv.get("t_dia") is not None:
            p = 1 - EM.phi(mv["t_dia"])            # H0: media por dia do filtrado <= 0
        ps.append(p if p is not None else 1.0)
        out[nome] = {"desenho": md, "validacao": mv, "ganho_desenho": _r(ganho_d), "ganho_validacao": _r(ganho_v),
                     "frequencia_validacao": _r(mv.get("dias", 0) / max(1, b_v.get("dias", 1)), 3), "p_unilateral": _r(p)}
    holm = EM.holm(ps) if ps else []
    out["_corte_walk_forward"] = _dt.datetime.fromtimestamp(corte_wf, _dt.timezone.utc).strftime("%Y-%m-%d")
    for (nome, x), (_, adj, _rej) in zip([kv for kv in out.items() if not kv[0].startswith("_")], holm):
        x["p_holm"] = _r(adj)
        x["passa"] = bool(adj is not None and adj < 0.05 and (x["ganho_desenho"] or 0) > 0 and (x["ganho_validacao"] or 0) > 0)
    return out


FILTROS = {
    "btc_acima_sma50": lambda o, reg: reg.get(o["t_entrada"] // DAY) is True,
    "btc_abaixo_sma50": lambda o, reg: reg.get(o["t_entrada"] // DAY) is False,
    "stop_largo_(>=12pct)": lambda o, reg: (o.get("stop_pct") or 0) >= 12,   # cortes fixos, escolhidos antes de ver
    "stop_curto_(<8pct)": lambda o, reg: 0 < (o.get("stop_pct") or 0) < 8,
    "dia_com_>=3_sinais": lambda o, reg: o.get("_n_dia", 1) >= 3,
    "dia_com_1_sinal": lambda o, reg: o.get("_n_dia", 1) == 1,
}


def marcar_dia(ops):
    nd = defaultdict(int)                             # sinais da MESMA estrategia no mesmo dia
    for o in ops:
        nd[(o["estrategia"], o["t_entrada"] // DAY)] += 1
    for o in ops:
        o["_n_dia"] = nd[(o["estrategia"], o["t_entrada"] // DAY)]
    return ops


# ---------------------------------------------------------------- correr
def _j(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def correr(pasta, bt_path, hist=None, reps=2000):
    from backtest.quant import dados as Q
    rng = random.Random(3)
    St, S, O = _j(os.path.join(pasta, "state.json")), _j(os.path.join(pasta, "scan.json")), _j(os.path.join(pasta, "okx.json"))
    F, L = _j(os.path.join(pasta, "forma.json")), _j(os.path.join(pasta, "longo.json"))
    CT = _j(os.path.join(pasta, "contabilidade_okx.json"))
    bt = _j(bt_path)
    regime = btc_regime(bt.get("btc_4h") or [])
    barras = {}
    if hist and os.path.isdir(hist):
        from engine import backtest as B
        barras, _ = B.load_all(hist, min_bars=100)
    ops_bt = [o for o in bt.get("operacoes") or []]
    mercado = {(o["ativo"], o["t_entrada"]) for o in ops_bt if o["estrategia"] == "H40 (panico do mercado)"}
    ops_bt += [dict(o, estrategia="H40 (panico isolado = todos menos mercado)") for o in ops_bt
               if o["estrategia"] == "H40 (todos os sinais)" and (o["ativo"], o["t_entrada"]) not in mercado]
    ops_bt = marcar_dia(ops_bt)
    res_bt = auditar_backtest(ops_bt, regime, barras, rng, reps)
    viv = Q.carregar(pasta)
    res_amb = auditar_ambientes([o for o in viv["operacoes"] if o["ambiente"] != "BACKTEST"], rng, reps)
    try:
        from engine.promo import REAL_OK
        real_ok = set(REAL_OK)
    except Exception:                                  # noqa: BLE001 (so para leitura)
        real_ok = set()
    arena = auditar_arena(F, L, S, St, real_ok)
    exe = execucao_okx(O)
    contab = [{k: o.get(k) for k in ("estrategia", "ativo", "r_bruto", "r_liquido", "custo_r", "deslize_stop_r", "completa")}
              for o in CT.get("operacoes") or []]
    wf = {}
    for est in ("H40 (panico do mercado)", "H40 (panico isolado = todos menos mercado)", "H46 (RSI<35)", "H46 (RSI<30)", "H45 (panico do mercado, custos Bybit)"):
        xs = [o for o in ops_bt if o["estrategia"] == est]
        for o in xs:
            o["stop_pct"] = stop_pct(barras.get(o.get("ativo")), o["t_entrada"])
        if xs:
            wf[est] = walk_forward(xs, regime, FILTROS, rng, reps)
    out = {"gerado": int(_dt.datetime.now(_dt.timezone.utc).timestamp()), "backtest": res_bt, "ambientes": res_amb,
            "arena_bybit": arena, "execucao_okx": exe, "contabilidade_okx": contab, "walk_forward": wf,
            "aviso": "So R. BACKTEST, ARENA, PAPEL, SOMBRA e REAL nunca somados. A reserva 2026-05-08..11-08 esta contaminada."}
    out["bloqueados_bybit"] = bloqueados_bybit(St.get("promo_lost"), barras)
    out["classificacao"] = tabela(out, O, St, S)
    out["resumo_classes"] = dict(_conta(x["classe"] for x in out["classificacao"]))
    return out


if __name__ == "__main__":
    a = sys.argv
    r = correr(a[1], a[2], a[3] if len(a) > 4 else None)
    json.dump(r, open(a[-1], "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("ok", a[-1])
