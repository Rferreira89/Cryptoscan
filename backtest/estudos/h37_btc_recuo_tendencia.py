"""H37 (pre-registado 02/11, antes de correr). Pergunta do Rui: "se a tendencia e para subir, porque nao comprar mais
baixo?". Comprar o recuo do BTC dentro da tendencia de fundo, AO NIVEL DA CONTA (valor todo, 1x e 2x).
Dados e metades do H33 (dias fechados, execucao na abertura seguinte, 0,35%/lado).
Regra: tendencia de fundo = fecho > SMA200. Entrada quando o fecho fica X% abaixo da SMA50 (recuo).
Saida quando o fecho volta acima da SMA50 (recuperou) OU fecha abaixo da SMA200 (tendencia partiu).
Variantes (k=2): X = 3% e X = 6%. Referencias: tendencia BTC 50d (H33 V2, a regra ligada) e BTC guardado.
Criterio fixo: nas DUAS metades conta a crescer a 1x, retorno/queda melhor do que a V2, e acima do percentil
97,5 do acaso (mesma sequencia dentro/fora rodada no tempo)."""
import random, numpy as np
exec(open("backtest/estudos/h33_conta_tendencia.py").read().split("rng = random.Random(33)")[0])
def recuo(x):
    c = C["BTC"]; pos = [None] * N; cur = None
    for i in range(210, N):
        s50, s200 = sma(c, 50, i), sma(c, 200, i)
        if cur is None and c[i] > s200 and c[i] < s50 * (1 - x): cur = "BTC"
        elif cur and (c[i] > s50 or c[i] < s200): cur = None
        pos[i] = cur
    return pos
rng = random.Random(37); v2 = sinal("V2")
print("H37 compra do recuo do BTC na tendencia (conta unica)")
for nome, per in (("H1", H1), ("H2", H2)):
    m, a, d, tr = conta(v2, per); print(f" V2 tendencia 50d {nome}: {100*a:+.0f}%/ano queda {100*d:.0f}% trocas {tr}")
for x in (0.03, 0.06):
    pos = recuo(x); ok = True
    for nome, per in (("H1", H1), ("H2", H2)):
        m, a, d, tr = conta(pos, per); m2, a2, d2, _ = conta(pos, per, 2.0)
        mv, av, dv, _ = conta(v2, per); ac = acaso(pos, per, rng); pv = sum(z >= m for z in ac) / len(ac)
        dentro = sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1] and pos[i]) / max(1, sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1]))
        print(f" recuo {int(x*100)}% {nome}: {100*a:+.0f}%/ano queda {100*d:.0f}% trocas {tr} no mercado {100*dentro:.0f}% p={pv:.3f} | 2x {100*a2:+.0f}%/ano queda {100*d2:.0f}%")
        ok &= m > 1 and (a / d if d else 0) > (av / dv if dv else 0) and pv < 0.025
    print(f"   recuo {int(x*100)}%: {'PASSA' if ok else 'CHUMBA'}")
c = C["BTC"]; i = N - 1
print(f"hoje (ultimo dia fechado no historico): fecho {c[i]:.0f} SMA50 {sma(c,50,i):.0f} SMA200 {sma(c,200,i):.0f}")
