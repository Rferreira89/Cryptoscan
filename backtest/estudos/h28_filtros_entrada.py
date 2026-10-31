"""H28 (pre-registado 31/10, pedido do Rui: "cada grafico tem que ser bem analisado para entrarmos certeiros").
Compra no panico L10 (H23) com um filtro de confirmacao no grafico da vela do sinal. Variantes (k=4, p<0,0125):
  F-PAVIO  a vela do sinal tem pavio inferior >= 40% da amplitude (compradores a rejeitar a queda)
  F-VOL    volume da vela do sinal >= 2x a media de 30 velas (capitulacao com volume)
  F-BTC    o BTC nao caiu mais de 3% nas ultimas 6 velas (panico da moeda, nao do mercado todo)
  F-RSI    RSI(14) de 4H abaixo de 25 (sobrevenda extrema)
Referencia: L10 sem filtro, +0,08R/+0,08R. Mesmos dados, metades, saidas e custos do H23.
Criterio unico: >= +0,15R nas duas metades, >= 50 ops por metade, p < 0,0125 contra o acaso, sem top 5% > 0, custos x2 > 0.
Mostra-se tambem a % de acerto (o Rui pediu entradas mais certeiras)."""
import gzip, glob, os, random, math, statistics as S, numpy as np
src = open(os.path.join(os.path.dirname(__file__), "h23_ordens_limite.py")).read().split("modos = (")[0]
exec(src)
def load4v(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
btc = load4v("BTC"); BT, BC = btc[:, 0], btc[:, 4]
def btc_ret6(t):
    k = np.searchsorted(BT, t, side="right") - 1
    return BC[k] / BC[k - 6] - 1 if k >= 6 else 0
def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0); dn = np.where(d < 0, -d, 0)
    k = np.ones(n) / n
    return 100 - 100 / (1 + np.convolve(up, k, "full")[:len(c)] / np.maximum(np.convolve(dn, k, "full")[:len(c)], 1e-12))
FILTROS = {"REF": lambda d, i: True,
           "F-PAVIO": lambda d, i: (min(d["o"][i], d["c"][i]) - d["l"][i]) >= 0.4 * max(d["h"][i] - d["l"][i], 1e-12),
           "F-VOL": lambda d, i: d["v"][i] >= 2 * d["av"][i],
           "F-BTC": lambda d, i: btc_ret6(d["t"][i]) > -0.03,
           "F-RSI": lambda d, i: d["rsi"][i] < 25}
res = {f: {"B1": [], "B2": []} for f in FILTROS}; dob = {f: {"B1": [], "B2": []} for f in FILTROS}; cands = {f: [] for f in FILTROS}
for p in sorted(glob.glob("/tmp/claude-0/hist/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"/tmp/claude-0/hist/{a}.csv.gz"): continue
    x, f = load4v(a), loadf(a)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c, v = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4], x[:, 5]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    d = dict(t=t, o=o, h=h, l=l, c=c, v=v, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)],
             av=np.convolve(v, np.ones(30) / 30, "full")[:len(v)], rsi=rsi(c))
    ft, fv = f[:, 0], f[:, 1]; sinais = []
    for i in range(30, len(c) - 2):
        if t[i] < ft[0] + 90 * DAY: continue
        k = np.searchsorted(ft, t[i] + H4, side="right") - 1
        if k < 270: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10:
            sinais.append(i)
    for nome, fil in FILTROS.items():
        livre = -1; sn = [i for i in sinais if fil(d, i)]
        for i in sn:
            if i <= livre: continue
            s = sim(d, i, "L10")
            if not s or s[0] == "sem": continue
            per = "B1" if t[i] < CUT else "B2"
            res[nome][per].append(s[0]); dob[nome][per].append(sim(d, i, "L10", 2.0)[0]); livre = s[1]
        cands[nome].append((d, sn))
rng = random.Random(28)
print("H28 compra no panico com filtros de confirmacao no grafico (R liquido por operacao)")
for nome in FILTROS:
    ok = nome != "REF"; cel = []
    for per in ("B1", "B2"):
        r = res[nome][per]
        if len(r) < 5: cel.append(f"{per} n={len(r)}"); ok = False; continue
        ms = []
        for _ in range(100):
            vv = []
            for d, sn in cands[nome]:
                t = d["t"]; nsn = sum(1 for i in sn if (t[i] < CUT) == (per == "B1"))
                if not nsn: continue
                pool = np.nonzero(((t < CUT) if per == "B1" else (t >= CUT)) & (t >= t[0] + 90 * DAY))[0]
                pool = pool[(pool > 30) & (pool < len(t) - 3)]
                for i in rng.sample(list(pool), min(nsn, len(pool))):
                    s = sim(d, i, "L10")
                    if s and s[0] != "sem": vv.append(s[0])
            ms.append(S.mean(vv) if vv else 0)
        mm = S.mean(r); sd = S.pstdev(ms) or 1e-9; pv = 0.5 * math.erfc((mm - S.mean(ms)) / sd / math.sqrt(2))
        top = S.mean(sorted(r)[:max(1, int(len(r) * 0.95))]); md = S.mean(dob[nome][per]); ac = 100 * sum(x > 0 for x in r) / len(r)
        cel.append(f"{per} n={len(r)} {mm:+.3f}R acerto {ac:.0f}% p={pv:.4f} s/top {top:+.3f} x2 {md:+.3f}")
        ok &= mm >= 0.15 and len(r) >= 50 and pv < 0.0125 and top > 0 and md > 0
    print(f" {nome:<8} {' | '.join(cel)} -> {'PASSA' if ok else ('referência' if nome == 'REF' else 'chumba')}")
