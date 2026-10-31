"""H31 (pre-registado 31/10, pedido do Rui: "arranjar maneira de termos uma estrategia de Longs").
Padroes de compra vistos no grafico do BNB de 30/10, nunca testados antes (velas de 4H):
  MECHA    vela de queda forte (amplitude >= 2,5 ATR) com mecha inferior >= 50% da amplitude e fecho na metade de
           cima: liquidacoes absorvidas. Compra na abertura seguinte; stop 0,2 ATR abaixo do minimo da mecha.
  MECHA-L  o mesmo com ordem limite no meio da mecha (valida 2 velas, entrada 0,10% sem deslize).
  BASE     depois de uma queda >= 8% em <= 3 velas, 6 a 12 velas de consolidacao (amplitude da base <= 2 ATR) e
           fecho acima do maximo da base: compra na abertura seguinte; stop 0,2 ATR abaixo do minimo da base.
  BASE-B   o mesmo, so com o BTC acima da SMA200 diaria.
Saidas: objetivo 2R, saida em 18 velas; custos 0,25%/lado (MECHA-L: 0,10% a entrar). Uma posicao por moeda.
Moedas: 72 atuais + 184 delistadas. Periodos P1 2021-2023, P2 2024-out/2026. Acaso: mesmas moedas e periodo,
mesmo numero de entradas, stop a mesma distancia relativa (em ATR) do preco, 40 repeticoes, z.
k=4 -> p < 0,0125. Criterio unico: >= +0,15R nos dois periodos, >= 50 ops/periodo, p < 0,0125, sem top 5% > 0,
custos x2 > 0. O que passar vai para papel ao vivo."""
import gzip, glob, os, math, numpy as np, multiprocessing as mp
DAY, H4 = 86400, 14400
T0, CUT, T1 = 1609459200 + 220 * DAY, 1704067200, 1792022400
def ler(p):
    r = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
B = ler("/tmp/claude-0/hist/BTC.csv.gz")
def acima_sma200():
    d = {}
    for row in B: d[int(row[0]) // DAY] = row[4]
    ks = sorted(d); c = np.array([d[k] for k in ks]); s = np.convolve(c, np.ones(200) / 200, "full")[:len(c)]
    return {k: bool(c[i - 1] > s[i - 1]) for i, k in enumerate(ks) if i > 201}
ACIMA = acima_sma200()
def prep(x):
    t, o, h, l, c, v = x.T
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    atr = np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)]; atr[:42] = np.nan
    return dict(t=t, o=o, h=h, l=l, c=c, atr=atr)
def sinais(d, var):
    t, o, h, l, c, atr = d["t"], d["o"], d["h"], d["l"], d["c"], d["atr"]
    n = len(c); out = []
    if var.startswith("MECHA"):
        rng = h - l; corpo_min = np.minimum(o, c)
        m = (rng >= 2.5 * atr) & ((corpo_min - l) >= 0.5 * rng) & (c >= l + 0.5 * rng) & ~np.isnan(atr)
        for i in np.nonzero(m)[0]:
            out.append((i, l[i] - 0.2 * atr[i], (l[i] + corpo_min[i]) / 2))
        return out
    for i in range(60, n - 1):
        if np.isnan(atr[i]): continue
        for L in range(6, 13):
            b0 = i - L                      # base = velas b0..i-1; queda acaba em b0-1
            q0 = b0 - 3
            if q0 < 1: break
            if c[b0 - 1] / c[q0 - 1] - 1 > -0.08: continue
            hi, lo = h[b0:i].max(), l[b0:i].min()
            if hi - lo > 2 * atr[i] or c[i] <= hi or c[i - 1] > hi: continue
            if var == "BASE-B" and not ACIMA.get(int(t[i] + H4) // DAY, False): break
            out.append((i, lo - 0.2 * atr[i], None)); break
    return out
def sim(d, i, stop, lim=None, mult=1.0):
    t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]; n = len(c)
    if i + 20 >= n: return None
    if lim is None:
        k0, e, fin = i + 1, o[i + 1], 0.0025
    else:
        k0 = next((k for k in (i + 1, i + 2) if l[k] <= lim), None)
        if k0 is None: return ("sem", None)
        e, fin = min(lim, o[k0]), 0.0010
    if not stop < e: return None
    risk = e - stop; alvo = e + 2 * risk; px = None; fout = 0.0025
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or lim is None or o[j] > stop): px = stop; break
        if h[j] >= alvo: px = alvo; break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return (((px - e) - mult * (fin * e + fout * px)) / risk, j)
