import json, sys, random, importlib.util
from collections import defaultdict
G, dias = sys.argv[1], sys.argv[2]
sp = importlib.util.spec_from_file_location("aud", G + "/qb/aud.py"); A = importlib.util.module_from_spec(sp); sp.loader.exec_module(A)
from tools import arena_ringue as AR
V = {v: json.load(open(f"{G}/as_{dias}_{v}.json")) for v in ("antiga", "margem", "margem_juros")}
mg = set(V["antiga"]["margem"])
out = {"dias": int(dias), "moedas_no_combate": len(V["antiga"]["moedas"]), "moedas_com_margem_no_combate": len(set(V["antiga"]["moedas"]) & mg),
       "lutadores": {}, "operacoes_sem_margem_na_arena_antiga": {}}
def ops_de(v, k):
    xs = [o for o in V[v]["operacoes"] if o["k"] == k]
    if v == "margem_juros":
        xs = [dict(o, r=o["r"] - AR.juros_short_r({"t": o["t"], "t_fim": o["t_fim"], "geo": {"stop": o["stop"]}}, 0.03)) for o in xs]
    return [{"t_entrada": o["t"], "t_saida": o["t_fim"], "R": o["r"], "ativo": o["asset"]} for o in xs]
for k in V["antiga"]["lutadores"]:
    linha = {}
    for v in V:
        L = V[v]["lutadores"][k]
        ops = ops_de(v, k) if v != "antiga" else ops_de("antiga", k)
        m = A.metricas(ops, random.Random(1), 1000) if ops else {"n": 0}
        pa = defaultdict(list)
        for o in ops: pa[o["ativo"]].append(o["R"])
        linha[v] = {"veredicto": L["veredicto"], "n": L["n"], "avg_r_arena": L["avg_r"], "acaso_p95": L["acaso_p95"],
                    "dias": m.get("dias"), "r_por_dia": m.get("media_dia"), "ic90_dia": m.get("ic90_dia"), "soma_r": m.get("soma"),
                    "por_regime": {rg: {"n": x.get("n"), "avg_r": x.get("avg_r"), "veredicto": x.get("veredicto"), "passa_atual": x.get("passa_atual")}
                                   for rg, x in (L.get("por_regime") or {}).items()},
                    "por_moeda": {a: [len(r), round(sum(r) / len(r), 3)] for a, r in sorted(pa.items(), key=lambda kv: -len(kv[1]))}}
    sem = [o for o in V["antiga"]["operacoes"] if o["k"] == k and o["asset"] not in mg]
    out["operacoes_sem_margem_na_arena_antiga"][k] = {"n": len(sem), "fracao": round(len(sem) / max(1, linha["antiga"]["n"] or 1), 3),
                                                      "r_medio": round(sum(o["r"] for o in sem) / len(sem), 3) if sem else None,
                                                      "moedas": sorted({o["asset"] for o in sem})}
    linha["mudou_veredicto"] = len({linha[v]["veredicto"] for v in V}) > 1
    out["lutadores"][k] = linha
json.dump(out, open(f"{G}/comparacao_arena_{dias}.json", "w"), ensure_ascii=False, indent=1)
for k, l in out["lutadores"].items():
    s = out["operacoes_sem_margem_na_arena_antiga"][k]
    print(f"{k:24s} " + " | ".join(f"{v}: {l[v]['veredicto'][:6]} n{l[v]['n']} R{l[v]['avg_r_arena']} dias {l[v]['dias']} R/dia {l[v]['r_por_dia']}" for v in V) + f" || sem margem antiga: {s['n']} ({s['fracao']}) R {s['r_medio']}")
    for v in V:
        if l[v]["por_regime"]: print("    ", v, l[v]["por_regime"])
