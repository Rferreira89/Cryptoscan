"""A maquina do tempo preve o resultado dos sinais do Ramiro? Sinais 2021-26 (quebra do minimo de
20 dias, stop 2N, 1.o objetivo 2R, 20 dias). Maquina so com dados ANTES do sinal (2000 percursos)."""
import gzip, glob, os, sys
sys.path.insert(0, "/home/claude/cryptoscan")
from engine import backtest as B, maquina_tempo as M
DAY, H4 = 86400, 14400
out = []
for p in sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    c4 = [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
           "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]
    if len(c4) < 1500: continue
    dd = B.daily(c4); last = -10**12
    for i in range(1200, len(c4) - 121):
        t = c4[i]["t"]
        if t - last < 5 * DAY: continue
        d = [x for x in dd if x["t"] + DAY <= t + H4]
        if len(d) < 25: continue
        lo20 = min(x["l"] for x in d[-21:-1])
        if not (c4[i]["c"] < lo20 <= c4[i - 1]["c"]): continue
        tr = [max(d[k]["h"], d[k-1]["c"]) - min(d[k]["l"], d[k-1]["c"]) for k in range(len(d)-20, len(d))]
        n = sum(tr) / 20; e = c4[i]["c"]; stop = e + 2 * n; alvo = e - 2 * (stop - e)
        if alvo <= 0: continue
        fim = None; px = e
        for x in c4[i+1:i+121]:
            fim = M._passo("SHORT", x["h"], x["l"], stop, alvo); px = x["c"]
            if fim: break
        R = 2.0 if fim == "alvo" else -1.0 if fim == "stop" else (e - px) / (stop - e)
        R -= 0.007 * e / (stop - e)
        mt = M.simular(c4[:i+1], "SHORT", e, stop, alvo, 20 * DAY, n=2000)
        if mt: out.append((mt["alvo_pct"], mt["r_medio"], fim or "nenhum", R, t)); last = t
print("sinais:", len(out))
import statistics as S
CUT = 1717200000
for per, g0 in (("A 2021-mai 2024", [x for x in out if x[4] < CUT]), ("B jun 2024-out 2026", [x for x in out if x[4] >= CUT])):
    g0 = sorted(g0); k = len(g0) // 3
    print(per, "n=", len(g0), "todos:", round(S.mean(x[3] for x in g0), 3), "R")
    for nome, g in (("menos hipótese", g0[:k]), ("meio", g0[k:2*k]), ("mais hipótese", g0[2*k:])):
        print(f"   {nome:<16} máquina {S.mean(x[0] for x in g):5.1f}%  real alvo {100*sum(x[2]=='alvo' for x in g)/len(g):5.1f}%  média {S.mean(x[3] for x in g):+.3f}R  (n={len(g)})")
