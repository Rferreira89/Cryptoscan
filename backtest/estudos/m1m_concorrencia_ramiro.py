"""Uso do capital do Ramiro: quantas operacoes em simultaneo (1, 2, 3) com as operacoes do
backtest (SHORT_TURTLE, fase lateral, 25 moedas, custos e juro incluidos). Mede R total,
R por mes, queda maxima em R e retorno por ano com o risco por operacao (composto)."""
import json, random
DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
T = [t for t in json.load(open("/tmp/claude-0/estudo/sr_trades.json")) if t["k"] == "SHORT_TURTLE" and t["fase"] == "lateral"]
T.sort(key=lambda t: t["t"])


def sim(trades, K):
    abertas, tom, eqR, pk, dd = [], [], 0, 0, 0
    for t in trades:
        abertas = [x for x in abertas if x["t"] + x["dias"] * DAY > t["t"]]
        if len(abertas) >= K or any(x["a"] == t["a"] for x in abertas):
            continue
        abertas.append(t); tom.append(t)
    for t in sorted(tom, key=lambda x: x["t"] + x["dias"] * DAY):
        eqR += t["r"]; pk = max(pk, eqR); dd = max(dd, pk - eqR)
    return tom, eqR, dd


def cresc(tom, risco, meses):
    eq = 1.0
    for t in sorted(tom, key=lambda x: x["t"] + x["dias"] * DAY):
        eq *= 1 + risco * t["r"]
    return (eq ** (12 / meses) - 1) * 100


out = {}
for nome, t0, t1 in (("A 2021-24", A0, A1), ("B 2024-26", B0, B1)):
    s = [t for t in T if t0 <= t["t"] < t1]
    dias_lat = len({t["t"] // DAY for t in s})
    meses = (t1 - t0) / DAY / 30.4
    for K in (1, 2, 3):
        tom, R, dd = sim(s, K)
        out[(nome, K)] = (len(tom), R, dd)
        print(f"{nome} K={K}: {len(tom)} op ({len(tom)/meses:.1f}/mês), {R:+.1f}R, {R/max(1,len(tom)):+.3f}R/op, queda máx {dd:.1f}R, "
              f"ano a 0,25%: {cresc(tom, .0025, meses):+.1f}%, a 0,5%: {cresc(tom, .005, meses):+.1f}%")
json.dump({f"{k[0]}|{k[1]}": v for k, v in out.items()}, open("/tmp/claude-0/estudo/concorrencia.json", "w"))
