"""H13 (pre-registado a 22/10, ANTES de correr; pedido do Rui: "um indice de mercado
de alta ou baixa" em vez de so detetar a queda).

Pergunta: o indice do mercado (engine/indice.py, 0-100) deixa os lutadores de cada
lado entrar MAIS CEDO do que a regra de fase, sem perder dinheiro?
  H13a  Xenia (SHORT_X30) nos dias com indice <= 35 em que a regra ainda NAO diz queda
  H13b  Teodoro (TURTLE_FORTES) nos dias com indice >= 65 em que a regra ainda NAO diz subida
Indice de cada dia: so com dados fechados ate a vespera (BTC diario + amplitude das 25 moedas).
Operacoes: as dos estudos H10 (SHORT_X30) e H11 (TURTLE_FORTES), mesmos custos e liquidez.
Criterio (o do H10, fixado antes): nos DOIS periodos, R medio por operacao >= +0,10,
R medio por dia > 0 e >= 15 dias distintos. Contador global de hipoteses: +2.
"""
import json, sys, gzip, glob, os
sys.path.insert(0, "/home/claude/cryptoscan")
from engine import backtest as B, indice
DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
HIST = "/tmp/claude-0/hist"


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


def res(ts):
    if not ts:
        return {"n": 0, "dias": 0}
    dd = {}
    for t in ts:
        dd.setdefault(t["t"] // DAY, []).append(t["r"])
    md = [sum(v) / len(v) for v in dd.values()]
    return {"n": len(ts), "r": round(sum(t["r"] for t in ts) / len(ts), 3), "dias": len(dd), "r_dia": round(sum(md) / len(md), 3)}


if __name__ == "__main__":
    vol = {}
    for p in glob.glob(f"{HIST}/*.csv.gz"):
        a = os.path.basename(p).split(".")[0]; c = load(p); vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
    moedas = sorted(vol, key=lambda a: -vol[a])[:25]
    dd = {a: B.daily(load(f"{HIST}/{a}.csv.gz")) for a in set(moedas) | {"BTC"}}
    idx = {}
    btc = dd["BTC"]
    pos = {a: 0 for a in dd}
    for k in range(200, len(btc)):
        dia = btc[k]["t"] // DAY
        sub = {}
        for a in moedas:
            d = dd[a]
            j = pos[a]
            while j < len(d) and d[j]["t"] // DAY <= dia:
                j += 1
            pos[a] = j
            if j >= 50:
                sub[a] = d[j - 50:j]
        r = indice.calcular(btc[:k + 1], sub)
        if r:
            idx[dia] = (r["valor"], r["fase_regra"])
    h10 = json.load(open("/tmp/claude-0/estudo/h10_trades.json"))
    h11 = json.load(open("/tmp/claude-0/estudo/h11_trades.json"))
    testes = {"H13a SHORT_X30 indice<=35 sem queda": ([t for t in h10 if t["k"] == "SHORT_X30"], lambda v, f: v <= 35 and f != "queda"),
              "H13b TURTLE_FORTES indice>=65 sem subida": ([t for t in h11 if t["k"] == "TURTLE_FORTES"], lambda v, f: v >= 65 and f != "subida")}
    aprov = []
    for nome, (ts, cond) in testes.items():
        sel = [t for t in ts if (t["t"] // DAY - 1) in idx and cond(*idx[t["t"] // DAY - 1])]
        ra = res([t for t in sel if A0 <= t["t"] < A1]); rb = res([t for t in sel if B0 <= t["t"] < B1])
        ok = all(x["n"] and x["r"] >= 0.10 and x["r_dia"] > 0 and x["dias"] >= 15 for x in (ra, rb))
        if ok:
            aprov.append(nome)
        print(f"{nome}: A {ra} | B {rb}{'  <== PASSA' if ok else ''}")
    dist = {}
    for v, f in idx.values():
        dist.setdefault(f, []).append(v)
    print("\nindice medio por fase da regra:", {f: round(sum(v) / len(v)) for f, v in dist.items()})
    print("APROVADAS:", aprov)
