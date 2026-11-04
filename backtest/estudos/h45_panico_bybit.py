"""H45 (pre-registado 04/11 21:42, antes de correr). Rui: "precisamos de operacoes em dinheiro para lucrarmos".
A unica regra com prova (H40, panico do mercado) so opera com dinheiro real na OKX. Pergunta: com os custos da Bybit UE
(spot/margem, ~0,25% de comissao por lado + 0,10% de deslize no stop e na saida por tempo; ordem limite sem deslize),
a H40 ainda ganha? Se sim, a Bybit tambem pode operar o panico do mercado com dinheiro real (decisao do Rui: mexe no
config.json). Mesmas regras da H40; risco 2% (H42). Uma so variante (k=1). Criterio: R medio > 0 e conta a crescer
nas DUAS metades."""
import numpy as np
src = open("backtest/estudos/h38_custos_futuros.py").read().split('print("A) compra no panico com custos de futuros")')[0]
src = src.replace("fout = 0.0010", "fout = 0.0035").replace("px, fout = alvo, 0.0002", "px, fout = alvo, 0.0025")
src = src.replace("- 0.0002 - fout * px / e, ((px - e) - (0.0002 * e + fout * px)) / risk", "- 0.0025 - fout * px / e, ((px - e) - (0.0025 * e + fout * px)) / risk")
assert "0.0035" in src and "0.0025 * e" in src
exec(src)
b = dados["BTC"]; bidx = b["idx"]
def mercado(ts):
    k = bidx.get(ts); return k is not None and k >= 6 and b["c"][k] / b["c"][k - 6] - 1 <= -0.03
for per in ("B1", "B2"):
    ev = [c for c in cand if (c[4] < CUT) == (per == "B1") and mercado(c[4])]
    eq = 1.0; pk = 1; dd = 0; ab = []
    for c in ev:
        for o in sorted([o for o in ab if o[0] <= c[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
        ab.append((c[1], 0.02 * eq * c[2]))
    for o in ab: eq += o[1]
    Rs = [c[2] for c in ev]
    print(f"H45 Bybit {per}: ops {len(ev)} R {np.mean(Rs):+.3f} acerto {100*np.mean([r>0 for r in Rs]):.0f}% conta x{eq:.2f} queda {100*dd:.0f}%")
