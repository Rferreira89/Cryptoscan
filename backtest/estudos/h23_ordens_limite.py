"""H23 (pre-registado 29/10, antes de correr). F2 (compra no panico: funding <= p5 de 90 dias e -10% em
3 dias) com execucao mais barata. Mesmos dados e metades do H22 (B1 ago/2024-set/2025, B2 out/2025-out/2026).
Execucao:
  M  (referencia, igual ao H22): compra a mercado na abertura seguinte, 0,25%/lado.
  L05 ordem limite 0,5% abaixo do fecho do sinal, valida 2 velas (8 h); se nao executar, nao ha operacao.
  L10 igual, 1,0% abaixo.
  Nas L: entrada com 0,10% (comissao maker, sem spread nem deslize); objetivo 2R como limite (0,10%);
  stop 2 ATR a mercado (0,25%); saida por tempo a mercado (0,25%). Stop e alvo contados a partir do preco executado.
Acaso: mesmas regras de execucao em momentos ao acaso (mesma moeda e metade, 300 repeticoes).
Criterio fixo (k=2 variantes novas, Bonferroni): >= +0,15R em B1 e B2, >= 50 ops por metade, p < 0,025,
sem as 5% melhores > 0, custos a dobrar > 0. Uma variante que passe vai para PAPEL, nunca dinheiro real."""
import gzip, glob, os, random, statistics as S, numpy as np
H4, DAY, CUT = 14400, 86400, 1759276800
def load4(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
def loadf(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/funding/{a}.csv.gz", "rt").read().split()]
    return np.array([[float(z[0]), float(z[1])] for z in r if len(z) >= 2])
def sim(d, i, modo, mult=1.0):
    t, o, h, l, c, atr = d["t"], d["o"], d["h"], d["l"], d["c"], d["atr"]
    n = len(c)
    if i + 2 >= n or not atr[i]: return None
    if modo == "M":
        k0, e, fin = i + 1, o[i + 1], 0.0025
    else:
        lim = c[i] * (1 - (0.005 if modo == "L05" else 0.010))
        k0 = next((k for k in (i + 1, i + 2) if k < n and l[k] <= lim), None)
        if k0 is None: return ("sem", None)
        e, fin = min(lim, o[k0]), 0.0010
    stop = e - 2 * atr[i]; risk = e - stop
    if risk <= 0: return None
    alvo = e + 2 * risk; px = None; fout = 0.0025
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or modo == "M" or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, (0.0010 if modo != "M" else 0.0025); break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return ((px - e) - mult * (fin * e + fout * px)) / risk, j
modos = ("M", "L05", "L10")
res = {m: {"B1": [], "B2": []} for m in modos}; dob = {m: {"B1": [], "B2": []} for m in modos}
fills = {m: [0, 0] for m in modos}; cands = []
for p in sorted(glob.glob("/tmp/claude-0/hist/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"/tmp/claude-0/hist/{a}.csv.gz"): continue
    x, f = load4(a), loadf(a)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    d = dict(t=t, o=o, h=h, l=l, c=c, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)])
    ft, fv = f[:, 0], f[:, 1]
    sinais = []
    for i in range(18, len(c) - 2):
        if t[i] < ft[0] + 90 * DAY: continue
        k = np.searchsorted(ft, t[i] + H4, side="right") - 1
        if k < 270: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10:
            sinais.append(i)
    for m in modos:
        livre = -1
        for i in sinais:
            if i <= livre: continue
            s = sim(d, i, m)
            if not s: continue
            fills[m][1] += 1
            if s[0] == "sem": continue
            fills[m][0] += 1
            per = "B1" if t[i] < CUT else "B2"
            res[m][per].append(s[0]); dob[m][per].append(sim(d, i, m, 2.0)[0]); livre = s[1]
    cands.append((d, [i for i in sinais]))
rng = random.Random(23)
print("H23 compra no panico com execucao mais barata (R liquido por operacao)")
for m in modos:
    ok = m != "M"
    print(f" {m}: ordens executadas {fills[m][0]}/{fills[m][1]}")
    for per in ("B1", "B2"):
        r = res[m][per]
        ms = []
        for _ in range(300):
            v = []
            for d, sn in cands:
                t = d["t"]; nsn = sum(1 for i in sn if (t[i] < CUT) == (per == "B1"))
                if not nsn: continue
                pool = np.nonzero(((t < CUT) if per == "B1" else (t >= CUT)) & (t >= t[0] + 90 * DAY))[0]
                pool = pool[(pool > 18) & (pool < len(t) - 3)]
                for i in rng.sample(list(pool), min(nsn, len(pool))):
                    s = sim(d, i, m)
                    if s and s[0] != "sem": v.append(s[0])
            ms.append(S.mean(v) if v else 0)
        mm = S.mean(r); pv = sum(x >= mm for x in ms) / len(ms)
        top = S.mean(sorted(r)[:max(1, int(len(r) * 0.95))]); md = S.mean(dob[m][per])
        print(f"   {per}: n={len(r)} media {mm:+.3f}R acerto {100*sum(x>0 for x in r)/len(r):.0f}% acaso {S.mean(ms):+.3f}R p={pv:.3f} sem top5% {top:+.3f} custos x2 {md:+.3f}")
        ok &= mm >= 0.15 and len(r) >= 50 and pv < 0.025 and top > 0 and md > 0
    if m != "M": print(f"   {m}: {'PASSA -> PAPEL' if ok else 'CHUMBA'}")
