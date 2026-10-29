"""H22 (pre-registado 29/10, antes de correr). Extremos de financiamento (contrarian).
Dados: funding 8h da Binance desde ago/2024 (69 moedas) + velas 4H. So ha periodo B: divide-se em
B1 (ago/2024-set/2025) e B2 (out/2025-out/2026). LIMITACAO declarada: nao ha periodo 2021-24.
F1 short: funding >= percentil 95 dos 90 dias anteriores da moeda E subida >= 10% em 3 dias.
F2 compra: funding <= percentil 5 dos 90 dias anteriores E queda >= 10% em 3 dias.
Entrada na abertura da vela 4H seguinte; stop 2 ATR(42 velas 4H); alvo 2R; 3 dias; 1 posicao por moeda.
Custos 0,25%/lado + juro de emprestimo 20%/ano no short (margem spot, sem financiamento recebido).
Criterio fixo (k=2, Bonferroni): R liquido >= +0,15 em B1 e B2, >= 50 ops por metade, p < 0,025 contra
entradas ao acaso (mesma moeda, lado, saidas, metade; 300 repeticoes), sem as 5% melhores > 0 nas duas,
com custos a dobrar > 0 nas duas.
Extra (resposta ao Rui): short de BTC a 10x ao acaso: quantas vezes ganha 9,1% antes de subir 9,5% (liquidacao)."""
import gzip, glob, os, random, statistics as S, numpy as np
H4, DAY = 14400, 86400
CUT = 1759276800            # 2025-10-01
def load4(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])
def loadf(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/funding/{a}.csv.gz", "rt").read().split()]
    return np.array([[float(z[0]), float(z[1])] for z in r if len(z) >= 2])
def sim(d, i, lado, fee=0.0025):
    t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    if i + 1 >= n: return None
    e, atr = o[i + 1], d["atr"][i]
    if not atr or e <= 0: return None
    stop = e - lado * 2 * atr; risk = abs(e - stop); alvo = e + lado * 2 * risk
    px, j = None, None
    for j in range(i + 1, min(n, i + 19)):
        if (l[j] <= stop) if lado > 0 else (h[j] >= stop): px = stop; break
        if (h[j] >= alvo) if lado > 0 else (l[j] <= alvo): px = alvo; break
    if px is None: j = min(n - 1, i + 18); px = c[j]
    dias = (t[j] - t[i]) / DAY
    custo = 2 * fee * e + (0.20 * dias / 365 * e if lado < 0 else 0)
    return (lado * (px - e) - custo) / risk, j
res = {"F1": {"B1": [], "B2": []}, "F2": {"B1": [], "B2": []}}
alea = {"F1": {"B1": [], "B2": []}, "F2": {"B1": [], "B2": []}}
dob = {"F1": {"B1": [], "B2": []}, "F2": {"B1": [], "B2": []}}
cands = {}
for p in sorted(glob.glob("/tmp/claude-0/hist/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"/tmp/claude-0/hist/{a}.csv.gz"): continue
    x, f = load4(a), loadf(a)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    atr = np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)]
    d = dict(t=t, o=o, h=h, l=l, c=c, atr=atr)
    ft, fv = f[:, 0], f[:, 1]
    for nome, lado in (("F1", -1), ("F2", 1)):
        livre = -1; idxs = {"B1": [], "B2": []}
        for i in range(18, len(c) - 1):
            if t[i] < ft[0] + 90 * DAY or i <= livre: continue
            k = np.searchsorted(ft, t[i] + H4, side="right") - 1      # ultimo funding ja conhecido no fecho
            if k < 270: continue
            hist = fv[k - 270:k]                                      # 90 dias (3 por dia)
            r3 = c[i] / c[i - 18] - 1
            if nome == "F1" and not (fv[k] >= np.percentile(hist, 95) and fv[k] > 0 and r3 >= 0.10): continue
            if nome == "F2" and not (fv[k] <= np.percentile(hist, 5) and fv[k] < 0 and r3 <= -0.10): continue
            s = sim(d, i, lado)
            if not s: continue
            per = "B1" if t[i] < CUT else "B2"
            res[nome][per].append(s[0]); dob[nome][per].append(sim(d, i, lado, 0.005)[0]); idxs[per].append(i); livre = s[1]
        cands[(nome, a)] = (d, idxs)
rng = random.Random(11)
for nome, lado in (("F1", -1), ("F2", 1)):
    for per in ("B1", "B2"):
        ms = []
        for _ in range(300):
            v = []
            for (nm, a), (d, idxs) in cands.items():
                if nm != nome or not idxs[per]: continue
                t = d["t"]; lo, hi = (0, CUT) if per == "B1" else (CUT, 9e18)
                pool = np.nonzero((t >= max(lo, t[0] + 90 * DAY)) & (t < hi))[0]
                pool = pool[pool < len(t) - 2]
                for i in rng.sample(list(pool), min(len(idxs[per]), len(pool))):
                    s = sim(d, i, lado)
                    if s: v.append(s[0])
            ms.append(S.mean(v) if v else 0)
        alea[nome][per] = ms
print("H22 extremos de financiamento (R liquido por operacao)")
for nome in ("F1", "F2"):
    ok = True
    for per in ("B1", "B2"):
        r = res[nome][per]
        if not r: print(nome, per, "sem operacoes"); ok = False; continue
        m = S.mean(r); pv = sum(x >= m for x in alea[nome][per]) / len(alea[nome][per])
        top = sorted(r)[:max(1, int(len(r) * 0.95))]; md = S.mean(dob[nome][per])
        print(f"  {nome} {per}: n={len(r)} media {m:+.3f}R  acerto {100*sum(x>0 for x in r)/len(r):.0f}%  acaso {S.mean(alea[nome][per]):+.3f}R  p={pv:.3f}  sem top5% {S.mean(top):+.3f}  custos x2 {md:+.3f}")
        ok &= m >= 0.15 and len(r) >= 50 and pv < 0.025 and S.mean(top) > 0 and md > 0
    print(f"  {nome}: {'PASSA' if ok else 'CHUMBA'}")
# extra: BTC short 10x ao acaso
x = load4("BTC"); t, h, l, c = x[:, 0], x[:, 3 - 1], x[:, 3], x[:, 4]
win = lose = nada = 0
for i in range(0, len(c) - 181):
    e = c[i]
    for j in range(i + 1, i + 181):
        if x[j, 2] >= e * 1.095: lose += 1; break
        if x[j, 3] <= e * (1 - 0.091): win += 1; break
    else: nada += 1
N = win + lose + nada
print(f"BTC short 10x ao acaso (30 dias, 2021-26): +91% antes da liquidacao {100*win/N:.1f}%  liquidado {100*lose/N:.1f}%  nenhum {100*nada/N:.1f}%")
