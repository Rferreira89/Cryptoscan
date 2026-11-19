"""C4 (20/11): reversao de curto prazo em indices, metais e acoes, LONG e SHORT por regime.
Regras, saidas, custos, regimes e criterios FIXADOS ANTES em backtest/pre_registo_c4_reversao.md (nao mudar aqui).
Uso: python3 backtest/estudos/c4_reversao.py <pasta_indices_diario> [saida.json]"""
import datetime
import json
import math
import os
import random
import sys

CUSTO_LADO, FUND_DIA, K_STOP = 0.001, 0.0003, 2.0
MAX_DIAS = {"V3": 5, "RSI2": 10}
CLASSES = {"indices": {"SP500": "5EGSPC", "NASDAQ100": "5ENDX"},
           "metais": {"OURO": "GCF", "PRATA": "SIF"},
           "acoes": {s: s for s in "AAPL AMD AMZN ADBE AMAT AVGO GOOGL IBM INTC KO LLY META MRVL MSFT MSTR MU NFLX NVDA "
                                    "ORCL QCOM TSLA TSM".split()}}
REGRAS, LADOS, REGIMES = ("V3", "RSI2"), ("LONG", "SHORT"), ("subida", "lateral", "descida")
N_ACASO, SEMENTE = 2000, 20261120


def carregar(p):
    with open(p, encoding="utf-8") as f:
        r = json.load(f)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(r["timestamp"]):
        v = [q[k][i] for k in ("open", "high", "low", "close")]
        if all(x is not None and x > 0 for x in v):
            out.append((t, *v))
    return out


def indicadores(d):
    n = len(d)
    o, h, l, c = ([x[k] for x in d] for k in (1, 2, 3, 4))
    atr, rsi, sma5, sma200 = [None] * n, [None] * n, [None] * n, [None] * n
    a = None
    for i in range(1, n):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        a = tr if a is None else (a * 13 + tr) / 14
        if i >= 14:
            atr[i] = a
    g = p = None
    for i in range(1, n):
        ch = c[i] - c[i - 1]
        up, dn = max(ch, 0), max(-ch, 0)
        g, p = (up, dn) if g is None else ((g + up) / 2, (p + dn) / 2)
        if i >= 2:
            rsi[i] = 100.0 if p == 0 else 100 - 100 / (1 + g / p)
    s = 0.0
    for i in range(n):
        s += c[i]
        if i >= 200:
            s -= c[i - 200]
        if i >= 199:
            sma200[i] = s / 200
        if i >= 4:
            sma5[i] = sum(c[i - 4:i + 1]) / 5
    reg = [None] * n
    for i in range(219, n):
        sub = sma200[i] > sma200[i - 20]
        reg[i] = "subida" if c[i] > sma200[i] and sub else "descida" if c[i] < sma200[i] and not sub else "lateral"
    return {"o": o, "h": h, "l": l, "c": c, "atr": atr, "rsi": rsi, "sma5": sma5, "reg": reg, "t": [x[0] for x in d]}


def sinal(I, t, regra, lado):
    c = I["c"]
    if regra == "V3":
        if t < 3:
            return False
        baixa = all(c[t - k] < c[t - k - 1] for k in range(3))
        alta = all(c[t - k] > c[t - k - 1] for k in range(3))
        return baixa if lado == "LONG" else alta
    r = I["rsi"][t]
    return r is not None and (r < 10 if lado == "LONG" else r > 90)


def operacao(I, t, regra, lado, custo_mult=1.0):
    """Operacao a partir do sinal em t. Devolve (R liquido, dia de saida) ou None."""
    n = len(I["c"])
    if t + 1 >= n or I["atr"][t] is None or I["reg"][t] is None:
        return None
    s = 1 if lado == "LONG" else -1
    e = I["o"][t + 1]
    risco = K_STOP * I["atr"][t]
    stop = e - s * risco
    saida, j = None, t + 1
    while j < n:
        o, h, l, c = I["o"][j], I["h"][j], I["l"][j], I["c"][j]
        if j > t + 1 and (o - stop) * s <= 0:
            saida = o
        elif (l if s == 1 else h) * s <= stop * s:
            saida = stop
        elif regra == "V3" and (c - I["c"][j - 1]) * s > 0:
            saida = c
        elif regra == "RSI2" and I["sma5"][j] is not None and (c - I["sma5"][j]) * s > 0:
            saida = c
        elif j - t >= MAX_DIAS[regra]:
            saida = c
        if saida is not None:
            break
        j += 1
    if saida is None:
        return None                                   # ainda aberta no fim dos dados
    custo = (CUSTO_LADO * (e + saida) + FUND_DIA * (j - t) * e) * custo_mult
    return (s * (saida - e) - custo) / risco, j


def operacoes(I, regra, lado):
    out, t, n = [], 0, len(I["c"])
    while t < n:
        if sinal(I, t, regra, lado):
            r = operacao(I, t, regra, lado)
            if r:
                r2 = operacao(I, t, regra, lado, 1.25)[0]
                out.append({"t": I["t"][t], "reg": I["reg"][t], "r": r[0], "r_custo125": r2})
                t = r[1]
                continue
        t += 1
    return out


def media(x):
    return sum(x) / len(x) if x else None


def holm(ps):
    ordem = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, m, ac = [1.0] * len(ps), len(ps), 0.0
    for k, i in enumerate(ordem):
        ac = max(ac, min(1.0, (m - k) * ps[i]))
        adj[i] = ac
    return adj


