"""H46 (pre-registado 04/11 23:12, antes de correr). Rui: "temos de ter trades todas as semanas". Falta uma estrategia
LONG para mercado a SUBIR (a H40 so opera em panico). Hipotese: numa altcoin em tendencia de subida, com o mercado
(BTC) tambem a subir, um recuo curto de sobrevenda e comprado pelos que perderam a subida (continuacao da tendencia).
Diferente da H37 (recuos do BTC), H34 (RSI2 sem filtro de tendencia da moeda e do mercado) e das quebras (H41/TURTLE).
Universo: as 69 moedas com velas de 4H do ramo history (2021-2026). Sinal na vela de 4H fechada:
  BTC acima da sua media de 300 velas de 4H (~50 dias) e essa media a subir face a 60 velas antes;
  a moeda acima da sua media de 300 velas e essa media a subir; RSI(14) de 4H da moeda abaixo de L.
Entrada: limite 1% abaixo do fecho, valida 2 velas; stop 2xATR42; objetivo 2R; saida as 72 h; uma posicao por moeda.
Custos de futuros da OKX (H38). Conta com risco 2% por operacao. Variantes (k=2): L=30 e L=35.
Metades: 2021-01..2023-10 e 2023-11..2026. Criterio: R medio > 0 e conta a crescer nas DUAS metades, e mede quantas
semanas tem pelo menos uma operacao."""
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
btc_ok = {int(b["t"][i]): (b["c"][i] > bs[i] and i >= 360 and bs[i] > bs[i - 60]) for i in range(len(b["c"]))}
def trade_f(d, k0, e, i):
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]; n = len(c)
    stop = e - 2 * atr[i]; risk = e - stop; alvo = e + 2 * risk; px = None; fout = 0.0010
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, 0.0002; break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return ((px - e) - (0.0002 * e + fout * px)) / risk, j
for L in (30, 35):
    cand = []
    for a, d in dados.items():
        if a == "BTC": continue
        c = d["c"]; s = sma(c, 300); r = rsi(c); livre = -1
        for i in range(360, len(c) - 2):
            if i <= livre or not btc_ok.get(int(d["t"][i])): continue
            if not (c[i] > s[i] and s[i] > s[i - 60] and r[i] < L and d["atr"][i]): continue
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
        print(f"H46 RSI<{L} {nome}: ops {len(ev)} R {np.mean(Rs):+.3f} acerto {100*np.mean([q>0 for q in Rs]):.0f}% conta x{eq:.2f} queda {100*dd:.0f}% semanas com op {sem}/{tot:.0f}", flush=True)
