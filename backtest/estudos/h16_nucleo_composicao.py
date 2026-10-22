"""H16 (pre-registado a 22/10, ANTES de correr; OK do Rui).

Mesma simulacao do H14/H15 (conta toda, 70% no nucleo, custos 0,35% por lado,
reforco na queda como hoje, periodos A 2021-24 e B 2024-26, sem depositos).
Referencia: o nucleo de hoje (BTC, ETH e SOL em partes iguais, 1 fecho diario).
Variantes (3 hipoteses):
  H16a  so BTC (os 70% todos em BTC)
  H16b  pesos 50% BTC, 25% ETH, 25% SOL
  H16c  confirmacao: entrar e sair so ao fim de 3 fechos diarios seguidos do mesmo lado
        da media de 200 dias (menos entradas e saidas a mais)
Criterio (fixado antes): uma variante substitui o nucleo de hoje so se, nos DOIS
periodos, render pelo menos +5 pontos percentuais a mais E a queda maxima nao for pior
em mais de 3 pontos. Contador global de hipoteses: +3.
"""
import sys
sys.path.insert(0, "/home/claude/cryptoscan/backtest/estudos")
import h14_h15_nucleo as H

MOEDAS = H.MOEDAS


def simula(t0, t1, pesos=None, confirma=1):
    pesos = pesos or {a: 1 / 3 for a in MOEDAS}
    usdc, qty = 100.0, {a: 0.0 for a in MOEDAS}
    pico, dd = 100.0, 0.0
    lado = {a: [] for a in MOEDAS}
    for dia in H.DIAS:
        if not (t0 // H.DAY <= dia < t1 // H.DAY):
            continue
        px = {a: H.CL[a][dia] for a in MOEDAS}
        eq = usdc + sum(qty[a] * px[a] for a in MOEDAS)
        for a in MOEDAS:
            if not pesos.get(a):
                continue
            m = H.sma200(a, dia)
            if m is None:
                continue
            lado[a] = (lado[a] + [px[a] > m])[-confirma:]
            acima = len(lado[a]) == confirma and all(lado[a])
            abaixo = len(lado[a]) == confirma and not any(lado[a])
            alvo = eq * 0.70 * pesos[a]
            val = qty[a] * px[a]
            if abaixo and qty[a]:
                usdc += val * (1 - H.CUSTO); qty[a] = 0.0
                continue
            if qty[a] == 0 and acima:
                comprar = min(alvo, usdc)
            elif qty[a] and val <= alvo * 0.85 and px[a] > m:
                comprar = min(alvo - val, usdc)
            else:
                comprar = 0
            if comprar > 1e-9:
                usdc -= comprar; qty[a] += comprar * (1 - H.CUSTO) / px[a]
        eq = usdc + sum(qty[a] * px[a] for a in MOEDAS)
        pico = max(pico, eq); dd = max(dd, 1 - eq / pico)
    return round(eq - 100, 1), round(dd * 100, 1)


if __name__ == "__main__":
    V = {"HOJE (BTC/ETH/SOL iguais, 1 fecho)": {},
         "H16a só BTC": {"pesos": {"BTC": 1.0}},
         "H16b 50% BTC, 25% ETH, 25% SOL": {"pesos": {"BTC": .5, "ETH": .25, "SOL": .25}},
         "H16c confirmação de 3 fechos": {"confirma": 3}}
    res = {}
    for nome, kw in V.items():
        res[nome] = [simula(H.A0, H.A1, **kw), simula(H.B0, H.B1, **kw)]
        (ra, da), (rb, db) = res[nome]
        print(f"{nome:36s} A: {ra:+.1f}% (queda máx. {da}%) | B: {rb:+.1f}% (queda máx. {db}%)")
    base = res["HOJE (BTC/ETH/SOL iguais, 1 fecho)"]
    print()
    for nome in list(V)[1:]:
        r = res[nome]
        ok = all(r[i][0] >= base[i][0] + 5 and r[i][1] <= base[i][1] + 3 for i in (0, 1))
        print(nome, "PASSA" if ok else "CHUMBA")