def correr(pasta):
    rnd = random.Random(SEMENTE)
    dados = {}
    for cl, ativos in CLASSES.items():
        for nome, f in ativos.items():
            p = os.path.join(pasta, f"yahoo_{f}.json")
            try:
                d = carregar(p)
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                d = []
            if len(d) > 400:
                dados[(cl, nome)] = indicadores(d)
    ts = [t for I in dados.values() for t in I["t"]]
    t0, t1 = min(ts), max(ts)
    cortes = (t0 + 0.5 * (t1 - t0), t0 + 0.75 * (t1 - t0))
    periodo = lambda t: 0 if t < cortes[0] else 1 if t < cortes[1] else 2  # noqa: E731
    celulas = []
    for cl in CLASSES:
        ativos = [k for k in dados if k[0] == cl]
        for regra in REGRAS:
            for lado in LADOS:
                ops_ativo = {k[1]: operacoes(dados[k], regra, lado) for k in ativos}
                # resultado de uma entrada em cada dia (para o acaso), por ativo
                todos = {}
                for k in ativos:
                    I = dados[k]
                    todos[k[1]] = [(i, operacao(I, i, regra, lado)) for i in range(len(I["c"]))]
                for regime in REGIMES:
                    ops = [dict(o, ativo=a) for a, lst in ops_ativo.items() for o in lst if o["reg"] == regime]
                    rs = [o["r"] for o in ops]
                    cel = {"classe": cl, "regra": regra, "lado": lado, "regime": regime, "n": len(ops),
                           "ativos_com_dados": len(ativos)}
                    if rs:
                        cel["r_medio"] = round(media(rs), 4)
                        cel["acerto_pct"] = round(100 * sum(r > 0 for r in rs) / len(rs), 1)
                        per = [[o["r"] for o in ops if periodo(o["t"]) == k] for k in range(3)]
                        cel["periodos"] = [{"n": len(x), "r_medio": round(media(x), 4) if x else None} for x in per]
                        cel["r_custo125"] = round(media([o["r_custo125"] for o in ops]), 4)
                        por_ativo = {}
                        for o in ops:
                            por_ativo.setdefault(o["ativo"], []).append(o["r"])
                        cel["por_ativo"] = {a: {"n": len(v), "soma_r": round(sum(v), 3)} for a, v in sorted(por_ativo.items())}
                        melhor = max(por_ativo, key=lambda a: sum(por_ativo[a]))
                        sem = [o["r"] for o in ops if o["ativo"] != melhor]
                        cel["sem_melhor_ativo"] = {"ativo": melhor, "r_medio": round(media(sem), 4) if sem else None}
                        # acaso: mesmo numero de entradas por ativo, dias do mesmo regime, mesmas saidas
                        pools = {}
                        for a, lst in por_ativo.items():
                            I = dados[(cl, a)]
                            pools[a] = ([r[0] for i, r in todos[a] if r and I["reg"][i] == regime], len(lst))
                        medias, ok = [], all(len(p) >= q for p, q in pools.values())
                        if ok:
                            for _ in range(N_ACASO):
                                amostra = []
                                for p, q in pools.values():
                                    amostra += rnd.sample(p, q)
                                medias.append(media(amostra))
                            cel["acaso_mediana"] = round(sorted(medias)[len(medias) // 2], 4)
                            cel["acaso_p95"] = round(sorted(medias)[int(0.95 * len(medias))], 4)
                            cel["p"] = round((1 + sum(m >= cel["r_medio"] for m in medias)) / (N_ACASO + 1), 5)
                    cel.setdefault("p", 1.0)
                    celulas.append(cel)
    for c, a in zip(celulas, holm([c["p"] for c in celulas])):
        c["p_holm"] = round(a, 5)
        per = c.get("periodos") or []
        falhas = []
        if c["n"] < 30:
            falhas.append("menos de 30 operacoes")
        if not per or any(x["n"] < 5 or (x["r_medio"] or 0) <= 0 for x in per):
            falhas.append("R medio <= 0 ou < 5 op. em algum periodo")
        if c["p_holm"] >= 0.05:
            falhas.append("nao bate o acaso (Holm)")
        if (c.get("r_custo125") or 0) <= 0:
            falhas.append("custos +25% <= 0")
        if len(c.get("por_ativo") or {}) >= 2 and ((c.get("sem_melhor_ativo") or {}).get("r_medio") or 0) <= 0:
            falhas.append("sem o melhor ativo <= 0")
        c["aprovada"] = not falhas
        c["falhas"] = falhas
    dia = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    return {"pre_registo": "backtest/pre_registo_c4_reversao.md", "testes": len(celulas),
            "de": dia(t0), "ate": dia(t1), "cortes": [dia(x) for x in cortes],
            "ativos": sorted(f"{k[0]}:{k[1]}" for k in dados), "celulas": celulas}


if __name__ == "__main__":
    res = correr(sys.argv[1])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"{res['testes']} testes, {res['de']} -> {res['ate']}, cortes {res['cortes']}, {len(res['ativos'])} ativos")
    for c in res["celulas"]:
        per = " ".join(f"{x['r_medio']:+.3f}({x['n']})" if x["r_medio"] is not None else f"—({x['n']})" for x in c.get("periodos") or [])
        print(f"{c['classe']:7} {c['regra']:4} {c['lado']:5} {c['regime']:7} n {c['n']:4} R {c.get('r_medio', 0):+.3f} "
              f"acaso p95 {c.get('acaso_p95', float('nan')):+.3f} p {c['p']:.4f} holm {c['p_holm']:.3f} | {per} | "
              f"{'APROVADA' if c['aprovada'] else '; '.join(c['falhas'])}")
