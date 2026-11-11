import json, random, importlib.util, sys
G = sys.argv[1]
sp = importlib.util.spec_from_file_location("aud", G + "/qb/aud.py"); A = importlib.util.module_from_spec(sp); sp.loader.exec_module(A)
def piloto(ops, k, n_ops, reps=4000, rng=None):
    """Teto de k abertas (empates ao acaso); depois blocos de n_ops operacoes seguidas, sorteados ao longo do
    historico: P(soma < 0), percentis da soma e do pior drawdown, em R."""
    rng = rng or random.Random(3)
    xs = sorted(A.limitar_simultaneas(ops, k, random.Random(1)), key=lambda o: o["t_entrada"])
    rs = [o["R"] for o in xs]
    if len(rs) <= n_ops: return {"n": len(rs)}
    somas, dds = [], []
    for _ in range(reps):
        i = rng.randrange(0, len(rs) - n_ops)
        eq = pk = dd = 0.0
        for r in rs[i:i + n_ops]:
            eq += r; pk = max(pk, eq); dd = min(dd, eq - pk)
        somas.append(eq); dds.append(dd)
    somas.sort(); dds.sort()
    q = lambda v, p: round(v[int(p * len(v))], 2)
    eq = pk = ddt = 0.0
    for r in rs:
        eq += r; pk = max(pk, eq); ddt = min(ddt, eq - pk)
    return {"n_com_teto": len(rs), "media_op": round(sum(rs) / len(rs), 3), "blocos_de": n_ops,
            "p_soma_negativa": round(sum(1 for s in somas if s < 0) / len(somas), 3),
            "soma_p05": q(somas, 0.05), "soma_p50": q(somas, 0.5), "pior_dd_p05": q(dds, 0.05), "dd_historico_total": round(ddt, 2)}
if __name__ == "__main__":
    f, est, k, n = sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    ops = [o for o in json.load(open(f))["operacoes"] if (o.get("estrategia") == est or est == "*") and o["t_entrada"] < A.CORTE]
    print(json.dumps(piloto(ops, k, n)))
