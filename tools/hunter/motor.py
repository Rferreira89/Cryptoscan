"""Motor de investigacao do Hunter: diagnostico por etapas, geometria, validacao emparelhada, evolucao e teste final.

Etapas (pre-registadas aqui, antes de correr):
  1. DIAGNOSTICO (so treino): para cada familia x parametros x timeframe x lado, retorno a prazo em ATR do tf
     do sinal (1, 2, 4, 8 velas), MFE/MAE e o custo de ida e volta em ATR. Diz se o problema esta na entrada
     (deriva <= 0), na geometria/objetivo (MFE >> deriva) ou nos custos (deriva > 0 mas < custo).
  2. GEOMETRIA (so treino): para as hipoteses com deriva liquida > 0 a algum prazo, escolhe a melhor saida da
     grelha (stop 1-3 ATR de 30m/1H/4H, objetivos 1-3R, parcial, trailing; tempo maximo dentro de 30 min-4 h no
     30m/1H e ate 24 h no 4H) pela media no treino.
  3. VALIDACAO: a hipotese com a geometria escolhida corre na validacao com controlo emparelhado e bootstrap por
     blocos (dias). Holm com o contador cumulativo de hipoteses do registo.
  4. EVOLUCAO (treino -> validacao): genomas = familia + parametros + timeframe + lado + filtro + saida; selecao no
     treino com orcamento fixo; os melhores (sem clones) vao a validacao e contam no Holm.
  5. TESTE FINAL: so as que passam a validacao (p de Holm < 0,05 e media > 0); cada regra uma unica vez (registo).
Veredictos: CANDIDATA (passou o teste final) | PROMISSORA (passou a validacao, falta teste ou falhou) |
EXPLORATORIA (melhores da validacao sem significancia: vao a papel para recolher dados novos) | REJEITADA.
Nada aqui envia ordens: o papel e simulado (tools/hunter/papel.py) e a passagem a real exige decisao do Rui.
"""
import json
import random
import time

import numpy as np

from tools.hunter import dados as DD, estat as ES, familias as FA, geometria as GE

HOLD = {"30m": (4, 8), "1H": (2, 4), "4H": (1, 3, 6)}
REFS = ("30m", "1H", "4H")
K_CTRL = 4
DIAS_MIN_VALIDACAO = 20     # dias UTC distintos com operacoes (bloco do bootstrap)
DIAS_MIN_TESTE = 10


def series(dados):
    """{tf: {base: S}} com arrays numpy e ATR14 do proprio tf."""
    out = {tf: {} for tf in DD.BAR}
    for b, d in dados.items():
        for tf in DD.BAR:
            v = DD.reamostrar(d["30m"], tf)
            if len(v) < 150:
                continue
            S = {k: np.array([x[k] for x in v], dtype=float) for k in "ohlcv"}
            S["t"] = np.array([x["t"] for x in v], dtype=np.int64)
            S["atr"] = np.array([np.nan if a is None else a for a in GE.atr_serie(v)], dtype=float)
            S["v_list"] = v
            out[tf][b] = S
    return out


def contexto(SS, dados, tf):
    """{base: M} alinhado por tempo: retornos do BTC, BTC acima da media de 50, mediana de mercado, funding."""
    btc = SS[tf].get("BTC")
    bt = {}
    if btc is not None:
        c = btc["c"]
        sma = FA.prev_mean(c, 50)
        for k in (1, 6, 24):
            r = FA.ret(c, k)
            bt[f"btc_ret_{k}"] = dict(zip(btc["t"].tolist(), r.tolist()))
        bt["btc_acima"] = dict(zip(btc["t"].tolist(), (c > sma).astype(float).tolist()))
    merc = {}
    for k in (6, 24):
        porT = {}
        for S in SS[tf].values():
            for t, r in zip(S["t"].tolist(), FA.ret(S["c"], k).tolist()):
                if r == r:
                    porT.setdefault(t, []).append(r)
        merc[f"mercado_ret_{k}"] = {t: float(np.median(v)) for t, v in porT.items() if len(v) >= 10}
    out = {}
    s = DD.BAR[tf]
    for b, S in SS[tf].items():
        M = {}
        for k, m in {**bt, **merc}.items():
            M[k] = np.array([m.get(t, np.nan) for t in S["t"].tolist()], dtype=float)
        f = dados[b].get("funding") or []
        if f:
            ft = np.array([x[0] for x in f])
            fr = np.array([x[1] for x in f])
            j = np.searchsorted(ft, S["t"] + s, side="right") - 1       # ultimo funding conhecido ao fecho
            M["funding"] = np.where(j >= 0, fr[np.clip(j, 0, None)], np.nan)
        out[b] = M
    return out


