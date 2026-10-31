"""H30 (pre-registado 31/10, pedido do Rui: "tem de haver uma para subida tambem").
No H29 nenhuma familia de 4H ganhou na SUBIDA. Hipotese: na subida a vantagem esta em ESTAR comprado nas maiores,
nao em entrar e sair. Variantes (k=4, p<0,0125), sempre so com dias fechados (sem olhar para o futuro):
  S-BTC   comprado em BTC nos dias em que a fase do dia anterior e SUBIDA (H29), fora nos outros
  S-ETH   o mesmo em ETH;   S-SOL o mesmo em SOL
  S-TRIO  1/3 em cada (BTC, ETH, SOL)
Custos: 0,25% em cada entrada e saida. Periodos: P1 2021-2023, P2 2024-out/2026.
Comparacao: ficar sempre comprado (buy and hold) e ACASO = a mesma sequencia de exposicao deslocada no tempo por um
desvio ao acaso (rotacao circular, 200 vezes): mesmo numero de dias, de entradas e de saidas (custos iguais).
(Correcao antes de decidir: a 1.a versao sorteava dias soltos, com muitas mais trocas e custos, e era injusta.)
Criterio adaptado (nao ha R por operacao): retorno > 0 e acima do acaso com p < 0,0125 nos dois periodos, e queda maxima
menor do que a do buy and hold. O que passar vai para papel."""
import gzip, math, numpy as np, random
DAY = 86400
def diario(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    d = {}
    for z in r:
        if len(z) < 5: continue
        d[int(float(z[0])) // DAY] = float(z[4])
    return d
B = diario("BTC"); ks = sorted(B); c = np.array([B[k] for k in ks])
s200 = np.convolve(c, np.ones(200) / 200, "full")[:len(c)]; s50 = np.convolve(c, np.ones(50) / 50, "full")[:len(c)]
fase = {}
for i, k in enumerate(ks):
    if i < 210: continue
    j = i - 1
    fase[k] = 1 if (c[j] > s200[j] and s50[j] > s50[j - 10]) else (-1 if (c[j] < s200[j] and s50[j] < s50[j - 10]) else 0)
CUT, FIM = 1704067200 // DAY, 1792022400 // DAY
def serie(moedas):
    ds = [diario(m) for m in moedas]
    dias = [k for k in ks if k in fase and k < FIM and all(k in d and k - 1 in d for d in ds)]
    ret = np.array([np.mean([d[k] / d[k - 1] - 1 for d in ds]) for k in dias])
    return dias, ret
def avaliar(dias, ret, exp):
    eq, pico, mdd, prev = 1.0, 1.0, 0.0, 0
    for r, e in zip(ret, exp):
        if e != prev: eq *= 1 - 0.0025
        if e: eq *= 1 + r
        prev = e; pico = max(pico, eq); mdd = max(mdd, 1 - eq / pico)
    return eq - 1, mdd
print("H30 estar comprado nas maiores so na fase de SUBIDA (retorno total no periodo, queda maxima)")
rng = random.Random(30)
for nome, ms in (("S-BTC", ["BTC"]), ("S-ETH", ["ETH"]), ("S-SOL", ["SOL"]), ("S-TRIO", ["BTC", "ETH", "SOL"])):
    dias, ret = serie(ms); ok = True; cel = []
    for pp, sel in (("P1", [k < CUT for k in dias]), ("P2", [k >= CUT for k in dias])):
        idx = [i for i, s in enumerate(sel) if s]
        r = ret[idx]; exp = [1 if fase[dias[i]] == 1 else 0 for i in idx]
        tot, mdd = avaliar(None, r, exp); bh, bmdd = avaliar(None, r, [1] * len(r))
        nexp = sum(exp); acs = []
        for _ in range(200):
            o = rng.randrange(30, len(r) - 30)
            acs.append(avaliar(None, r, exp[o:] + exp[:o])[0])
        pv = sum(1 for a in acs if a >= tot) / len(acs)
        cel.append(f"{pp}: {100*tot:+.0f}% (queda max {100*mdd:.0f}%) | sempre comprado {100*bh:+.0f}% (queda {100*bmdd:.0f}%) | acaso {100*np.median(acs):+.0f}% p={pv:.3f} | {nexp} de {len(r)} dias")
        ok &= tot > 0 and pv < 0.0125 and mdd < bmdd
    print(f" {nome}:\n   " + "\n   ".join(cel) + f"\n   -> {'PASSA -> PAPEL' if ok else 'chumba'}")
