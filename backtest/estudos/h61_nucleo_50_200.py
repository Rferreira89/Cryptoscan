"""H61 (13/11, ordem do Rui, A5): nucleo BTC, media de 50 contra media de 200 dias, com o MESMO metodo da validacao
original e dos estudos H19/H33: velas de 4h do ramo history agregadas em dias fechados, decisao no fecho, execucao na
abertura seguinte, custos 0,25% comissao + 0,10% deslize por lado, sem alavancagem, valor todo, sem dados do futuro.
Periodos da validacao original: A 2021-06-01 a 2024-05-31, B 2024-06-01 ate ao fim dos dados.
Criterios (os tres ja usados no projeto, aplicados sem mudar):
  C1 original (20/10): retorno positivo nos dois periodos.
  C2 H19 (27/10): positivo nos dois e Sharpe >= BTC comprado e guardado nos dois.
  C3 H33 (01/11): nos dois, retorno anual > 0, retorno/queda melhor que BTC guardado, acima do p95 do acaso
     (rotacao circular da sequencia dentro/fora, 500 desvios) e queda maxima <= 40%.
Uso: python3 backtest/estudos/h61_nucleo_50_200.py <pasta_history> [saida.json]"""
import gzip
import json
import math
import random
import sys

DAY = 86400
A = (1622505600, 1717199999)          # 2021-06-01 .. 2024-05-31
B0 = 1717200000                       # 2024-06-01 ..
CUSTO = 0.0035


def diario(pasta):
    d = {}
    for l in gzip.open(f"{pasta}/BTC.csv.gz", "rt").read().split():
        z = l.split(",")
        if len(z) < 5:
            continue
        t, o, c = int(float(z[0])), float(z[1]), float(z[4])
        k = t // DAY * DAY
        if k not in d:
            d[k] = [o, c, 1]
        else:
            d[k][1] = c
            d[k][2] += 1
    return [(k, v[0], v[1]) for k, v in sorted(d.items()) if v[2] >= 6]


def posicoes(dd, n):
    """dentro[i] = 1 se no dia i (aberto na abertura de i) se esta em BTC, decidido no fecho de i-1."""
    c = [x[2] for x in dd]
    out = [0] * len(dd)
    for i in range(n, len(dd)):
        ma = sum(c[i - n:i]) / n
        out[i] = 1 if c[i - 1] > ma else 0
    return out


def curva(dd, dentro, t0, t1):
    eq, pico, dd_max, rets, trocas = 1.0, 1.0, 0.0, [], 0
    prev = 0
    for i, (t, o, c) in enumerate(dd):
        if not (t0 <= t <= t1) or i == 0:
            continue
        r = 0.0
        if dentro[i]:
            r = c / o - 1 if not prev else c / dd[i - 1][2] - 1
            if not prev:
                r -= CUSTO
                trocas += 1
        if prev and not dentro[i]:
            r = o / dd[i - 1][2] - 1 - CUSTO                 # vende na abertura
        eq *= 1 + r
        rets.append(r)
        pico = max(pico, eq)
        dd_max = min(dd_max, eq / pico - 1)
        prev = dentro[i]
    anos = len(rets) / 365
    m = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / len(rets)) if rets else 0
    return {"retorno_pct": round(100 * (eq - 1), 1), "anual_pct": round(100 * (eq ** (1 / anos) - 1), 1) if anos else 0,
            "queda_pct": round(100 * dd_max, 1), "sharpe": round(m / sd * math.sqrt(365), 2) if sd else 0,
            "trocas": trocas, "dentro_pct": round(100 * sum(dentro[i] for i, x in enumerate(dd) if t0 <= x[0] <= t1)
                                                  / max(1, sum(1 for x in dd if t0 <= x[0] <= t1)), 1)}


def acaso(dd, dentro, t0, t1, n=500, semente=11):
    idx = [i for i, x in enumerate(dd) if t0 <= x[0] <= t1]
    seq = [dentro[i] for i in idx]
    rnd = random.Random(semente)
    real = curva(dd, dentro, t0, t1)["retorno_pct"]
    res = []
    for _ in range(n):
        k = rnd.randrange(1, len(seq))
        rot = seq[k:] + seq[:k]
        d2 = list(dentro)
        for j, i in enumerate(idx):
            d2[i] = rot[j]
        res.append(curva(dd, d2, t0, t1)["retorno_pct"])
    res.sort()
    return {"p95_pct": res[int(0.95 * n)], "p": round(sum(1 for x in res if x >= real) / n, 3)}


def main(pasta, saida=None):
    dd = diario(pasta)
    fim = dd[-1][0]
    per = {"A": A, "B": (B0, fim)}
    hold = {k: curva(dd, [1] * len(dd), *v) for k, v in per.items()}
    out = {"dados_ate": fim, "btc_guardado": hold, "regras": {}}
    for n in (50, 200):
        pos = posicoes(dd, n)
        r = {k: dict(curva(dd, pos, *v), **acaso(dd, pos, *v)) for k, v in per.items()}
        c1 = all(r[k]["retorno_pct"] > 0 for k in per)
        c2 = c1 and all(r[k]["sharpe"] >= hold[k]["sharpe"] for k in per)
        c3 = all(r[k]["anual_pct"] > 0 and r[k]["retorno_pct"] / max(1e-9, -r[k]["queda_pct"])
                 > hold[k]["retorno_pct"] / max(1e-9, -hold[k]["queda_pct"]) and r[k]["retorno_pct"] > r[k]["p95_pct"]
                 and r[k]["queda_pct"] >= -40 for k in per)
        out["regras"][f"MA{n}"] = {"periodos": r, "C1_original": c1, "C2_H19": c2, "C3_H33": c3}
    if saida:
        json.dump(out, open(saida, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