def atr_ref(SS, b, tf_sinal, i, tf_ref):
    """ATR do tf de referencia na ultima vela FECHADA ate ao fecho da vela i do sinal."""
    S = SS[tf_sinal][b]
    fecho = S["t"][i] + DD.BAR[tf_sinal]
    R = SS[tf_ref].get(b)
    if R is None:
        return None
    j = np.searchsorted(R["t"] + DD.BAR[tf_ref], fecho, side="right") - 1
    if j < 0:
        return None
    a = R["atr"][j]
    return None if a != a else float(a)


def sinais(SS, MM, tf, fam, p, lado):
    """{base: [i]} sem sobreposicao (uma posicao de cada vez por moeda: o motor salta enquanto ha posicao)."""
    fn = FA.FAMILIAS[fam][0]
    out = {}
    with np.errstate(all="ignore"):
        for b, S in SS[tf].items():
            L, Sh = fn(S, MM[tf][b], p)
            ii = L if lado == "LONG" else Sh
            ii = [int(i) for i in ii if i >= 120 and i < len(S["c"]) - 1]
            if ii:
                out[b] = ii
    return out


def deslize_tier(tier):
    """(17/11) custo de execucao por escalao de liquidez (por lado, % do preco): um sinal num contrato pouco
    liquido nao vale o mesmo que num liquido. A=0,03 B=0,08 C=0,20 (o papel usa tambem o spread observado)."""
    return {"A": 0.03, "B": 0.08, "C": 0.20}.get(tier, GE.DESLIZE)


def regime3(MM, tf, b, i):
    """Regime do BTC em 3 estados pelo retorno das ultimas 24 velas do tf: subida (> +3%), queda (< -3%), lateral."""
    r = MM[tf][b].get("btc_ret_24")
    if r is None or r[i] != r[i]:
        return "?"
    return "subida" if r[i] > 0.03 else "queda" if r[i] < -0.03 else "lateral"


def _regime(MM, tf, b, i):
    up = MM[tf][b].get("btc_acima")
    if up is None or up[i] != up[i]:
        return "?"
    return "btc_acima_media50" if up[i] > 0.5 else "btc_abaixo_media50"


def diagnostico(SS, MM, cortes, tf, fam, p, lado, sig=None):
    """Deriva a prazo em ATR (so treino) contra a deriva incondicional; custo de ida e volta em ATR."""
    sig = sig if sig is not None else sinais(SS, MM, tf, fam, p, lado)
    d = 1.0 if lado == "LONG" else -1.0
    fw = {h: [] for h in (1, 2, 4, 8)}
    mfe, mae, custo = [], [], []
    for b, ii in sig.items():
        S = SS[tf][b]
        for i in ii:
            if S["t"][i] >= cortes[0] or i + 9 >= len(S["c"]):
                continue
            a = S["atr"][i]
            if not a or a != a:
                continue
            e = S["o"][i + 1]
            for h in fw:
                fw[h].append(d * (S["c"][i + h] - e) / a)
            seg = slice(i + 1, i + 9)
            mfe.append(d * ((S["h"][seg].max() if d > 0 else S["l"][seg].min()) - e) / a)
            mae.append(-d * ((S["l"][seg].min() if d > 0 else S["h"][seg].max()) - e) / a)
            custo.append(e * 2 * (GE.COMISSAO + GE.DESLIZE) / 100 / a)
    n = len(custo)
    if not n:
        return {"n_treino": 0}
    out = {"n_treino": n, "custo_ida_volta_atr": round(float(np.mean(custo)), 3),
           "mfe8_atr": round(float(np.mean(mfe)), 3), "mae8_atr": round(float(np.mean(mae)), 3)}
    for h, xs in fw.items():
        out[f"deriva{h}_atr"] = round(float(np.mean(xs)), 4)
    melhor = max(out[f"deriva{h}_atr"] for h in fw)
    out["deriva_liquida_max_atr"] = round(melhor - out["custo_ida_volta_atr"], 4)
    out["onde_falha"] = ("entrada (sem deriva a favor)" if melhor <= 0 else
                         "custos (deriva menor que o custo)" if melhor < out["custo_ida_volta_atr"] else
                         "nenhum a priori: passa a geometria")
    return out


