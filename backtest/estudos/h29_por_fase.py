"""H29 (pre-registado 31/10, pedido do Rui: "tem de haver estrategias para todas as alturas do mercado").
Pergunta: em cada fase do mercado (subida, lateral, queda), ha alguma familia de estrategia que ganhe?
Fase (pelo BTC diario, so passado): SUBIDA = fecho > SMA200 e SMA50 a subir (vs 10 dias antes);
QUEDA = fecho < SMA200 e SMA50 a descer; LATERAL = o resto.
Familias em velas de 4H, compra e short: DON20 (rompe max/min de 20 velas), DON55, MR25 (RSI14 < 25 / > 75),
MR30 (RSI < 30 / > 70), REV3 (3 velas seguidas a cair/subir com fecho no extremo; aposta na inversao).
Saidas iguais para todas: entrada na abertura seguinte, stop 2 ATR(42), objetivo 2R, 18 velas; 0,25%/lado;
short paga juro 20%/ano. Uma posicao por moeda. Moedas: as 72 atuais + 184 delistadas (sem vies de sobrevivencia).
Periodos: P1 2021-2023, P2 2024-out/2026. Acaso: mesmas moedas, fase, periodo e numero de entradas, 40 repeticoes, z.
k = 10 familias x 3 fases = 30 -> p < 0,0017. Criterio unico: >= +0,15R nos dois periodos, >= 50 ops por periodo,
p < 0,0017, sem top 5% > 0, custos x2 > 0. O que passar vai para papel, nunca direto a dinheiro real."""
import gzip, glob, os, math, numpy as np, multiprocessing as mp
DAY, H4 = 86400, 14400
T0, CUT, T1 = 1609459200 + 220 * DAY, 1704067200, 1792022400
def ler(p):
    r = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
B = ler("/tmp/claude-0/hist/BTC.csv.gz")
def fases():
    d = {}
    for row in B:
        k = int(row[0]) // DAY
        d.setdefault(k, []).append(row[4])
    ks = sorted(d); c = np.array([d[k][-1] for k in ks])
    s200 = np.convolve(c, np.ones(200) / 200, "full")[:len(c)]; s50 = np.convolve(c, np.ones(50) / 50, "full")[:len(c)]
    f = {}
    for i, k in enumerate(ks):
        if i < 210: continue
        up, dn = s50[i - 1] > s50[i - 11], s50[i - 1] < s50[i - 11]       # so dias fechados (i-1)
        if c[i - 1] > s200[i - 1] and up: f[k] = 1
        elif c[i - 1] < s200[i - 1] and dn: f[k] = -1
        else: f[k] = 0
    return f
