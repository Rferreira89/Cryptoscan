"""H17 (pre-registado a 23/10, antes de correr). Reversao de curto prazo entre moedas.
Todas as segundas 00h UTC, entre as 25 moedas liquidas (>= 5 M USD/dia):
  H17a compra as 3 com PIOR retorno de 7 dias (so com o BTC acima da media de 200 dias), 7 dias.
  H17b vende a descoberto as 3 com MELHOR retorno de 7 dias (sem filtro), 7 dias, juro 20%/ano.
Custos 0,35% por lado. Referencia: as 25 moedas em pesos iguais na mesma semana (para H17a)
e o simetrico (para H17b). Criterio: nos DOIS periodos, retorno medio semanal liquido do cabaz
>= +0,5% E acima da referencia em >= 0,5 pontos; >= 40 semanas por periodo.
"""
import gzip, glob, os, sys, statistics, json
sys.path.insert(0, "/home/claude/cryptoscan")
from engine import backtest as B
DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
C = 0.0035


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


vol = {}
for p in glob.glob("/tmp/claude-0/hist/*.csv.gz"):
    a = os.path.basename(p).split(".")[0]; c = load(p); vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
moedas = sorted(vol, key=lambda a: -vol[a])[:25]
D = {a: {x["t"] // DAY: x for x in B.daily(load(f"/tmp/claude-0/hist/{a}.csv.gz"))} for a in moedas}
btc = sorted(D["BTC"].items())
bc = {d: x["c"] for d, x in btc}


def liq(a, d):
    v = [D[a][k]["v"] * D[a][k]["c"] for k in range(d - 30, d) if k in D[a]]
    return statistics.median(v) if len(v) >= 20 else 0


def sma200(d):
    v = [bc[k] for k in range(d - 200, d) if k in bc]
    return sum(v) / len(v) if len(v) >= 190 else None


res = {"a": [], "b": [], "ref": []}
d0 = (A0 // DAY) - ((A0 // DAY) - 4) % 7        # segunda-feira
for d in range(d0, B1 // DAY - 7, 7):
    univ = [a for a in moedas if all(k in D[a] for k in (d - 8, d - 1, d + 6)) and liq(a, d) >= 5e6]
    if len(univ) < 10:
        continue
    r7 = {a: D[a][d - 1]["c"] / D[a][d - 8]["c"] - 1 for a in univ}
    fwd = {a: D[a][d + 6]["c"] / D[a][d - 1]["c"] - 1 for a in univ}     # entra no fecho de domingo, sai no fecho do domingo seguinte
    ordem = sorted(univ, key=lambda a: r7[a])
    ref = sum(fwd.values()) / len(fwd)
    m = sma200(d)
    if m and bc[d - 1] > m:
        res["a"].append((d, sum(fwd[a] for a in ordem[:3]) / 3 - 2 * C, ref - 2 * C))
    res["b"].append((d, -sum(fwd[a] for a in ordem[-3:]) / 3 - 2 * C - 0.20 * 7 / 365, -ref - 2 * C - 0.20 * 7 / 365))
for k in ("a", "b"):
    print(f"H17{k}")
    ok = True
    for nome, t0, t1 in (("A", A0, A1), ("B", B0, B1)):
        s = [x for x in res[k] if t0 // DAY <= x[0] < t1 // DAY]
        if not s:
            print(" ", nome, "sem semanas"); ok = False; continue
        mr = sum(x[1] for x in s) / len(s); mref = sum(x[2] for x in s) / len(s)
        win = sum(1 for x in s if x[1] > 0) / len(s)
        eq = 1; pk = 1; dd = 0
        for x in s:
            eq *= 1 + x[1]; pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
        print(f"  {nome}: {len(s)} semanas, médio {mr*100:+.2f}%/semana, referência {mref*100:+.2f}%, acerto {win:.0%}, acumulado {(eq-1)*100:+.0f}%, queda máx. {dd*100:.0f}%")
        ok &= len(s) >= 40 and mr >= 0.005 and mr - mref >= 0.005
    print("  ->", "PASSA" if ok else "CHUMBA")
