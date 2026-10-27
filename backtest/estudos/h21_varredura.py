"""Varredura (pre-registada a 27/10). 74 moedas, velas de 4H 2021-out 2026. Entrada na abertura da vela seguinte.
Custos 0,25% por lado. Uma posicao por moeda. Descoberta: A (jun21-mai24). Confirmacao: B (jun24-abr26).
Prova final: H (mai26-out26). Cada configuracao contra entradas ao acaso (mesmas moedas, lado e saidas).
Familias: DON (rompimento de N dias, stop 3 ATR, saida a seguir 3 ATR, 30 dias), MR (RSI 4H extremo, saida na
media de 20 velas, stop 2 ATR, 3 dias), RS (forca relativa 7d vs BTC no decil extremo + media de 50 velas,
stop 2 ATR, alvo 3R, 10 dias), IGN (vela de ignicao: amplitude >2x, volume >3x, fecho no extremo; stop no outro
extremo, alvo 2R, 2 dias). Lados compra e short. Filtros: nenhum, a favor do BTC (media de 200 dias).
"""
import gzip, glob, os, random, statistics as S, numpy as np, json
H4, DAY = 14400, 86400
A0, A1, B1, H1 = 1622505600, 1717200000, 1777593600, 1792022400   # mai 2026 para a prova final
FEE = 0.0025
data = {}
for p in sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    x = np.array([[float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in rows if len(r) >= 6])
    if len(x) > 600: data[a] = x
btc = data["BTC"]; bt = btc[:, 0]; bc = btc[:, 4]
bsma = np.convolve(bc, np.ones(1200) / 1200, mode="full")[:len(bc)]; bsma[:1200] = np.nan
b7 = np.full(len(bc), np.nan); b7[42:] = bc[42:] / bc[:-42] - 1
bidx = {int(t): i for i, t in enumerate(bt)}
def ind(x):
    t, o, h, l, c, v = x.T
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h, pc) - np.minimum(l, pc)
    atr = np.convolve(tr, np.ones(42) / 42, mode="full")[:len(tr)]
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0); dn = np.where(d < 0, -d, 0)
    k = np.ones(14) / 14
    ru = np.convolve(up, k, "full")[:len(c)]; rd = np.convolve(dn, k, "full")[:len(c)]
    rsi = 100 - 100 / (1 + ru / np.maximum(rd, 1e-12))
    s20 = np.convolve(c, np.ones(20) / 20, "full")[:len(c)]; s50 = np.convolve(c, np.ones(50) / 50, "full")[:len(c)]
    rng = h - l; ar = np.convolve(rng, np.ones(30) / 30, "full")[:len(c)]; av = np.convolve(v, np.ones(30) / 30, "full")[:len(c)]
    r7 = np.full(len(c), np.nan); r7[42:] = c[42:] / c[:-42] - 1
    return dict(t=t, o=o, h=h, l=l, c=c, v=v, atr=atr, rsi=rsi, s20=s20, s50=s50, ar=ar, av=av, r7=r7)
I = {a: ind(x) for a, x in data.items()}
# forca relativa: decis por vela entre moedas
RS = {}
for a, d in I.items():
    if a == "BTC": continue
    bi = np.array([bidx.get(int(t), -1) for t in d["t"]])
    RS[a] = np.where(bi >= 0, d["r7"] - b7[np.maximum(bi, 0)], np.nan)
    d["bup"] = np.where(bi >= 0, bc[np.maximum(bi, 0)] > bsma[np.maximum(bi, 0)], False)
allrs = np.concatenate([v[~np.isnan(v)] for v in RS.values()])
q10, q90 = np.percentile(allrs, 10), np.percentile(allrs, 90)

def sinais(d, a, fam, par, lado):
    c, h, l, n = d["c"], d["h"], d["l"], len(d["c"])
    if fam == "DON":
        N = par * 6
        hi = np.array([h[max(0, i - N):i].max() if i >= N else np.inf for i in range(n)])
        lo = np.array([l[max(0, i - N):i].min() if i >= N else -np.inf for i in range(n)])
        return (c > hi) if lado > 0 else (c < lo)
    if fam == "MR":
        return (d["rsi"] < par) if lado > 0 else (d["rsi"] > 100 - par)
    if fam == "RS":
        r = RS.get(a)
        if r is None: return np.zeros(n, bool)
        return ((r > q90) & (c > d["s50"])) if lado > 0 else ((r < q10) & (c < d["s50"]))
    if fam == "IGN":
        rg = h - l; pos = (c - l) / np.maximum(rg, 1e-12)
        base = (rg > par * d["ar"]) & (d["v"] > 3 * d["av"])
        return base & (pos > 0.8) if lado > 0 else base & (pos < 0.2)

