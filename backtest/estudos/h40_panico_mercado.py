"""H40 (03/11->04/11): o pânico do mercado todo (BTC -3% em 6 velas de 4H, etiqueta "mercado" registada desde 01/11, H28) contra o pânico isolado, com custos de futuros e risco de 1% em todos os sinais. Hipótese registada antes (tipo_panico, 01/11)."""
import numpy as np
src=open("backtest/estudos/h38_custos_futuros.py").read().split('print("A) compra no panico com custos de futuros")')[0]
exec(src)
b=dados["BTC"]; bidx=b["idx"]
def tipo(ts):
    k=bidx.get(ts)
    if k is None or k<6: return None
    return "mercado" if b["c"][k]/b["c"][k-6]-1<=-0.03 else "isolado"
for filtro in ("todos","mercado","isolado"):
    for per in ("B1","B2"):
        ev=[c for c in cand if (c[4]<CUT)==(per=="B1") and (filtro=="todos" or tipo(c[4])==filtro)]
        Rs=[c[2] for c in ev]; eq=1.0;pk=1;dd=0;ab=[]
        for c in ev:
            for o in sorted([o for o in ab if o[0]<=c[0]]): eq+=o[1]; ab.remove(o); pk=max(pk,eq); dd=max(dd,1-eq/pk)
            ab.append((c[1],0.01*eq*c[2]))
        for o in ab: eq+=o[1]
        print(filtro,per,"ops",len(ev),"R %+.3f"%np.mean(Rs),"conta x%.2f queda %d%%"%(eq,100*dd))
