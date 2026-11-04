"""H43 (pre-registado 04/11 17:58, antes de correr). Pedido do Rui: "um agente sempre em busca das melhores operacoes...
faz de tudo para obtermos lucros". Pergunta: da para ter MAIS operacoes do panico do mercado (H40) sem perder a vantagem?
Base H40: BTC -3% em 6 velas de 4H + financiamento negativo e <= p5 de 270 + queda de 3 dias <= -10%. Custos de futuros
(H38), ordem limite 1% abaixo valida 2 velas, stop 2xATR42, objetivo 2R, 72 h. Conta com risco de 2% por operacao (H42).
Variantes (k=3, decididas antes):
  V1 sem a condicao do financiamento (so queda de 10% + BTC -3%)
  V2 queda de 3 dias <= -7% (em vez de -10%), financiamento p5
  V3 financiamento <= p10 (em vez de p5), queda -10%
Criterio fixo: nas DUAS metades, R medio > 0, conta a crescer, E conta final MAIOR do que a da H40 com o mesmo risco.
Se passar: muda o agente da OKX (o Rui ja autorizou dinheiro real nesta familia). Se nao: fica tudo como esta."""
import numpy as np
from collections import defaultdict
base = open("backtest/estudos/h38_custos_futuros.py").read().split('print("A) compra no panico com custos de futuros")')[0]
COND = "if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10 and d[\"atr\"][i]:"
VAR = {"H40": COND,
       "V1": "if c[i] / c[i - 18] - 1 <= -0.10 and d[\"atr\"][i]:",
       "V2": COND.replace("<= -0.10", "<= -0.07"),
       "V3": COND.replace(", 5)", ", 10)")}
h32 = open("backtest/estudos/h32_uma_conta.py").read()
assert COND in h32
for nome, cond in VAR.items():
    ns = {}
    src = base.replace('src = open("backtest/estudos/h32_uma_conta.py").read().split(\'print("H32 PANICO_L10\')[0]',
                       'src = H32.split(\'print("H32 PANICO_L10\')[0].replace(COND, NOVA)')
    ns.update(H32=h32, COND=COND, NOVA=cond, __name__="h43")
    exec(src, ns)
    cand, dados = ns["cand"], ns["dados"]; CUT = ns["CUT"]
    b = dados["BTC"]; bidx = b["idx"]
    def mercado(ts):
        k = bidx.get(ts)
        return k is not None and k >= 6 and b["c"][k] / b["c"][k - 6] - 1 <= -0.03
    for per in ("B1", "B2"):
        ev = [c for c in cand if (c[4] < CUT) == (per == "B1") and mercado(c[4])]
        eq = 1.0; pk = 1; dd = 0; ab = []
        for c in ev:
            for o in sorted([o for o in ab if o[0] <= c[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
            ab.append((c[1], 0.02 * eq * c[2]))
        for o in ab: eq += o[1]
        print(f"{nome} {per} ops {len(ev)} R {np.mean([c[2] for c in ev]):+.3f} conta x{eq:.2f} queda {100*dd:.0f}%", flush=True)