def sair(d, i, lado, fam):
    """entrada na abertura de i+1; devolve (R, indice de saida)"""
    n = len(d["c"])
    if i + 1 >= n: return None
    e = d["o"][i + 1]; atr = d["atr"][i]
    if not atr or atr <= 0 or e <= 0: return None
    if fam == "IGN":
        stop = d["l"][i] if lado > 0 else d["h"][i]
        if (e - stop) * lado <= 0: return None
    else:
        stop = e - lado * (3 if fam == "DON" else 2) * atr
    risk = abs(e - stop)
    alvo = e + lado * (3 if fam == "RS" else 2) * risk if fam in ("RS", "IGN") else None
    hold = {"DON": 180, "MR": 18, "RS": 60, "IGN": 12}[fam]
    trail = stop
    for j in range(i + 1, min(n, i + 1 + hold)):
        h, l, c = d["h"][j], d["l"][j], d["c"][j]
        if (l <= trail) if lado > 0 else (h >= trail):
            px = trail; break
        if alvo is not None and ((h >= alvo) if lado > 0 else (l <= alvo)):
            px = alvo; break
        if fam == "MR" and ((c >= d["s20"][j]) if lado > 0 else (c <= d["s20"][j])):
            px = c; break
        if fam == "DON":
            trail = max(trail, c - 3 * d["atr"][j]) if lado > 0 else min(trail, c + 3 * d["atr"][j])
    else:
        j = min(n - 1, i + hold); px = d["c"][j]
    R = lado * (px - e) / risk - 2 * FEE * e / risk
    return max(R, -3.0), j

PERS = (("A", A0, A1), ("B", A1, B1), ("H", B1, H1))
def corre(fam, par, lado, filtro, aleatorio=None):
    out = {p: [] for p, _, _ in PERS}
    rng = random.Random(7)
    for a, d in I.items():
        if a == "BTC": continue
        s = sinais(d, a, fam, par, lado)
        if filtro: s = s & (d["bup"] if lado > 0 else ~d["bup"])
        idx = np.nonzero(s)[0]
        if aleatorio:     # mesmas quantidades por periodo, momentos ao acaso
            novo = []
            for p, t0, t1 in PERS:
                k = int(((d["t"][idx] >= t0) & (d["t"][idx] < t1)).sum())
                cand = np.nonzero((d["t"] >= t0) & (d["t"] < t1))[0]
                if k and len(cand): novo += sorted(rng.sample(list(cand), min(k, len(cand))))
            idx = np.array(sorted(novo), dtype=int)
        livre = -1
        for i in idx:
            if i <= livre: continue
            t = d["t"][i]
            per = next((p for p, t0, t1 in PERS if t0 <= t < t1), None)
            if not per: continue
            r = sair(d, i, lado, fam)
            if not r: continue
            out[per].append(r[0]); livre = r[1]
    return out

cfgs = []
for lado in (1, -1):
    for filtro in (False, True):
        for N in (10, 20, 55): cfgs.append(("DON", N, lado, filtro))
        for q in (20, 25, 30): cfgs.append(("MR", q, lado, filtro))
        cfgs.append(("RS", 0, lado, filtro))
        for m in (2.0, 3.0): cfgs.append(("IGN", m, lado, filtro))
res = []
for f in cfgs:
    r = corre(*f); z = corre(*f, aleatorio=True)
    row = {"cfg": f"{f[0]}{f[1]:g} {'compra' if f[2] > 0 else 'short'}{' +filtroBTC' if f[3] else ''}"}
    for p in ("A", "B", "H"):
        row[p] = (len(r[p]), S.mean(r[p]) if r[p] else None, S.mean(z[p]) if z[p] else None)
    res.append(row)
json.dump(res, open("/tmp/claude-0/-home-claude/c24514fd-e14e-5ed3-ac5f-71d5f0688a07/scratchpad/varredura.json", "w"))
fmt = lambda x: "   –  " if x is None else f"{x:+.3f}"
print(f"{'configuração':<26}{'A n':>6}{'A R':>8}{'acaso':>8}{'B n':>6}{'B R':>8}{'acaso':>8}{'H n':>5}{'H R':>8}{'acaso':>8}")
for row in sorted(res, key=lambda r: -((r['A'][1] or -9) - (r['A'][2] or 0))):
    print(f"{row['cfg']:<26}" + "".join(f"{row[p][0]:>6}{fmt(row[p][1]):>8}{fmt(row[p][2]):>8}" if p != "H" else f"{row[p][0]:>5}{fmt(row[p][1]):>8}{fmt(row[p][2]):>8}" for p in ("A", "B", "H")))
