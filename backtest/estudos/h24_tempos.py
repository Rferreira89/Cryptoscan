"""H24 (pre-registado 29/10, antes de correr): varios tempos de grafico.
Mesma estrategia em velas de 1H, 4H e 1D, com os parametros contados em velas (o grafico muda a velocidade).
Parte 1 - compra no panico (H23 L10) em 1H e 1D: financiamento ja pago <0 e <= p5 dos 270 anteriores,
  queda >= 10% em 18 velas, limite 1% abaixo do fecho valido 2 velas, stop 2 ATR(42), objetivo 2R,
  18 velas; custos 0,10% limite / 0,25% stop e tempo. Periodos B1 ago-set/2024..set/2025, B2 out/2025-out/2026.
Parte 2 - familias classicas em 1H (B1/B2) e 1D (A jun/2021-mai/2024, B jun/2024-out/2026):
  DON20, DON55 (fecho rompe o max/min de N velas), MR25, MR30 (RSI14 abaixo/acima de q / 100-q),
  IGN2, IGN3 (amplitude > m x media de 30, volume > 3x, fecho no extremo); compra e short.
  Saidas iguais para todas (diferente do H21, declarado): entrada a mercado na abertura seguinte, stop 2 ATR(42),
  objetivo 2R, 18 velas, 0,25%/lado (+ juro 20%/ano no short). Uma posicao por moeda.
Acaso: mesmo numero de entradas por moeda e periodo em velas ao acaso, mesmas saidas; 40 repeticoes;
p por aproximacao normal (z). 26 configuracoes -> Bonferroni p < 0,002.
Criterio: >= +0,15R nos dois periodos, >= 50 ops por periodo, p < 0,002, sem top 5% > 0, custos x2 > 0."""
import gzip, glob, os, math, random, statistics as S, numpy as np
DAY = 86400
CUT_B = 1759276800; A0, A1, B1E = 1622505600, 1717200000, 1792022400
def ler(p):
    r = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
def diario(x):
    d = {}
    for row in x:
        k = int(row[0]) // DAY
        if k not in d: d[k] = [k * DAY, row[1], row[2], row[3], row[4], row[5], 1]
        else:
            v = d[k]; v[2] = max(v[2], row[2]); v[3] = min(v[3], row[3]); v[4] = row[4]; v[5] += row[5]; v[6] += 1
    return np.array([v[:6] for v in d.values() if v[6] == 6])
def prep(x):
    t, o, h, l, c, v = x.T
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    atr = np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)]; atr[:42] = np.nan
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0); dn = np.where(d < 0, -d, 0)
    k = np.ones(14) / 14
    rsi = 100 - 100 / (1 + np.convolve(up, k, "full")[:len(c)] / np.maximum(np.convolve(dn, k, "full")[:len(c)], 1e-12))
    rg = h - l
    return dict(t=t, o=o, h=h, l=l, c=c, v=v, atr=atr, rsi=rsi, rg=rg,
                ar=np.convolve(rg, np.ones(30) / 30, "full")[:len(c)], av=np.convolve(v, np.ones(30) / 30, "full")[:len(c)])
def rolling_ext(a, n, f):
    out = np.full(len(a), np.nan)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    if len(a) > n: out[n:] = f(sw(a[:-1], n), axis=1)[:len(a) - n]
    return out
