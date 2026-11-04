"""H44 (pre-registado 04/11 21:00, antes de correr). Missao 1M do Rui: oportunidades em todos os regimes, longs E shorts.
Espelho da H40 (a unica com prova): quando os longs alavancados se amontoam numa moeda que disparou, o financiamento
fica extremo POSITIVO; a hipotese e que o excesso se desfaz (liquidacoes de longs) e o preco recua.
Sinal (vela de 4H fechada): financiamento > 0 e >= p95 dos 270 anteriores E subida de 3 dias >= +10%.
Short: ordem limite 1% ACIMA do fecho, valida 2 velas; stop 2xATR42 acima; objetivo 2R abaixo; saida as 72 h.
Custos de futuros (H38): limite 0,02%, stop/tempo 0,05% + 0,05% deslize. Financiamento nao incluido (a favor do short
na entrada, porque e positivo). Conta com risco 2% por operacao, sinais sobrepostos permitidos (como a H42).
Variantes (k=3): V1 todos; V2 so com o BTC +3% em 6 velas (euforia do mercado); V3 so sem essa euforia (isolado).
Criterio fixo: nas DUAS metades R medio > 0 E conta a crescer. Se passar: papel ao vivo na OKX ao lado da H40
(dinheiro real so depois de 30 operacoes em papel com media positiva, como diz a AUTORIZACAO PREVIA)."""
import numpy as np
from collections import defaultdict
h32 = open("backtest/estudos/h32_uma_conta.py").read().split('print("H32 PANICO_L10')[0]
COND = "if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10 and d[\"atr\"][i]:"
assert COND in h32
NOVA = "if fv[k] >= np.percentile(fv[k - 270:k], 95) and fv[k] > 0 and c[i] / c[i - 18] - 1 >= 0.10 and d[\"atr\"][i]:"
exec(h32.replace(COND, NOVA))
def fill_s(a, i, k):
    d = dados[a]; lim = d["c"][i] * 1.01
    if k < len(d["c"]) and d["h"][k] >= lim: return max(lim, d["o"][k])
    return None
def trade_s(d, k0, e, i):
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]; n = len(c)
    stop = e + 2 * atr[i]; risk = stop - e; alvo = e - 2 * risk; px = None; fout = 0.0010
    for j in range(k0, min(n, k0 + 18)):
        if h[j] >= stop and (j > k0 or o[j] < stop): px = stop; break
        if l[j] <= alvo: px, fout = alvo, 0.0002; break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return ((e - px) - (0.0002 * e + fout * px)) / risk, j
por = defaultdict(list)
for ts, a, i in sinais: por[a].append((ts, i))
cand = []
for a, L in por.items():
    livre = -1
    for ts, i in L:
        if i <= livre: continue
        for k in (i + 1, i + 2):
            e = fill_s(a, i, k)
            if e:
                R, j = trade_s(dados[a], k, e, i); cand.append((int(dados[a]["t"][k]), int(dados[a]["t"][j]) + H4, R, ts)); livre = j; break
cand.sort()
b = dados["BTC"]; bidx = b["idx"]
def euforia(ts):
    k = bidx.get(ts)
    return None if k is None or k < 6 else bool(b["c"][k] / b["c"][k - 6] - 1 >= 0.03)
print(f"{len(sinais)} sinais, {len(cand)} operacoes executadas")
for nome, f in (("V1 todos", lambda t: True), ("V2 euforia BTC", lambda t: euforia(t) is True), ("V3 isolado", lambda t: euforia(t) is False)):
    for per in ("B1", "B2"):
        ev = [c for c in cand if (c[3] < CUT) == (per == "B1") and f(c[3])]
        if not ev: print(nome, per, "sem operacoes"); continue
        eq = 1.0; pk = 1; dd = 0; ab = []
        for c in ev:
            for o in sorted([o for o in ab if o[0] <= c[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
            ab.append((c[1], 0.02 * eq * c[2]))
        for o in ab: eq += o[1]
        Rs = [c[2] for c in ev]
        print(f"{nome} {per}: ops {len(ev)} R {np.mean(Rs):+.3f} acerto {100*np.mean([r>0 for r in Rs]):.0f}% conta x{eq:.2f} queda {100*dd:.0f}%", flush=True)
