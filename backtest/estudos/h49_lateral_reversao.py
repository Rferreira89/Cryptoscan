"""H49 (pre-registado 05/11 10:36, antes de correr). Rui: "agora e arranjar mais operacoes". Falta o regime LATERAL
(o atual: BTC perto da media de 50 dias, sem tendencia). Hipotese: sem tendencia do mercado, as quedas fortes e curtas
de uma altcoin revertem a media (vendedores esgotados, sem fluxo de tendencia a empurrar). Diferente da H46 (exige
subida da moeda e do BTC), da H34 (RSI2 sem filtro de regime) e da H40 (exige financiamento extremo e queda de 10%).
Sinal na vela de 4H fechada: BTC a menos de 4% da sua media de 300 velas de 4H (~50 dias) [regime lateral];
RSI(14) de 4H da moeda abaixo de L. Compra limite 1% abaixo (2 velas), stop 2xATR42, objetivo 2R, 72 h, custos de
futuros da OKX, risco 2%. Variantes (k=2): L=25 e L=20. Metades como a H46. Criterio: R medio > 0 e conta a crescer
nas DUAS metades; mede as semanas com operacao."""
import numpy as np, time
from collections import defaultdict
h32 = open("backtest/estudos/h32_uma_conta.py").read().split('print("H32 PANICO_L10')[0]
COND = "if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10 and d[\"atr\"][i]:"
assert COND in h32
h32 = h32.replace(COND, "if False:")                    # so os dados; os sinais sao feitos abaixo
h32 = h32.replace("if t[i] < ft[0] + 90 * DAY: continue", "continue")
exec(h32)
CUT2 = 1698796800
def sma(x, n):
    o = np.full(len(x), np.nan); cs = np.cumsum(np.r_[0, x]); o[n - 1:] = (cs[n:] - cs[:-n]) / n; return o
def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0); dn = np.where(d < 0, -d, 0)
    au = np.zeros(len(c)); ad = np.zeros(len(c)); au[n] = up[1:n + 1].mean(); ad[n] = dn[1:n + 1].mean()
    for i in range(n + 1, len(c)): au[i] = (au[i - 1] * (n - 1) + up[i]) / n; ad[i] = (ad[i - 1] * (n - 1) + dn[i]) / n
    r = 100 - 100 / (1 + au / np.maximum(ad, 1e-12)); r[:n + 1] = 50; return r
b = dados["BTC"]; bs = sma(b["c"], 300)
btc_ok = {int(b["t"][i]): (i >= 360 and abs(b["c"][i] / bs[i] - 1) < 0.04) for i in range(len(b["c"]))}
def trade_f(d, k0, e, i):
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]; n = len(c)
    stop = e - 2 * atr[i]; risk = e - stop; alvo = e + 2 * risk; px = None; fout = 0.0010
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, 0.0002; break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return ((px - e) - (0.0002 * e + fout * px)) / risk, j
for L in (25, 20):
    cand = []
    for a, d in dados.items():
        if a == "BTC": continue
        c = d["c"]; s = sma(c, 300); r = rsi(c); livre = -1
        for i in range(360, len(c) - 2):
            if i <= livre or not btc_ok.get(int(d["t"][i])): continue
            if not (r[i] < L and d["atr"][i]): continue
            lim = c[i] * 0.99
            for k in (i + 1, i + 2):
                if d["l"][k] <= lim:
                    e = min(lim, d["o"][k]); R, j = trade_f(d, k, e, i)
                    cand.append((int(d["t"][k]), int(d["t"][j]) + H4, R, int(d["t"][i]))); livre = j; break
    cand.sort()
    for nome, f in (("2021-23", lambda t: t < CUT2), ("2023-26", lambda t: t >= CUT2)):
        ev = [x for x in cand if f(x[3])]
        eq = 1.0; pk = 1; dd = 0; ab = []
        for x in ev:
            for o in sorted([o for o in ab if o[0] <= x[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
            ab.append((x[1], 0.02 * eq * x[2]))
        for o in ab: eq += o[1]
        Rs = [x[2] for x in ev]; sem = len({x[3] // (7 * DAY) for x in ev})
        tot = (max(x[3] for x in ev) - min(x[3] for x in ev)) / (7 * DAY) if ev else 1
        print(f"H49 lateral RSI<{L} {nome}: ops {len(ev)} R {np.mean(Rs):+.3f} acerto {100*np.mean([q>0 for q in Rs]):.0f}% conta x{eq:.2f} queda {100*dd:.0f}% semanas com op {sem}/{tot:.0f}", flush=True)