def operacoes(SS, MM, dados, tf, sig, lado, geo, ref, per, cortes, ctrl=False, rng=None, cenario=None, inverso=None,
              filtro=None, max_ops=None):
    """Simula as operacoes de um periodo; com ctrl=True junta o controlo emparelhado (media de K_CTRL entradas ao
    acaso da mesma moeda, mesmo periodo, mesmo lado e mesma geometria)."""
    ops = []
    pares = [(b, i) for b, ii in sig.items() for i in ii if ES.periodo(int(SS[tf][b]["t"][i]), cortes) == per]
    if max_ops and len(pares) > max_ops:
        pares = random.Random(5).sample(pares, max_ops)
        pares.sort(key=lambda x: (x[0], x[1]))
    livre = {}
    for b, i in pares:
        if i < livre.get(b, -1):
            continue
        S = SS[tf][b]
        if filtro and not filtro(MM, tf, b, i, dados):
            continue
        a = atr_ref(SS, b, tf, i, ref)
        fund = dados[b].get("funding") or []
        cen = cenario if cenario is not None else (float(np.median([x[1] for x in fund])) if fund else 0.0001)
        desl = deslize_tier((dados[b].get("info") or {}).get("tier"))
        r = GE.simular(S["v_list"], i, lado, a, geo, fund, cen, inverso=(inverso or {}).get(b), deslize=desl)
        if not r:
            continue
        livre[b] = i + r["velas"] + 1
        o = {"b": b, "t": int(S["t"][i]), "r": r["r"], "regime": _regime(MM, tf, b, i), "saida": r["saida"],
             "velas": r["velas"], "funding_fonte": r["funding_fonte"], "custos_r": r["custos_r"], "bruto_r": r["bruto_r"],
             "tier": (dados[b].get("info") or {}).get("tier"), "regime3": regime3(MM, tf, b, i),
             "minutos": r["velas"] * DD.BAR[tf] // 60, "stop_pct": 100 * geo["k"] * a / S["c"][i]}
        if ctrl:
            lo, hi = _limites(S["t"], per, cortes)
            xs = []
            for _ in range(K_CTRL * 3):
                if len(xs) >= K_CTRL:
                    break
                j = rng.randrange(max(120, lo), max(121, hi))
                if j >= len(S["c"]) - 1:
                    continue
                rr = GE.simular(S["v_list"], j, lado, atr_ref(SS, b, tf, j, ref), geo, fund, cen, deslize=desl)
                if rr:
                    xs.append(rr["r"])
            if not xs:
                continue
            o["ctrl"] = sum(xs) / len(xs)
            o["d"] = o["r"] - o["ctrl"]
        ops.append(o)
    return ops


def _limites(t, per, cortes):
    t = t.tolist()
    a = next((k for k, x in enumerate(t) if x >= cortes[0]), len(t))
    b = next((k for k, x in enumerate(t) if x >= cortes[1]), len(t))
    return {"treino": (0, a), "validacao": (a, b), "teste": (b, len(t))}[per]


def geometrias(tf):
    gs = []
    for ref in REFS:
        if DD.BAR[ref] < DD.BAR[tf] // 2:
            continue                       # stop de 30m num sinal de 4H nao faz sentido
        for g in GE.GEOMETRIAS_BASE:
            for h in HOLD[tf]:
                gs.append((ref, dict(g, hold=h)))
    return gs


def melhor_geometria(SS, MM, dados, tf, sig, lado, cortes, max_ops=1500, inverso=None):
    """Por etapas (nao a grelha cega): 1) stop k x ATR de cada tf de referencia e tempo maximo, com alvo 2R;
    2) com o melhor stop: alvos 1/1,5/2/3R, parcial, trailing e saida por inversao do sinal."""
    def media(ref, g, inv=None):
        ops = operacoes(SS, MM, dados, tf, sig, lado, g, ref, "treino", cortes, max_ops=max_ops, inverso=inv)
        return (sum(o["r"] for o in ops) / len(ops), len(ops)) if len(ops) >= 30 else (None, len(ops))
    best = None
    for ref in REFS:
        if DD.BAR[ref] < DD.BAR[tf] // 2:
            continue
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            for h in HOLD[tf]:
                g = {"tipo": "fixa", "k": k, "tp": 2.0, "hold": h}
                m, n = media(ref, g)
                if m is not None and (best is None or m > best[0]):
                    best = (m, ref, g, n)
    if not best:
        return None
    _, ref, g0, _ = best
    variantes = [dict(g0, tp=tp) for tp in (1.0, 1.5, 3.0)] + [dict(g0, tipo="parcial"),
                                                                dict(g0, tipo="trailing", tp=None)]
    for g in variantes:
        m, n = media(ref, g)
        if m is not None and m > best[0]:
            best = (m, ref, g, n)
    if inverso:
        g = dict(best[2], inversao=True)
        m, n = media(ref, g, inverso)
        if m is not None and m > best[0]:
            best = (m, ref, g, n)
    return best


# --------------------------------------------- filtros para a evolucao -------------------------------------------
def _f_btc_acima(MM, tf, b, i, dados):
    u = MM[tf][b].get("btc_acima")
    return u is not None and u[i] > 0.5


def _f_btc_abaixo(MM, tf, b, i, dados):
    u = MM[tf][b].get("btc_acima")
    return u is not None and u[i] == u[i] and u[i] < 0.5


def _f_tier_a(MM, tf, b, i, dados):
    return dados[b]["info"].get("tier") == "A"


def _f_cripto(MM, tf, b, i, dados):
    return dados[b]["info"].get("classe") == "crypto"


def _f_nao_cripto(MM, tf, b, i, dados):
    return dados[b]["info"].get("classe") != "crypto"


FILTROS = {None: None, "btc_acima": _f_btc_acima, "btc_abaixo": _f_btc_abaixo, "tier_A": _f_tier_a,
           "cripto": _f_cripto, "nao_cripto": _f_nao_cripto}


def inverso_de(SS, MM, h):
    if not h["saida"].get("inversao"):
        return None
    op = sinais(SS, MM, h["tf"], h["familia"], h["parametros"], "SHORT" if h["lado"] == "LONG" else "LONG")
    return {b: set(ii) for b, ii in op.items()}


def avaliar_validacao(SS, MM, dados, h, cortes, rng):
    sig = sinais(SS, MM, h["tf"], h["familia"], h["parametros"], h["lado"])
    ops = operacoes(SS, MM, dados, h["tf"], sig, h["lado"], h["saida"], h["stop_ref"], "validacao", cortes,
                    ctrl=True, rng=rng, filtro=FILTROS[h.get("filtro")], inverso=inverso_de(SS, MM, h))
    return ops, ES.resumo(ops, "validacao")


def evolucao(SS, MM, dados, cortes, orcamento=120, pop=24, seed=3, log=print):
    """Pesquisa evolutiva no TREINO: mutacao de familia/parametros/tf/lado/filtro/saida; aptidao = media - erro
    padrao por dias (penaliza amostras pequenas e operacoes concentradas no mesmo dia)."""
    rng = random.Random(seed)
    fams = list(FA.FAMILIAS)

    def novo():
        f = rng.choice(fams)
        tf = rng.choice(list(HOLD))
        ref, g = rng.choice(geometrias(tf))
        return {"familia": f, "parametros": rng.choice(FA.FAMILIAS[f][1]), "tf": tf, "lado": rng.choice(("LONG", "SHORT")),
                "filtro": rng.choice(list(FILTROS)), "stop_ref": ref, "saida": g}

    def mutar(h):
        h = json.loads(json.dumps(h))
        q = rng.choice(("parametros", "filtro", "saida", "tf", "lado"))
        if q == "parametros":
            h["parametros"] = rng.choice(FA.FAMILIAS[h["familia"]][1])
        elif q == "filtro":
            h["filtro"] = rng.choice(list(FILTROS))
        elif q == "lado":
            h["lado"] = "SHORT" if h["lado"] == "LONG" else "LONG"
        else:
            if q == "tf":
                h["tf"] = rng.choice(list(HOLD))
            h["stop_ref"], h["saida"] = rng.choice(geometrias(h["tf"]))
        return h

    cache = {}

    def apt(h):
        k = ES.regra_id(h)
        if k in cache:
            return cache[k]
        sig = sinais(SS, MM, h["tf"], h["familia"], h["parametros"], h["lado"])
        ops = operacoes(SS, MM, dados, h["tf"], sig, h["lado"], h["saida"], h["stop_ref"], "treino", cortes,
                        filtro=FILTROS[h.get("filtro")], max_ops=3000)
        if len(ops) < 40:
            cache[k] = (-9.0, len(ops), ops)
            return cache[k]
        porD = {}
        for o in ops:
            porD.setdefault(o["t"] // 86400, []).append(o["r"])
        ms = [sum(v) / len(v) for v in porD.values()]
        m = sum(o["r"] for o in ops) / len(ops)
        se = (np.std(ms) / np.sqrt(len(ms))) if len(ms) > 1 else 9.0
        cache[k] = (m - se, len(ops), ops)
        return cache[k]

    P = [novo() for _ in range(pop)]
    gastos = 0
    while gastos < orcamento:
        P.sort(key=lambda h: -apt(h)[0])
        gastos = len(cache)
        elite = P[:pop // 3]
        filhos = []
        for _ in range(pop - len(elite)):
            a = rng.choice(elite)
            filhos.append(mutar(a) if rng.random() < 0.8 else novo())
        P = elite + filhos
        log(f"evolucao: {gastos} avaliadas, melhor aptidao {apt(P[0])[0]:+.3f} ({P[0]['familia']} {P[0]['tf']} {P[0]['lado']})")
    P.sort(key=lambda h: -apt(h)[0])
    # eliminar clones: Jaccard das (moeda, dia) das operacoes > 0,6
    finais = []
    for h in P:
        a = apt(h)
        if a[0] <= 0:
            continue
        chaves = {(o["b"], o["t"] // 86400) for o in a[2]}
        clone = False
        for f in finais:
            cf = {(o["b"], o["t"] // 86400) for o in apt(f)[2]}
            if chaves and len(chaves & cf) / len(chaves | cf) > 0.6:
                clone = True
                break
        if not clone:
            finais.append(h)
    todos = sorted(cache.items(), key=lambda kv: -kv[1][0])
    return finais[:12], len(cache), [(k, round(v[0], 4), v[1]) for k, v in todos[:20]]


def correr(dados, registo, log=print, orcamento_evolucao=120, max_validacao=60):
    t0 = time.time()
    SS = series(dados)
    MM = {tf: contexto(SS, dados, tf) for tf in DD.BAR}
    ts = sorted(int(t) for S in SS["30m"].values() for t in (S["t"][0], S["t"][-1]))
    cortes = ES.cortes(ts[0], ts[-1])
    rng = random.Random(17)
    out = {"cortes": {"treino_ate": cortes[0], "validacao_ate": cortes[1], "teste_ate": ts[-1]},
           "moedas_por_tf": {tf: len(SS[tf]) for tf in SS}, "diagnostico": {}, "hipoteses": {}}
    # 1. diagnostico + 2. geometria
    cand = []
    for fam, (fn, grelha) in FA.FAMILIAS.items():
        for p in grelha:
            for tf in HOLD:
                for lado in ("LONG", "SHORT"):
                    sig = sinais(SS, MM, tf, fam, p, lado)
                    dg = diagnostico(SS, MM, cortes, tf, fam, p, lado, sig)
                    nome = f"{fam} {json.dumps(p, sort_keys=True)} {tf} {lado}"
                    out["diagnostico"][nome] = dg
                    if dg.get("n_treino", 0) >= 60 and dg.get("deriva_liquida_max_atr", -1) > 0:
                        cand.append((dg["deriva_liquida_max_atr"], fam, p, tf, lado, sig))
    log(f"diagnostico: {len(out['diagnostico'])} hipoteses, {len(cand)} com deriva liquida > 0 no treino "
        f"({time.time() - t0:.0f}s)")
    cand.sort(key=lambda x: -x[0])
    hip = []
    for _, fam, p, tf, lado, sig in cand[:max_validacao]:
        oposto = sinais(SS, MM, tf, fam, p, "SHORT" if lado == "LONG" else "LONG")
        inv = {b: set(ii) for b, ii in oposto.items()}
        mg = melhor_geometria(SS, MM, dados, tf, sig, lado, cortes, inverso=inv)
        if not mg or mg[0] <= 0:
            continue
        hip.append({"familia": fam, "grupo": FA.GRUPO[fam], "parametros": p, "tf": tf, "lado": lado, "filtro": None,
                    "stop_ref": mg[1], "saida": mg[2], "r_treino": round(mg[0], 4), "n_treino": mg[3], "origem": "grelha"})
    log(f"geometria: {len(hip)} hipoteses com media > 0 no treino ({time.time() - t0:.0f}s)")
    # 4. evolucao
    evo, gastos, top = evolucao(SS, MM, dados, cortes, orcamento=orcamento_evolucao, log=log)
    for h in evo:
        hip.append({**h, "grupo": FA.GRUPO[h["familia"]], "origem": "evolucao"})
    out["evolucao"] = {"genomas_avaliados": gastos, "melhores_no_treino": top}
    # 3. validacao com Holm cumulativo
    agora = int(time.time())
    ja = registo.recentes(agora)
    novos = []
    for h in hip:
        rid = ES.regra_id({k: h[k] for k in ("familia", "parametros", "tf", "lado", "filtro", "stop_ref", "saida")})
        if rid in ja or rid in {x[0] for x in novos}:
            continue
        novos.append((rid, h))
    out["ja_avaliadas_nao_repetidas"] = len(hip) - len(novos)
    m_total = registo.nova_ronda(len(novos), f"hunter {time.strftime('%Y-%m-%d')}")
    res = {}
    for rid, h in novos:
        registo.marcar_avaliada(rid, agora)
        ops, rv = avaliar_validacao(SS, MM, dados, h, cortes, rng)
        res[rid] = {**h, "id": rid, "validacao": rv, "_ops": ops}
    ps = {k: v["validacao"].get("p_vantagem", 1.0) if v["validacao"].get("n", 0) >= 30 else 1.0 for k, v in res.items()}
    ph = ES.holm(ps, m_total)
    for k, v in res.items():
        v["p_holm_validacao"] = ph[k]
        rv = v["validacao"]
        # (17/11, revisao) dezenas de operacoes no mesmo dia sao UM acontecimento: exige dias distintos
        v["passa_validacao"] = bool(rv.get("n", 0) >= 30 and rv.get("dias_com_operacoes", 0) >= DIAS_MIN_VALIDACAO
                                    and ph[k] < 0.05 and (rv.get("r_medio") or 0) > 0)
    # 5. teste final (uma vez por regra)
    for k, v in res.items():
        if not v["passa_validacao"]:
            continue
        if not registo.pode_testar(k):
            v["teste"] = {"nota": "teste final ja usado por esta regra: nao reavaliado"}
            continue
        sig = sinais(SS, MM, v["tf"], v["familia"], v["parametros"], v["lado"])
        ops = operacoes(SS, MM, dados, v["tf"], sig, v["lado"], v["saida"], v["stop_ref"], "teste", cortes, ctrl=True,
                        rng=rng, filtro=FILTROS[v.get("filtro")], inverso=inverso_de(SS, MM, v))
        rt = ES.resumo(ops, "teste")
        v["teste"] = rt
        registo.marcar_teste(k, {q: rt.get(q) for q in ("n", "r_medio", "p_vantagem")})
    # veredictos e papel
    for k, v in res.items():
        rt = v.get("teste") or {}
        if (v["passa_validacao"] and rt.get("n", 0) >= 30 and rt.get("dias_com_operacoes", 0) >= DIAS_MIN_TESTE
                and (rt.get("r_medio") or 0) > 0 and rt.get("p_r_positivo", 1) < 0.05 and rt.get("p_vantagem", 1) < 0.05):
            v["veredicto"] = "CANDIDATA"
        elif v["passa_validacao"]:
            v["veredicto"] = "PROMISSORA"
        else:
            v["veredicto"] = "REJEITADA"
    expl = sorted((v for v in res.values() if v["veredicto"] == "REJEITADA" and v["validacao"].get("n", 0) >= 30
                   and (v["validacao"].get("r_medio") or 0) > 0),
                  key=lambda v: -(v["validacao"].get("vantagem_sobre_acaso") or -9))
    for v in expl[:8]:
        v["veredicto"] = "EXPLORATORIA"
    for v in res.values():
        ops = v.pop("_ops", None) or []
        if v["veredicto"] != "REJEITADA":
            v["_ops_validacao"] = [[o["t"], round(o["r"], 3)] for o in sorted(ops, key=lambda o: o["t"])]
    out["hipoteses"] = res
    out["papel"] = [{k: v[k] for k in ("id", "familia", "parametros", "tf", "lado", "filtro", "stop_ref", "saida", "veredicto")}
                    for v in res.values() if v["veredicto"] in ("CANDIDATA", "PROMISSORA", "EXPLORATORIA")]
    out["segundos"] = round(time.time() - t0)
    out["_ctx"] = (SS, MM, cortes)
    return out
