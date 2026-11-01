"""H32b (exploratorio, 01/11): verificacao do H32 - replica por moeda, posicao na vaga, regra 1a da moeda + vaga, posicoes 2 e 4, risco fixo. Corre a partir da raiz do repositorio."""
import sys, numpy as np, random
sys.argv=["x"]
src=open("backtest/estudos/h32_uma_conta.py").read().split('print("H32 PANICO_L10')[0]
exec(src)
# H23 replica: por moeda, sem sobrepor
from collections import defaultdict
por=defaultdict(list)
for ts,a,i in sinais: por[a].append((ts,i))
res={"B1":[],"B2":[]}; rets={"B1":[],"B2":[]}; tsl={"B1":[],"B2":[]}
for a,L in por.items():
    livre=-1
    for ts,i in L:
        if i<=livre: continue
        for k in (i+1,i+2):
            e=fill(a,i,k)
            if e:
                r,R,j=trade(dados[a],k,e,i,0.001); per="B1" if ts<CUT else "B2"
                res[per].append(R); rets[per].append(r); tsl[per].append(ts); livre=j; break
for p in res:
    print(p,len(res[p]),round(np.mean(res[p]),3),"ret preco medio %",round(100*np.mean(rets[p]),2), "stop medio % ~")
# how clustered: number of signals within same 4H bar
from collections import Counter
c=Counter(ts for ts,_,_ in sinais); print("barras com sinal",len(c),"media sinais por barra",round(np.mean(list(c.values())),2), "max",max(c.values()))
# R by order within cluster: first signal of a wave (no signal in previous 24h) vs later
allts=sorted(c)
import bisect
tsall=sorted(ts for ts,_,_ in sinais)
def antes(ts,h): return bisect.bisect_left(tsall,ts)-bisect.bisect_left(tsall,ts-h*3600)
def mesmo(ts): return c[ts]
rows=[]
for a,L in por.items():
    livre=-1
    for ts,i in L:
        if i<=livre: continue
        for k in (i+1,i+2):
            e=fill(a,i,k)
            if e:
                r,R,j=trade(dados[a],k,e,i,0.001); rows.append((ts,R,antes(ts,72),mesmo(ts))); livre=j; break
for nm,f in [("1a vaga (0 sinais nas 72h antes)",lambda x:x[2]==0),("1-10 antes",lambda x:1<=x[2]<=10),("11-40",lambda x:11<=x[2]<=40),(">40",lambda x:x[2]>40)]:
    for p in ("B1","B2"):
        v=[x[1] for x in rows if f(x) and ((x[0]<CUT)==(p=="B1"))]
        print(nm,p,len(v),round(np.mean(v),3) if v else None)
pcset={(x[0]) for x in rows}
pc_keys=set()
for a,L in por.items():
    livre=-1
    for ts,i in L:
        if i<=livre: continue
        for k in (i+1,i+2):
            e=fill(a,i,k)
            if e:
                r,R,j=trade(dados[a],k,e,i,0.001); pc_keys.add((a,ts)); livre=j; break
# rerun A recording asset
import types
def polA(rng):
    out=[];livre_t=0
    porT={}
    for sg in sinais:
        for s_ in (1,2): porT.setdefault(sg[0]+H4*s_,[]).append(sg)
    ordem=None
    for T in sorted(porT):
        if T<livre_t: continue
        cand=porT[T]
        if ordem not in cand: ordem=rng.choice(cand)
        ts,a,i=ordem; k=dados[a]["idx"].get(T); e=fill(a,i,k) if k is not None else None
        if e:
            r,R,j=trade(dados[a],k,e,i,0.001); out.append((ts,a,R,antes(ts,72),r)); livre_t=dados[a]["t"][j]+H4; ordem=None
    return out
o=polA(random.Random(32))
for p in ("B1","B2"):
    v=[x for x in o if (x[0]<CUT)==(p=="B1")]
    ins=[x[2] for x in v if (x[1],x[0]) in pc_keys]; out_=[x[2] for x in v if (x[1],x[0]) not in pc_keys]
    print(p,"em comum",len(ins),round(np.mean(ins),3),"so na conta",len(out_),round(np.mean(out_),3) if out_ else None,
          "1a vaga",sum(1 for x in v if x[3]==0), "ret medio %",round(100*np.mean([x[4] for x in v]),2))
print("----- H32b")
ult_coin={}
primeiro=set()
for ts,a,i in sinais:
    if ts-ult_coin.get(a,-10**12) > 72*3600: primeiro.add((a,ts))
    ult_coin[a]=ts