def sim_vec(d, idx, lado, entrada=None, fee_in=0.0025, fee_tp=0.0025, mult=1.0, dur=None):
    """idx: velas do sinal; entrada na abertura seguinte (ou precos dados, ja na vela idx+1)."""
    t, o, h, l, c, atr = d["t"], d["o"], d["h"], d["l"], d["c"], d["atr"]
    n = len(c); idx = idx[(idx + 19 < n) & ~np.isnan(atr[idx])]
    if not len(idx): return np.array([]), np.array([], int), idx
    e = o[idx + 1] if entrada is None else entrada[:len(idx)]
    stop = e - lado * 2 * atr[idx]; risk = np.abs(e - stop); alvo = e + lado * 2 * risk
    res = np.full(len(idx), np.nan); fim = np.full(len(idx), -1)
    for k in range(1, 19):
        j = idx + k
        hs, ls = h[j], l[j]
        bad = (ls <= stop) if lado > 0 else (hs >= stop)
        ok = (hs >= alvo) if lado > 0 else (ls <= alvo)
        novo = np.isnan(res)
        b = novo & bad; res[b] = -risk[b] * 1.0; fim[b] = j[b]
        g = novo & ~bad & ok; res[g] = 2 * risk[g]; fim[g] = j[g]
    nz = np.isnan(res); jj = idx + 18; res[nz] = lado * (c[jj[nz]] - e[nz]); fim[nz] = jj[nz]
    px = e + lado * res
    tp = ~nz & (res > 0)
    custo = mult * (fee_in * e + np.where(tp, fee_tp, 0.0025) * px)
    if lado < 0: custo = custo + mult * 0.20 * (t[fim] - t[idx]) / DAY / 365 * e
    return (res - custo) / risk, fim, idx
def nao_sobrepor(idx, fim):
    out, livre = [], -1
    for k in np.argsort(idx):
        if idx[k] > livre: out.append(k); livre = fim[k]
    return np.array(out, int)
def periodo(t, tf):
    if tf == "1H": return np.where(t < CUT_B, "P1", "P2")
    return np.where(t < A1, "P1", "P2")
def valido(t, tf):
    return (t >= A0) & (t < B1E) if tf == "1D" else (t < B1E)

TFS = {}
for p in sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    x4 = ler(p)
    if len(x4) < 600: continue
    TFS.setdefault("1D", {})[a] = prep(diario(x4))