FASE = fases()
NOMES = {1: "SUBIDA", 0: "LATERAL", -1: "QUEDA"}
def prep(x):
    t, o, h, l, c, v = x.T
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    atr = np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)]; atr[:42] = np.nan
    d_ = np.diff(c, prepend=c[0]); up = np.where(d_ > 0, d_, 0); dn = np.where(d_ < 0, -d_, 0); k = np.ones(14) / 14
    rsi = 100 - 100 / (1 + np.convolve(up, k, "full")[:len(c)] / np.maximum(np.convolve(dn, k, "full")[:len(c)], 1e-12))
    fz = np.array([FASE.get(int(tt + H4) // DAY, 9) for tt in t])
    return dict(t=t, o=o, h=h, l=l, c=c, atr=atr, rsi=rsi, fase=fz)
def rmax(a, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    out = np.full(len(a), np.nan)
    if len(a) > n: out[n:] = sw(a[:-1], n).max(axis=1)[:len(a) - n]
    return out
def rmin(a, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    out = np.full(len(a), np.nan)
    if len(a) > n: out[n:] = sw(a[:-1], n).min(axis=1)[:len(a) - n]
    return out
def sinais(d, fam, lado):
    c, h, l, o = d["c"], d["h"], d["l"], d["o"]
    if fam.startswith("DON"):
        n = int(fam[3:])
        return np.nonzero((c > rmax(h, n)) if lado > 0 else (c < rmin(l, n)))[0]
    if fam.startswith("MR"):
        q = int(fam[2:])
        return np.nonzero((d["rsi"] < q) if lado > 0 else (d["rsi"] > 100 - q))[0]
    if fam == "REV3":
        dn3 = (c < o) & (np.r_[False, c[1:] < o[1:]]) & (np.r_[False, False, c[2:] < o[2:]])
        up3 = (c > o) & (np.r_[False, c[1:] > o[1:]]) & (np.r_[False, False, c[2:] > o[2:]])
        rng = np.maximum(h - l, 1e-12)
        return np.nonzero((dn3 & ((c - l) / rng < 0.2)) if lado > 0 else (up3 & ((h - c) / rng < 0.2)))[0]
def sim(d, idx, lado, mult=1.0):
    t, o, h, l, c, atr = d["t"], d["o"], d["h"], d["l"], d["c"], d["atr"]
    n = len(c); idx = idx[(idx + 19 < n)]; idx = idx[~np.isnan(atr[idx])]
    if not len(idx): return np.array([]), np.array([], int), idx
    e = o[idx + 1]; stop = e - lado * 2 * atr[idx]; risk = np.abs(e - stop); alvo = e + lado * 2 * risk
    res = np.full(len(idx), np.nan); fim = np.full(len(idx), -1)
    for k in range(1, 19):
        j = idx + k
        bad = (l[j] <= stop) if lado > 0 else (h[j] >= stop); ok = (h[j] >= alvo) if lado > 0 else (l[j] <= alvo)
        nv = np.isnan(res); b = nv & bad; res[b] = -risk[b]; fim[b] = j[b]; g = nv & ~bad & ok; res[g] = 2 * risk[g]; fim[g] = j[g]
    nz = np.isnan(res); jj = idx + 18; res[nz] = lado * (c[jj[nz]] - e[nz]); fim[nz] = jj[nz]
    px = e + lado * res
    custo = mult * 0.0025 * (e + px)
    if lado < 0: custo = custo + mult * 0.20 * (t[fim] - t[idx]) / DAY / 365 * e
    return (res - custo) / np.maximum(risk, 1e-12), fim, idx
FAMS = [(f, s) for f in ("DON20", "DON55", "MR25", "MR30", "REV3") for s in (1, -1)]
def moeda(p):
    try:
        x = ler(p)
    except Exception:
        return None
    if len(x) < 600: return None
    d = prep(x); t = d["t"]; rng = np.random.default_rng(abs(hash(p)) % 2**32)
    per = np.where(t < CUT, 1, 2); ok = (t >= T0) & (t < T1)
    out = {}
    for fam, lado in FAMS:
        idx = sinais(d, fam, lado); idx = idx[ok[idx] & (d["fase"][idx] != 9)]
        r, fim, idx2 = sim(d, idx, lado); r2, _, _ = sim(d, idx, lado, 2.0)
        if not len(idx2): continue
        livre, sel = -1, []
        for q in range(len(idx2)):
            if idx2[q] > livre: sel.append(q); livre = fim[q]
        sel = np.array(sel, int)
        for fz in (1, 0, -1):
            for pp in (1, 2):
                m = (d["fase"][idx2[sel]] == fz) & (per[idx2[sel]] == pp)
                if not m.any(): continue
                key = (fam, lado, fz, pp)
                pool = np.nonzero(ok & (d["fase"] == fz) & (per == pp))[0]; pool = pool[(pool > 50) & (pool < len(t) - 21)]
                ac = []
                for _ in range(40):
                    if len(pool) == 0: break
                    ii = np.sort(rng.choice(pool, size=min(int(m.sum()), len(pool)), replace=False))
                    rv, _, _ = sim(d, ii, lado); ac.append(rv.tolist())
                out[key] = (r[sel][m].tolist(), r2[sel][m].tolist(), ac)
    return out
if __name__ == "__main__":
    fich = sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")) + sorted(glob.glob("/tmp/claude-0/delist/*.csv.gz"))
    with mp.Pool(2) as pool:
        partes = [x for x in pool.map(moeda, fich) if x]
    print(f"H29 estrategias por fase do mercado ({len(partes)} moedas com delistadas; R liquido por operacao)")
    dias = {NOMES[k]: sum(1 for v in FASE.values() if v == k) for k in NOMES}
    print("dias em cada fase (2021-26):", dias)
    passou = []
    for fz in (1, 0, -1):
        print(f"--- {NOMES[fz]} ---")
        for fam, lado in FAMS:
            cel, ok = [], True
            for pp in (1, 2):
                key = (fam, lado, fz, pp)
                r = [x for p in partes for x in p.get(key, ([], [], []))[0]]
                r2 = [x for p in partes for x in p.get(key, ([], [], []))[1]]
                if len(r) < 5: cel.append(f"P{pp} n={len(r)}"); ok = False; continue
                ms = []
                for rep in range(40):
                    v = [y for p in partes for ac in [p.get(key, ([], [], []))[2]] if rep < len(ac) for y in ac[rep]]
                    ms.append(np.mean(v) if v else 0)
                mm = float(np.mean(r)); sd = float(np.std(ms)) or 1e-9; pv = 0.5 * math.erfc((mm - np.mean(ms)) / sd / math.sqrt(2))
                top = float(np.mean(sorted(r)[:max(1, int(len(r) * 0.95))])); md = float(np.mean(r2))
                cel.append(f"P{pp} n={len(r):>5} {mm:+.3f}R (acaso {np.mean(ms):+.3f} p={pv:.4f})")
                ok &= mm >= 0.15 and len(r) >= 50 and pv < 0.0017 and top > 0 and md > 0
            nome = f"{fam} {'compra' if lado > 0 else 'short'}"
            print(f"  {nome:<13} {' | '.join(cel)}{'  PASSA' if ok else ''}")
            if ok: passou.append((NOMES[fz], nome))
    print("passam:", passou or "nenhuma")
