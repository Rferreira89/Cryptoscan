"""H42 (04/11): tamanho do risco por operacao no panico do mercado todo (H40), custos de futuros, todos os sinais. Informativo para a decisao do Rui ("forca o agente a lucrar muito")."""
import numpy as np
src=open("backtest/estudos/h38_custos_futuros.py").read().split('print("A) compra no panico com custos de futuros")')[0]
exec(src)
b=dados["BTC"]; bidx=b["idx"]
def tipo(ts):
    k=bidx.get(ts)
    if k is None or k<6: return None
    return "mercado" if b["c"][k]/b["c"][k-6]-1<=-0.03 else "isolado"
for risk in (0.01,0.02,0.03,0.05):
    linha=[]
    for per in ("B1","B2"):
        ev=[c for c in cand if (c[4]<CUT)==(per=="B1") and tipo(c[4])=="mercado"]
        eq=1.0;pk=1;dd=0;ab=[];mx=0
        for c in ev:
            for o in sorted([o for o in ab if o[0]<=c[0]]): eq+=o[1]; ab.remove(o); pk=max(pk,eq); dd=max(dd,1-eq/pk)
            ab.append((c[1],risk*eq*c[2],risk*eq/max(1e-9,0.083))); mx=max(mx,sum(o[2] for o in ab)/eq)
        for o in ab: eq+=o[1]
        linha.append("x%.2f queda %d%% expo max %.1fx"%(eq,100*dd,mx))
    print("risco %d%%:"%(risk*100)," | ".join(linha))
# quantas operacoes por semana e quantas ao mesmo tempo
ev=[c for c in cand if tipo(c[4])=="mercado"]
semanas=(max(c[0] for c in ev)-min(c[0] for c in ev))/604800
print("ops/semana %.1f"%(len(ev)/semanas))