for p in sorted(glob.glob("/tmp/claude-0/hist/1h/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]; x = ler(p)
    if len(x) > 2000: TFS.setdefault("1H", {})[a] = prep(x)
FUND = {}
for p in glob.glob("/tmp/claude-0/hist/funding/*.csv.gz"):
    a = os.path.basename(p).split(".")[0]
    r = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    FUND[a] = np.array([[float(z[0]), float(z[1])] for z in r if len(z) >= 2])
rng = np.random.default_rng(24)

def avaliar(nome, tf, gerar, lado, limite=False):
    linhas = {"P1": [], "P2": []}; dob = {"P1": [], "P2": []}; cont = {}
    for a, d in TFS[tf].items():
        idx = gerar(a, d)
        if idx is None or not len(idx): continue
        idx = idx[valido(d["t"][idx], tf)]
        if limite:
            lim = d["c"][idx] * 0.99; ent, keep = [], []
            for q, i in enumerate(idx):
                if i + 20 >= len(d["c"]): continue
                k0 = next((k for k in (i + 1, i + 2) if d["l"][k] <= lim[q]), None)
                if k0 is None: continue
                keep.append(k0 - 1); ent.append(min(lim[q], d["o"][k0]))
            idx = np.array(keep, int); ent = np.array(ent)
            r, fim, idx2 = sim_vec(d, idx, lado, ent, 0.001, 0.001); r2, _, _ = sim_vec(d, idx, lado, ent, 0.001, 0.001, 2.0)
        else:
            r, fim, idx2 = sim_vec(d, idx, lado); r2, _, _ = sim_vec(d, idx, lado, mult=2.0)
        if not len(idx2): continue
        sel = nao_sobrepor(idx2, fim)
        pr = periodo(d["t"][idx2[sel]], tf)
        for per in ("P1", "P2"):
            m = pr == per
            linhas[per] += list(r[sel][m]); dob[per] += list(r2[sel][m]); cont[(a, per)] = int(m.sum())
    out, ok = {}, True
    for per in ("P1", "P2"):
        rr = linhas[per]
        if len(rr) < 5: out[per] = None; ok = False; continue
        ms = []
        for _ in range(40):
            v = []
            for a, d in TFS[tf].items():
                k = cont.get((a, per), 0)
                if not k: continue
                tt = d["t"]; pool = np.nonzero((periodo(tt, tf) == per) & valido(tt, tf))[0]
                pool = pool[(pool > 60) & (pool < len(tt) - 21)]
                if not len(pool): continue
                ii = rng.choice(pool, size=min(k, len(pool)), replace=False)
                rv, _, _ = sim_vec(d, np.sort(ii), lado)
                v += list(rv)
            ms.append(np.mean(v) if v else 0)
        m = float(np.mean(rr)); mu, sd = float(np.mean(ms)), float(np.std(ms)) or 1e-9
        z = (m - mu) / sd; pv = 0.5 * math.erfc(z / math.sqrt(2))
        top = float(np.mean(sorted(rr)[:max(1, int(len(rr) * 0.95))])); md = float(np.mean(dob[per]))
        out[per] = (len(rr), m, mu, pv, top, md)
        ok &= m >= 0.15 and len(rr) >= 50 and pv < 0.002 and top > 0 and md > 0
    return out, ok

def g_panico(a, d):
    f = FUND.get(a)
    if f is None or len(f) < 300: return None
    t, c = d["t"], d["c"]; ft, fv = f[:, 0], f[:, 1]
    out = []
    step = 3600 if len(t) > 1 and t[1] - t[0] < 7200 else DAY
    for i in range(60, len(c) - 1):
        k = np.searchsorted(ft, t[i] + step, side="right") - 1
        if k < 270 or fv[k] >= 0 or c[i] / c[i - 18] - 1 > -0.10: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5): out.append(i)
    return np.array(out, int)
def g_don(n, lado):
    def g(a, d):
        ref = rolling_ext(d["h"] if lado > 0 else d["l"], n, np.max if lado > 0 else np.min)
        s = (d["c"] > ref) if lado > 0 else (d["c"] < ref)
        return np.nonzero(s & ~np.isnan(ref))[0]
    return g
def g_mr(q, lado):
    return lambda a, d: np.nonzero((d["rsi"] < q) if lado > 0 else (d["rsi"] > 100 - q))[0][1:]
def g_ign(m, lado):
    def g(a, d):
        pos = (d["c"] - d["l"]) / np.maximum(d["rg"], 1e-12)
        base = (d["rg"] > m * d["ar"]) & (d["v"] > 3 * d["av"])
        return np.nonzero(base & ((pos > 0.8) if lado > 0 else (pos < 0.2)))[0][30:]
    return g
cfgs = [("PANICO-L10", "1H", g_panico, 1, True), ("PANICO-L10", "1D", g_panico, 1, True)]
for tf in ("1H", "1D"):
    for lado, nm in ((1, "compra"), (-1, "short")):
        cfgs += [(f"DON20 {nm}", tf, g_don(20, lado), lado, False), (f"DON55 {nm}", tf, g_don(55, lado), lado, False),
                 (f"MR25 {nm}", tf, g_mr(25, lado), lado, False), (f"MR30 {nm}", tf, g_mr(30, lado), lado, False),
                 (f"IGN2 {nm}", tf, g_ign(2.0, lado), lado, False), (f"IGN3 {nm}", tf, g_ign(3.0, lado), lado, False)]
print("H24 varios tempos de grafico (R liquido por operacao; P1/P2 = 2024-25/2025-26 em 1H, 2021-24/2024-26 em 1D)")
for nome, tf, g, lado, lim in cfgs:
    o, ok = avaliar(nome, tf, g, lado, lim)
    f = lambda x: "  sem dados" if not x else f"n={x[0]:>5} {x[1]:+.3f}R acaso {x[2]:+.3f} p={x[3]:.3f} s/top {x[4]:+.3f} x2 {x[5]:+.3f}"
    print(f"{tf} {nome:<16} P1 {f(o['P1'])} | P2 {f(o['P2'])} -> {'PASSA' if ok else 'chumba'}")
