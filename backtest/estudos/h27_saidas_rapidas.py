"""H27 (pre-registado 31/10, pedido do Rui: "trades mais curtas, rapidas"). Compra no panico L10 (H23) com
a mesma entrada e saidas mais rapidas. Variantes (k=6 novas, Bonferroni p<0,0083):
  T6/T12   saida por tempo em 6 velas (1 dia) ou 12 (2 dias), stop 2 ATR, objetivo 2R
  T6-1R / T12-1R  o mesmo com objetivo 1R (sai mais cedo com ganho)
  T6-1A / T12-1A  stop 1 ATR e objetivo 2R (operacao mais curta e apertada)
Referencia: H23 L10 (18 velas, 2 ATR, 2R) +0,08R/+0,08R. Mesmos dados e metades (B1/B2), custos iguais.
Criterio unico: >= +0,15R nas duas metades, >= 50 ops, p < 0,0083 contra o acaso, sem top 5% > 0, custos x2 > 0.
Nota honesta: o retorno por DIA conta (capital livre mais cedo), por isso mostra-se tambem R por dia de exposicao."""
import gzip, glob, os, random, math, statistics as S, numpy as np
src = open(os.path.join(os.path.dirname(__file__), "h23_ordens_limite.py")).read().split("def sim(")[0]
exec(src)
def sim(d, i, hold, alvo_r, stop_atr, mult=1.0, k0=None, e=None):
    t, o, h, l, c, atr = d["t"], d["o"], d["h"], d["l"], d["c"], d["atr"]
    n = len(c)
    if i + 2 >= n or not atr[i]: return None
    if k0 is None:
        lim = c[i] * 0.99
        k0 = next((k for k in (i + 1, i + 2) if k < n and l[k] <= lim), None)
        if k0 is None: return ("sem", None, 0)
        e, fin = min(lim, o[k0]), 0.0010
    else:
        fin = 0.0025
    stop = e - stop_atr * atr[i]; risk = e - stop
    if risk <= 0: return None
    alvo = e + alvo_r * risk; px = None; fout = 0.0025
    for j in range(k0, min(n, k0 + hold)):
        if l[j] <= stop and (j > k0 or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, 0.0010; break
    if px is None: j = min(n - 1, k0 + hold - 1); px = c[j]
    return ((px - e) - mult * (fin * e + fout * px)) / risk, j, (j - k0 + 1)
VAR = {"REF18": (18, 2, 2), "T6": (6, 2, 2), "T12": (12, 2, 2), "T6-1R": (6, 1, 2), "T12-1R": (12, 1, 2),
       "T6-1A": (6, 2, 1), "T12-1A": (12, 2, 1)}
res = {v: {"B1": [], "B2": []} for v in VAR}; dob = {v: {"B1": [], "B2": []} for v in VAR}; barras = {v: [] for v in VAR}
cands = []
for p in sorted(glob.glob("/tmp/claude-0/hist/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"/tmp/claude-0/hist/{a}.csv.gz"): continue
    x, f = load4(a), loadf(a)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    d = dict(t=t, o=o, h=h, l=l, c=c, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)])
    ft, fv = f[:, 0], f[:, 1]; sinais = []
    for i in range(18, len(c) - 2):
        if t[i] < ft[0] + 90 * DAY: continue
        k = np.searchsorted(ft, t[i] + H4, side="right") - 1
        if k < 270: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10:
            sinais.append(i)
    for v, (hold, ar, sa) in VAR.items():
        livre = -1
        for i in sinais:
            if i <= livre: continue
            s = sim(d, i, hold, ar, sa)
            if not s or s[0] == "sem": continue
            per = "B1" if t[i] < CUT else "B2"
            res[v][per].append(s[0]); dob[v][per].append(sim(d, i, hold, ar, sa, 2.0)[0]); barras[v].append(s[2]); livre = s[1]
    cands.append((d, sinais))
rng = random.Random(27)
print("H27 compra no panico com saidas rapidas (R liquido por operacao)")
for v, (hold, ar, sa) in VAR.items():
    ok = v != "REF18"; cel = []
    for per in ("B1", "B2"):
        r = res[v][per]; ms = []
        for _ in range(100):
            vv = []
            for d, sn in cands:
                t = d["t"]; nsn = sum(1 for i in sn if (t[i] < CUT) == (per == "B1"))
                if not nsn: continue
                pool = np.nonzero(((t < CUT) if per == "B1" else (t >= CUT)) & (t >= t[0] + 90 * DAY))[0]
                pool = pool[(pool > 18) & (pool < len(t) - 3)]
                for i in rng.sample(list(pool), min(nsn, len(pool))):
                    s = sim(d, i, hold, ar, sa)
                    if s and s[0] != "sem": vv.append(s[0])
            ms.append(S.mean(vv) if vv else 0)
        mm = S.mean(r); sd = S.pstdev(ms) or 1e-9; pv = 0.5 * math.erfc((mm - S.mean(ms)) / sd / math.sqrt(2))
        top = S.mean(sorted(r)[:max(1, int(len(r) * 0.95))]); md = S.mean(dob[v][per])
        cel.append(f"{per} n={len(r)} {mm:+.3f}R acaso {S.mean(ms):+.3f} p={pv:.4f} s/top {top:+.3f} x2 {md:+.3f}")
        ok &= mm >= 0.15 and len(r) >= 50 and pv < 0.0083 and top > 0 and md > 0
    allr = res[v]["B1"] + res[v]["B2"]
    dias = S.mean(barras[v]) * 4 / 24
    print(f" {v:<7} {' | '.join(cel)} | duracao media {dias:.1f} dias, {S.mean(allr)/dias:+.3f}R por dia -> {'PASSA' if ok else ('referência' if v == 'REF18' else 'chumba')}")
