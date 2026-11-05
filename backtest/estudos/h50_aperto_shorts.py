"""H50 (pre-registado 05/11 10:40, antes de correr). Mais operacoes fora do panico. Hipotese "aperto dos shorts":
quando o financiamento de uma moeda fica extremo NEGATIVO (shorts amontoados a pagar) mas o preco NAO esta a cair
(3 dias >= 0%), os shorts estao errados e uma subida obriga-os a fechar (compra forcada). Diferente da H40 (exige
queda de 10%: e capitulacao, nao aperto) e da H44 (o contrario: longs amontoados).
Sinal (4H fechada): financiamento < 0 e <= p5 dos 270 anteriores E fecho >= fecho de 18 velas antes. Sem filtro de
mercado (V1) ou so com o BTC acima da media de 300 velas de 4H (V2). Entrada, saidas e custos como a H40 (OKX), risco
2%. k=2. Criterio: R medio > 0 e conta a crescer nas DUAS metades (dados de financiamento so desde finais de 2024)."""
import numpy as np
base = open("backtest/estudos/h38_custos_futuros.py").read().split('print("A) compra no panico com custos de futuros")')[0]
COND = "if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10 and d[\"atr\"][i]:"
NOVA = "if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 >= 0 and d[\"atr\"][i]:"
h32 = open("backtest/estudos/h32_uma_conta.py").read(); assert COND in h32
src = base.replace('src = open("backtest/estudos/h32_uma_conta.py").read().split(\'print("H32 PANICO_L10\')[0]',
                   'src = H32.split(\'print("H32 PANICO_L10\')[0].replace(COND, NOVA)')
ns = dict(H32=h32, COND=COND, NOVA=NOVA, __name__="h50"); exec(src, ns)
cand, dados, CUT, DAY = ns["cand"], ns["dados"], ns["CUT"], ns["DAY"]
b = dados["BTC"]; c = b["c"]; s = np.full(len(c), np.nan); cs = np.cumsum(np.r_[0, c]); s[299:] = (cs[300:] - cs[:-300]) / 300
acima = {int(b["t"][i]): bool(c[i] > s[i]) for i in range(300, len(c))}
for nome, f in (("V1 todos", lambda t: True), ("V2 BTC acima da media", lambda t: acima.get(t, False))):
    for per in ("B1", "B2"):
        ev = [x for x in cand if (x[4] < CUT) == (per == "B1") and f(x[4])]
        if not ev: print(nome, per, "sem operacoes"); continue
        eq = 1.0; pk = 1; dd = 0; ab = []
        for x in ev:
            for o in sorted([o for o in ab if o[0] <= x[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
            ab.append((x[1], 0.02 * eq * x[2]))
        for o in ab: eq += o[1]
        Rs = [x[2] for x in ev]; sem = len({x[4] // (7 * DAY) for x in ev})
        print(f"H50 {nome} {per}: ops {len(ev)} R {np.mean(Rs):+.3f} acerto {100*np.mean([q>0 for q in Rs]):.0f}% conta x{eq:.2f} queda {100*dd:.0f}% semanas com op {sem}", flush=True)