def ok(sg,regra):
    ts,a,i=sg
    if regra=="base": return True
    return (a,ts) in primeiro and antes(ts,72)>0
def pol(rng,modo,regra):
    out=[];livre_t=0;porT={}
    for sg in sinais:
        if not ok(sg,regra): continue
        for s_ in (1,2): porT.setdefault(sg[0]+H4*s_,[]).append(sg)
    ordem=None
    for T in sorted(porT):
        if T<livre_t: continue
        cand=porT[T]
        if modo=="A":
            if ordem not in cand: ordem=rng.choice(cand)
            lst=[ordem]
        else: lst=cand
        toc=[]
        for ts,a,i in lst:
            k=dados[a]["idx"].get(T); e=fill(a,i,k) if k is not None else None
            if e: toc.append((ts,a,i,k,e))
        if toc:
            ts,a,i,k,e=rng.choice(toc); r,R,j=trade(dados[a],k,e,i,0.001)
            stp=2*dados[a]["atr"][i]/e
            out.append((ts,r,R,stp)); livre_t=dados[a]["t"][j]+H4; ordem=None
    return out
def grow(ops,how):
    m=1;pk=1;dd=0
    for _,r,R,stp in ops:
        if how=="1x": g=r
        elif how=="3x": g=3*r
        else: g=min(how/stp,3)*r   # risco how por operacao, ate 3x
        m*=max(0,1+g);pk=max(pk,m);dd=max(dd,1-m/pk)
    return m,dd
for regra in ("base","1a da moeda + vaga"):
  for modo in ("A","B"):
    for p in ("B1","B2"):
        N=[];RR=[];G={h:[] for h in ("1x","3x",0.02,0.05)};D={h:[] for h in G}
        for s in range(40):
            v=[x for x in pol(random.Random(100+s),modo,regra) if (x[0]<CUT)==(p=="B1")]
            N.append(len(v));RR.append(np.mean([x[2] for x in v]))
            for h in G: m,d=grow(v,h);G[h].append(m);D[h].append(d)
        print(regra,modo,p,"ops",int(np.mean(N)),"R",round(np.mean(RR),3),
              " | ".join(f"{h if isinstance(h,str) else 'risco '+str(int(h*100))+'%'}: x{np.median(G[h]):.2f} dd{100*np.median(D[h]):.0f}%" for h in G))
st=[2*dados[a]["atr"][i]/dados[a]["c"][i] for _,a,i in sinais]; print("stop medio %",round(100*np.median(st),1))
print("----- slots")
def slots(rng,K,regra):
    porT={}
    for sg in sinais:
        if not ok(sg,regra): continue
        for s_ in (1,2): porT.setdefault(sg[0]+H4*s_,[]).append(sg)
    livres=[0]*K; out=[]; usados=set()
    for T in sorted(porT):
        toc=[]
        for ts,a,i in porT[T]:
            if (a,ts) in usados: continue
            k=dados[a]["idx"].get(T); e=fill(a,i,k) if k is not None else None
            if e: toc.append((ts,a,i,k,e))
        rng.shuffle(toc)
        for ts,a,i,k,e in toc:
            fr=[n for n in range(K) if livres[n]<=T]
            if not fr: break
            r,R,j=trade(dados[a],k,e,i,0.001); livres[fr[0]]=dados[a]["t"][j]+H4; usados.add((a,ts)); out.append((ts,T,dados[a]["t"][j]+H4,r,R))
    return out
def growK(ops,K,lev):
    # simples: cada operacao mexe 1/K da conta (aprox. sequencial por fecho)
    m=1;pk=1;dd=0
    for x in sorted(ops,key=lambda x:x[2]):
        m*=1+lev*x[3]/K; pk=max(pk,m); dd=max(dd,1-m/pk)
    return m,dd
for regra in ("base","1a da moeda + vaga"):
  for K in (2,4):
    for p in ("B1","B2"):
        rs=[];G=[];D=[];N=[]
        for s in range(30):
            v=[x for x in slots(random.Random(7+s),K,regra) if (x[0]<CUT)==(p=="B1")]
            N.append(len(v)); rs.append(np.mean([x[4] for x in v])); m,d=growK(v,K,1); G.append(m); D.append(d)
        print(regra,"K",K,p,"ops",int(np.mean(N)),"R",round(np.mean(rs),3),"conta 1x x%.2f dd%d%%"%(np.median(G),100*np.median(D)))