VARS = ("MECHA", "MECHA-L", "BASE", "BASE-B")
def moeda(p):
    try: x = ler(p)
    except Exception: return None
    if len(x) < 600: return None
    d = prep(x); t = d["t"]; rng = np.random.default_rng(abs(hash(p)) % 2**32)
    out = {}
    for var in VARS:
        base = "MECHA" if var.startswith("MECHA") else var
        sg = sinais(d, base if var != "BASE-B" else "BASE-B")
        livre = -1
        for i, stop, meio in sg:
            if i <= livre or not (T0 <= t[i] < T1): continue
            lim = meio if var == "MECHA-L" else None
            s = sim(d, i, stop, lim)
            if not s or s[0] == "sem": continue
            s2 = sim(d, i, stop, lim, 2.0)
            per = 1 if t[i] < CUT else 2
            dist = (d["o"][i + 1] - stop) / d["atr"][i]
            out.setdefault((var, per), {"r": [], "x2": [], "dist": []})
            out[(var, per)]["r"].append(s[0]); out[(var, per)]["x2"].append(s2[0]); out[(var, per)]["dist"].append(dist)
            livre = s[1]
    for (var, per), v in list(out.items()):
        pool = np.nonzero((t >= T0) & (t < T1) & ((t < CUT) if per == 1 else (t >= CUT)) & ~np.isnan(d["atr"]))[0]
        pool = pool[(pool > 60) & (pool < len(t) - 22)]
        ac = []
        for _ in range(40):
            rr = []
            for q in rng.choice(pool, size=min(len(v["r"]), len(pool)), replace=False):
                dist = float(rng.choice(v["dist"])); stop = d["o"][q + 1] - dist * d["atr"][q]
                s = sim(d, int(q), stop)
                if s and s[0] != "sem": rr.append(s[0])
            ac.append(rr)
        v["acaso"] = ac
    return out
if __name__ == "__main__":
    fich = sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")) + sorted(glob.glob("/tmp/claude-0/delist/*.csv.gz"))
    with mp.Pool(2) as pool:
        partes = [x for x in pool.map(moeda, fich) if x]
    print(f"H31 padroes de compra (mecha de liquidacao, base depois da queda) em {len(partes)} moedas")
    for var in VARS:
        ok, cel = True, []
        for per in (1, 2):
            r = [x for p in partes for x in p.get((var, per), {}).get("r", [])]
            r2 = [x for p in partes for x in p.get((var, per), {}).get("x2", [])]
            if len(r) < 5: cel.append(f"P{per} n={len(r)}"); ok = False; continue
            ms = []
            for rep in range(40):
                v = [y for p in partes for ac in [p.get((var, per), {}).get("acaso", [])] if rep < len(ac) for y in ac[rep]]
                ms.append(np.mean(v) if v else 0)
            mm = float(np.mean(r)); sd = float(np.std(ms)) or 1e-9; pv = 0.5 * math.erfc((mm - np.mean(ms)) / sd / math.sqrt(2))
            top = float(np.mean(sorted(r)[:max(1, int(len(r) * 0.95))])); md = float(np.mean(r2)); ac_ = 100 * np.mean(np.array(r) > 0)
            cel.append(f"P{per} n={len(r):>5} {mm:+.3f}R acerto {ac_:.0f}% (acaso {np.mean(ms):+.3f} p={pv:.4f}) s/top {top:+.3f} x2 {md:+.3f}")
            ok &= mm >= 0.15 and len(r) >= 50 and pv < 0.0125 and top > 0 and md > 0
        print(f" {var:<8} {' | '.join(cel)} -> {'PASSA -> PAPEL' if ok else 'chumba'}")
