"""H14 e H15 (pre-registados a 22/10, ANTES de correr; OK do Rui).

Simulacao diaria do nucleo (BTC, ETH, SOL, cada uma com a regra da media de 200
dias, em spot) com a conta toda: o nucleo e uma fracao do valor total da conta e o
resto fica em USDC (nesta simulacao o USDC nao rende, para isolar o nucleo).
Custos: 0,25% de comissao + 0,10% de deslize por compra e por venda.
Periodos: A = 2021-06-01 a 2024-05-31 e B = 2024-06-01 a 2026-10-15, cada um a comecar
com 100 USDC e sem depositos.

Base B0 (sem reforco na queda): compra a parte inteira (70% / 3) quando a moeda fecha
acima da media de 200 dias, vende tudo quando fecha abaixo, nada entre os dois.

H14  Reforco na queda (como o programa faz hoje): se o valor de uma moeda ficar 15% ou
     mais abaixo da sua parte (70% da conta / 3), compra a diferenca com o USDC livre.
     FICA LIGADO se, nos DOIS periodos, o retorno for >= o da base E a queda maxima
     nao for pior do que a da base em mais de 2 pontos percentuais. Senao, desliga-se.

H15  Nucleo a 85% na fase de subida (regra de fase do programa, BTC diario):
     a parte de cada moeda passa a 85% / 3 enquanto a fase for subida (compra a
     diferenca ao entrar na fase), e volta a 70% / 3 quando a fase sai de subida
     (vende o excesso). Comparado com a base.
     PASSA se, nos DOIS periodos, o retorno for >= base + 2 pontos E a queda maxima
     nao for pior do que a da base em mais de 3 pontos.
Contador global de hipoteses: +2.
"""
import gzip, sys
sys.path.insert(0, "/home/claude/cryptoscan")
from engine import backtest as B

DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
CUSTO = 0.0035
MOEDAS = ("BTC", "ETH", "SOL")


def load(a):
    rows = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    c4 = [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
           "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]
    return B.daily(c4)


D = {a: load(a) for a in MOEDAS}
DIAS = sorted(set.intersection(*[{x["t"] // DAY for x in D[a]} for a in MOEDAS]))
CL = {a: {x["t"] // DAY: x["c"] for x in D[a]} for a in MOEDAS}


def sma200(a, dia):
    i = IDX[a][dia]
    c = [x["c"] for x in D[a][i - 199:i + 1]]
    return sum(c) / 200 if len(c) == 200 else None


IDX = {a: {x["t"] // DAY: i for i, x in enumerate(D[a])} for a in MOEDAS}


def fase(dia):
    i = IDX["BTC"][dia]
    if i < 200:
        return None
    c = [x["c"] for x in D["BTC"][:i + 1]]
    s50, s200, r30 = sum(c[-50:]) / 50, sum(c[-200:]) / 200, c[-1] / c[-31] - 1
    return "subida" if c[-1] > s50 > s200 and r30 > 0.08 else "queda" if c[-1] < s50 < s200 and r30 < -0.08 else "lateral"


def simula(t0, t1, reforco=False, f_subida=None):
    usdc, qty = 100.0, {a: 0.0 for a in MOEDAS}
    pico, dd, fase_ant = 100.0, 0.0, None
    for dia in DIAS:
        if not (t0 // DAY <= dia < t1 // DAY):
            continue
        px = {a: CL[a][dia] for a in MOEDAS}
        eq = usdc + sum(qty[a] * px[a] for a in MOEDAS)
        fz = fase(dia)
        fr = f_subida if (f_subida and fz == "subida") else 0.70
        alvo = eq * fr / 3
        for a in MOEDAS:
            m = sma200(a, dia)
            if m is None:
                continue
            val = qty[a] * px[a]
            if px[a] <= m:
                if qty[a]:
                    usdc += val * (1 - CUSTO); qty[a] = 0.0
                continue
            if qty[a] == 0:
                comprar = min(alvo, usdc)
            elif reforco and val <= alvo * 0.85:
                comprar = min(alvo - val, usdc)
            elif f_subida and fz != fase_ant and val < alvo * 0.98:
                comprar = min(alvo - val, usdc)         # entrou na subida: sobe para 85%
            elif f_subida and fz != fase_ant and val > alvo * 1.02:
                vend = val - alvo                        # saiu da subida: volta a 70%
                qty[a] -= vend / px[a]; usdc += vend * (1 - CUSTO); comprar = 0
            else:
                comprar = 0
            if comprar > 1e-9:
                usdc -= comprar; qty[a] += comprar * (1 - CUSTO) / px[a]
        fase_ant = fz
        eq = usdc + sum(qty[a] * px[a] for a in MOEDAS)
        pico = max(pico, eq); dd = max(dd, 1 - eq / pico)
    return round(eq - 100, 1), round(dd * 100, 1)


if __name__ == "__main__":
    res = {}
    for nome, kw in (("BASE (sem reforço na queda)", {}), ("H14 reforço na queda (hoje)", {"reforco": True}),
                     ("H15 85% na subida", {"f_subida": 0.85})):
        res[nome] = [simula(A0, A1, **kw), simula(B0, B1, **kw)]
        (ra, da), (rb, db) = res[nome]
        print(f"{nome:30s} A: {ra:+.1f}% (queda máx. {da}%) | B: {rb:+.1f}% (queda máx. {db}%)")
    b = res["BASE (sem reforço na queda)"]
    h14 = res["H14 reforço na queda (hoje)"]
    h15 = res["H15 85% na subida"]
    ok14 = all(h14[i][0] >= b[i][0] and h14[i][1] <= b[i][1] + 2 for i in (0, 1))
    ok15 = all(h15[i][0] >= b[i][0] + 2 and h15[i][1] <= b[i][1] + 3 for i in (0, 1))
    print("\nH14:", "FICA LIGADO" if ok14 else "DESLIGA-SE (pior que a base)")
    print("H15:", "PASSA" if ok15 else "CHUMBA")
    btc = [CL["BTC"][d] for d in DIAS if A0 // DAY <= d < A1 // DAY]
    print(f"\nReferência: BTC comprado e guardado A {btc[-1] / btc[0] * 100 - 100:+.0f}%", end="")
    btc = [CL["BTC"][d] for d in DIAS if B0 // DAY <= d < B1 // DAY]
    print(f" | B {btc[-1] / btc[0] * 100 - 100:+.0f}%")
