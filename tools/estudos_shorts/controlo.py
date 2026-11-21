import numpy as np, json
from tools.estudos_shorts import laboratorio as L
D=L.carregar(); ctx=L.btc_ctx(D)
p=dict(ema=50,k=6,x=0.03)
rng=np.random.default_rng(11)
out={}
for sd in (dict(k=3.0,tp=1.5,hold=30),dict(k=3.0,tp=2.5,hold=30)):
    est=[];ctl=[]
    for b,S in D.items():
        s=L.f_sell_rally(S,p,ctx)
        est+=L.simular(S,b,s,sd)
        down=np.where(S['c']<S['e300'])[0]
        for rep in range(5):
            if len(down) and len(s):
                r=np.sort(rng.choice(down,size=min(len(s),len(down)),replace=False))
                ctl+=L.simular(S,b,r,sd)
    for nome,ops in (('estrategia',est),('acaso_em_queda',ctl)):
        for per,(a,z) in {'treino':(0,L.T_VAL),'validacao':(L.T_VAL,L.T_TEST),'teste':(L.T_TEST,9e9)}.items():
            out[f"{sd['tp']}|{nome}|{per}"]=L.resumo([x for x in ops if a<=x[0]<z])
for k,v in out.items(): print(k,v)
json.dump(out,open('controlo.json','w'))
