import json, collections
DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
T = json.load(open("/tmp/claude-0/estudo/sr_trades.json"))


def m(ts):
    if not ts:
        return {"n": 0}
    rs = [t["r"] for t in ts]
    w = [r for r in rs if r > 0]; l = [r for r in rs if r <= 0]
    dd = collections.defaultdict(list)
    for t in ts:
        dd[t["t"] // DAY].append(t["r"])
    md = [sum(v) / len(v) for v in dd.values()]
    pf = sum(w) / -sum(l) if l and sum(l) < 0 else None
    # curva em R por ordem cronologica
    eq = pk = mdd = 0
    for t in sorted(ts, key=lambda x: x["t"]):
        eq += t["r"]; pk = max(pk, eq); mdd = max(mdd, pk - eq)
    return {"n": len(ts), "acerto": round(100 * len(w) / len(rs)), "pf": None if pf is None else round(pf, 2),
            "r": round(sum(rs) / len(rs), 3), "r_dia": round(sum(md) / len(md), 3), "dias": len(dd),
            "ganho_med": round(sum(w) / len(w), 2) if w else None, "perda_med": round(sum(l) / len(l), 2) if l else None,
            "dias_aberta": round(sum(t["dias"] for t in ts) / len(ts), 1), "total_r": round(sum(rs), 1), "dd_r": round(mdd, 1)}


nomes = list(dict.fromkeys(t["k"] for t in T))
out = {}
for k in nomes:
    out[k] = {}
    for f in ("subida", "lateral", "queda", "todas"):
        sel = [t for t in T if t["k"] == k and (f == "todas" or t["fase"] == f)]
        a = m([t for t in sel if A0 <= t["t"] < A1]); b = m([t for t in sel if B0 <= t["t"] < B1])
        ok = f != "todas" and all(x.get("n") and x["r"] >= 0.10 and x["r_dia"] > 0 and x["dias"] >= 15 for x in (a, b))
        out[k][f] = {"A": a, "B": b, "apta": ok}
json.dump(out, open("/tmp/claude-0/estudo/sr_metricas.json", "w"), ensure_ascii=False, indent=1)
for k in nomes:
    print(f"\n== {k}")
    for f, v in out[k].items():
        print(f"  {f:8s} A {v['A']}\n           B {v['B']}{'   <== APTA' if v['apta'] else ''}")
# por moeda (so para SHORT_TURTLE lateral, quantas moedas ganham)
st = [t for t in T if t["k"] == "SHORT_TURTLE" and t["fase"] == "lateral"]
pm = collections.defaultdict(list)
for t in st:
    pm[t["a"]].append(t["r"])
print("\nSHORT_TURTLE lateral por moeda: positivas", sum(1 for v in pm.values() if sum(v) > 0), "de", len(pm))
print(sorted(((round(sum(v) / len(v), 2), a, len(v)) for a, v in pm.items()), reverse=True))
