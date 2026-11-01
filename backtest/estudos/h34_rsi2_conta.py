"""H34 (pre-registado 01/11, antes de correr). Rui: "arranja outra maneira de lucrar" com 20$ (uma posicao).
Reversao curta classica (Connors RSI-2), so nas moedas mais liquidas, ao nivel da conta (valor todo, 1 posicao).
Dados: 4H do ramo history, BTC e ETH (spread minimo). Metades H1 2021-08..2024-02, H2 2024-03..2026-10.
Regra: tendencia de fundo (fecho > SMA200 das velas de DIAS, so dias fechados); na vela de 4H, RSI(2) < 10 ->
compra ao fecho; sai quando o fecho passa a SMA(5) de 4H, ou ao fim de 12 velas (2 dias); sem stop (variante a)
ou stop 3 ATR(14) (variante b). Custos: c1 0,35%/lado (taker+deslize) e c2 0,10%/lado (maker, otimista).
k=2 variantes de regra. Uma posicao: se BTC e ETH dao sinal na mesma vela, BTC. Criterio fixo nas DUAS metades
(com c1): conta a crescer a 1x, >= 50 operacoes, retorno/queda melhor do que BTC guardado e media por
operacao acima do percentil 97,5 do acaso (mesmas saidas, entradas ao acaso nas velas em tendencia)."""
import gzip, random, numpy as np
HIST="/tmp/claude-0/hist"; H4=14400; DAY=86400
H1=(1627776000,1709251199); H2=(1709251200,1761350399)
def load(a):
    r=[l.split(",") for l in gzip.open(f"{HIST}/{a}.csv.gz","rt").read().split()]
    return np.array([[float(v) for v in z[:6]] for z in r if len(z)>=6])
D={}
for a in ("BTC","ETH"):
    x=load(a); t,o,h,l,c=x[:,0],x[:,1],x[:,2],x[:,3],x[:,4]
    d=c.copy(); up=np.maximum(np.diff(c,prepend=c[0]),0); dn=np.maximum(-np.diff(c,prepend=c[0]),0)
    def ema(v,n):
        out=np.zeros_like(v); a_=1/n
        for i in range(1,len(v)): out[i]=out[i-1]+a_*(v[i]-out[i-1])
        return out
    ru,rd=ema(up,2),ema(dn,2); rsi=100-100/(1+ru/np.maximum(rd,1e-12))
    pc=np.r_[c[0],c[:-1]]; tr=np.maximum(h,pc)-np.minimum(l,pc); atr=np.convolve(tr,np.ones(14)/14,"full")[:len(tr)]
    sma5=np.convolve(c,np.ones(5)/5,"full")[:len(c)]
    # tendencia diaria com dias fechados
    dia=(t//DAY).astype(int); fd={}
    for i in range(len(t)): fd[dia[i]]=c[i]
    ks=sorted(fd); dc=np.array([fd[k] for k in ks]); s200={}
    for j in range(200,len(ks)): s200[ks[j]]=dc[j-199:j+1].mean()>0 and dc[j]>dc[j-199:j+1].mean()
    tend=np.array([s200.get(dia[i]-1,False) for i in range(len(t))])
    D[a]=dict(t=t,o=o,h=h,l=l,c=c,rsi=rsi,atr=atr,sma5=sma5,tend=tend,idx={int(v):k for k,v in enumerate(t)})
def saida(d,i,var,cost):
    e=d["c"][i]; stop=e-3*d["atr"][i]
    for j in range(i+1,min(len(d["c"]),i+13)):
        if var=="b" and d["l"][j]<=stop: px=min(stop,d["o"][j]); return px/e-1-2*cost,j
        if d["c"][j]>d["sma5"][j] or j==i+12: return d["c"][j]/e-1-2*cost,j
    j=len(d["c"])-1; return d["c"][j]/e-1-2*cost,j
tempos=sorted(set(int(v) for v in D["BTC"]["t"])&set(int(v) for v in D["ETH"]["t"]))
def corre(var,cost,per,aleat=None,rng=None):
    ops=[];livre=0
    for T in tempos:
        if T<livre or not(per[0]<=T<=per[1]): continue
        for a in ("BTC","ETH"):
            d=D[a]; i=d["idx"][T]
            if not d["tend"][i]: continue
            sig = d["rsi"][i]<10 if aleat is None else rng.random()<aleat
            if sig:
                r,j=saida(d,i,var,cost); ops.append(r); livre=int(d["t"][j])+H4; break
    return ops
def conta(ops):
    m=pk=1;dd=0
    for r in ops: m*=1+r; pk=max(pk,m); dd=max(dd,1-m/pk)
    return m,dd
rng=random.Random(34)
print("H34 RSI-2 em BTC/ETH 4H, conta unica")
for per,nm in ((H1,"H1"),(H2,"H2")):
    b=D["BTC"]; ii=[k for k in range(len(b["t"])) if per[0]<=b["t"][k]<=per[1]]
    print(f" BTC guardado {nm}: x{b['c'][ii[-1]]/b['c'][ii[0]]:.2f}")
for var in ("a","b"):
    ok=True
    for per,nm in ((H1,"H1"),(H2,"H2")):
        o1=corre(var,0.0035,per); o2=corre(var,0.0010,per)
        m1,d1=conta(o1); m2,d2=conta(o2)
        frac=len(o1)/max(1,sum(1 for T in tempos if per[0]<=T<=per[1])); ac=[]
        for _ in range(300):
            v=corre(var,0.0035,per,aleat=frac*1.5,rng=rng); ac.append(np.mean(v) if v else 0)
        mu=np.mean(o1); pv=sum(x>=mu for x in ac)/len(ac)
        print(f" {var} {nm}: ops {len(o1)} media {100*mu:+.2f}%/op acerto {100*np.mean(np.array(o1)>0):.0f}% conta x{m1:.2f} queda {100*d1:.0f}% | maker x{m2:.2f} queda {100*d2:.0f}% | acaso {100*np.mean(ac):+.2f}%/op p={pv:.3f}")
        ok&= m1>1 and len(o1)>=50 and pv<0.025
    print(f"   {var}: {'PASSA -> PAPEL' if ok else 'CHUMBA'}")
