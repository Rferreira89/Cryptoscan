"""H38 (pre-registado 03/11, antes de correr). Pergunta do Rui: uma corretora com futuros (Kraken Pro / OKX, MiFID,
comissoes 0,02% maker / 0,05% taker) traria mais lucro? Mesmas regras ja testadas, so com custos de futuros.
Custos: entrada limite e alvo 0,02%; stop e saida por tempo 0,05% + 0,05% de deslize. Financiamento (funding)
nao incluido (na compra no panico o funding e negativo na entrada, logo a favor; nas tendencias e contra: cerca
de 10%/ano estimado quando comprado - reportado a parte).
A) Compra no panico (H23 L10), todos os sinais, risco 1% e 2% por operacao, e 1 posicao com o valor todo.
B) Tendencia BTC com medias curtas (20, 30, 50 dias), 1x e 2x, custo 0,10%/lado e menos 10%/ano de funding.
Criterio: conta a crescer nas DUAS metades (o mesmo da conta). So informa: nada muda sem novo teste ao vivo."""
import numpy as np
from collections import defaultdict
src = open("backtest/estudos/h32_uma_conta.py").read().split('print("H32 PANICO_L10')[0]
exec(src)
def trade_f(d, k0, e, i):
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]; n = len(c)
    stop = e - 2 * atr[i]; risk = e - stop; alvo = e + 2 * risk; px = None; fout = 0.0010
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, 0.0002; break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    return px / e - 1 - 0.0002 - fout * px / e, ((px - e) - (0.0002 * e + fout * px)) / risk, j
por = defaultdict(list)
for ts, a, i in sinais: por[a].append((ts, i))
cand = []
for a, L in por.items():
    livre = -1
    for ts, i in L:
        if i <= livre: continue
        for k in (i + 1, i + 2):
            e = fill(a, i, k)
            if e:
                r, R, j = trade_f(dados[a], k, e, i); cand.append((int(dados[a]["t"][k]), int(dados[a]["t"][j]) + H4, R, r, ts)); livre = j; break
cand.sort()
print("A) compra no panico com custos de futuros")
for per in ("B1", "B2"):
    ev = [c for c in cand if (c[4] < CUT) == (per == "B1")]
    Rs = [c[2] for c in ev]
    for risk in (0.01, 0.02):
        eq = 1.0; pk = 1; dd = 0; ab = []
        for c in ev:
            for o in sorted([o for o in ab if o[0] <= c[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
            ab.append((c[1], risk * eq * c[2]))
        for o in ab: eq += o[1]
        print(f"   {per} todos os sinais risco {int(risk*100)}%: ops {len(ev)} R medio {np.mean(Rs):+.3f} conta x{eq:.2f} queda {100*dd:.0f}%")
    # uma posicao, valor todo, 1x: primeira a chegar quando livre
    eq = 1.0; livre = 0; n = 0
    for c in ev:
        if c[0] < livre: continue
        eq *= 1 + c[3]; livre = c[1]; n += 1
    print(f"   {per} uma posicao, valor todo 1x: ops {n} conta x{eq:.2f}")
print("B) tendencia BTC curta com custos de futuros (0,10%/lado) e funding -10%/ano quando comprado")
exec(open("backtest/estudos/h33_conta_tendencia.py").read().split("rng = random.Random(33)")[0].replace("CUSTO = 0.0035", "CUSTO = 0.0010"))
c = C["BTC"]
for n_ in (20, 30, 50):
    p = [None] * 210 + ["BTC" if c[i] > sma(c, n_, i) else None for i in range(210, N)]
    linha = []
    for per in (H1, H2):
        for L in (1, 2):
            m, a, d, tr = conta(p, per, L)
            dentro = sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1] and p[i]) / max(1, sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1]))
            a_f = a - 0.10 * L * dentro
            linha.append(f"{L}x {100*a_f:+.0f}%/ano q{100*d:.0f}%")
    print(f"   media {n_}: H1 " + " ".join(linha[:2]) + " | H2 " + " ".join(linha[2:]))
