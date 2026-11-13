"""C2 (13/11, ordem do Rui): tendencia diaria e semanal em indices e metais, para os X-Perps da OKX (US500, US100,
XAU, XAG, CL). Os contratos da OKX tem 1 semana a 6 meses de historia: usa-se o ativo por baixo (FRED: SP500,
NASDAQ100; Yahoo, futuro continuo sem ajuste de mudanca de contrato: GC=F, SI=F, CL=F) e anota-se que o contrato da
OKX pode divergir (premio, horas sem volume).
Regras fixas ANTES de correr (3 regras x 2 modos x 5 ativos = 30 testes, Holm):
  MA200   no fecho: acima da media de 200 dias -> comprado; abaixo -> vendido (modo LS) ou fora (modo L)
  DON     Donchian: entra comprado ao fechar acima do maximo de 50 dias, sai abaixo do minimo de 20 (vendido ao
          contrario no modo LS)
  SEM     semanal: media de 10 semanas acima da de 40 -> comprado; abaixo -> vendido (LS) ou fora (L)
Execucao no fecho seguinte ao sinal (sem futuro); custos OKX 0,10% por lado (comissao + deslize) por cada mudanca;
financiamento 0,01%/8 h (0,03%/dia) pago sempre que ha posicao (conservador, qualquer lado).
Periodos por tempo: treino 50%, validacao 25%, fora 25% da serie de cada ativo. Criterio: retorno liquido > 0 nos
tres periodos, Sharpe em validacao+fora acima do comprar-e-manter do proprio ativo, e p de Holm < 0,05 (t dos
retornos diarios em validacao+fora).
Uso: python3 backtest/estudos/c2_tendencia_indices.py <pasta_indices> [saida.json]"""
import csv
import json
import math
import os
import sys

CUSTO, FUND_DIA = 0.001, 0.0003


def fred(p):
    out = []
    for r in csv.DictReader(open(p)):
        v = list(r.values())
        try:
            out.append((v[0], float(v[1])))
        except (ValueError, IndexError):
            continue
    return out


def yahoo(p):
    d = json.load(open(p))["chart"]["result"][0]
    ts, cs = d["timestamp"], d["indicators"]["quote"][0]["close"]
    import time
    return [(time.strftime("%Y-%m-%d", time.gmtime(t)), c) for t, c in zip(ts, cs) if c]


def posicoes(c, regra, modo):
    n = len(c)
    pos = [0] * n
    if regra == "MA200":
        for i in range(200, n):
            m = sum(c[i - 200:i]) / 200
            pos[i] = 1 if c[i - 1] > m else (-1 if modo == "LS" else 0)
    elif regra == "DON":
        p = 0
        for i in range(51, n):
            hi, lo = max(c[i - 51:i - 1]), min(c[i - 21:i - 1])
            if c[i - 1] > hi:
                p = 1
            elif c[i - 1] < lo:
                p = -1 if modo == "LS" else 0
            elif p == 1 and c[i - 1] < lo:
                p = 0
            pos[i] = p
    elif regra == "SEM":
        for i in range(200, n):
            sem = c[i - 200:i:5]                      # um fecho por semana (5 sessoes)
            m10, m40 = sum(sem[-10:]) / 10, sum(sem[-40:]) / 40
            pos[i] = 1 if m10 > m40 else (-1 if modo == "LS" else 0)
    return pos


def rets(c, pos):
    out = [0.0]
    for i in range(1, len(c)):
        r = pos[i] * (c[i] / c[i - 1] - 1)
        if pos[i] != pos[i - 1]:
            r -= CUSTO * abs(pos[i] - pos[i - 1])
        if pos[i]:
            r -= FUND_DIA
        out.append(r)
    return out


def stats(rs):
    if not rs:
        return {}
    eq = 1.0
    for r in rs:
        eq *= 1 + r
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / max(1, len(rs) - 1))
    return {"ret_pct": round(100 * (eq - 1), 1), "sharpe": round(m / sd * math.sqrt(252), 2) if sd else 0.0,
            "t": m / (sd / math.sqrt(len(rs))) if sd else 0.0}


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def correr(pasta):
    series = {"SP500": fred(os.path.join(pasta, "fred_SP500.csv")), "NASDAQ100": fred(os.path.join(pasta, "fred_NASDAQ100.csv")),
              "OURO": yahoo(os.path.join(pasta, "yahoo_GCF.json")), "PRATA": yahoo(os.path.join(pasta, "yahoo_SIF.json")),
              "PETROLEO": yahoo(os.path.join(pasta, "yahoo_CLF.json"))}
    linhas = []
    for a, s in series.items():
        c = [x[1] for x in s if x[1] and x[1] > 0]
        n = len(c)
        cortes = (int(0.5 * n), int(0.75 * n))
        bh = rets(c, [1] * n)
        for regra in ("MA200", "DON", "SEM"):
            for modo in ("L", "LS"):
                rs = rets(c, posicoes(c, regra, modo))
                per = {"treino": stats(rs[200:cortes[0]]), "validacao": stats(rs[cortes[0]:cortes[1]]),
                       "fora": stats(rs[cortes[1]:])}
                vf = stats(rs[cortes[0]:])
                bvf = stats(bh[cortes[0]:])
                linhas.append({"ativo": a, "regra": regra, "modo": modo, "dias": n, "desde": s[0][0],
                               "periodos": {k: {kk: v[kk] for kk in ("ret_pct", "sharpe")} for k, v in per.items()},
                               "validacao_mais_fora": {"ret_pct": vf["ret_pct"], "sharpe": vf["sharpe"]},
                               "comprar_manter_vf": {"ret_pct": bvf["ret_pct"], "sharpe": bvf["sharpe"]},
                               "p": 1 - phi(vf["t"]),
                               "_base": all(per[k]["ret_pct"] > 0 for k in per) and vf["sharpe"] > bvf["sharpe"]})
    ps = [l["p"] for l in linhas]
    ordem = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, cor = [0.0] * len(ps), 0.0
    for j, i in enumerate(ordem):
        cor = max(cor, min(1.0, (len(ps) - j) * ps[i]))
        adj[i] = cor
    for l, h in zip(linhas, adj):
        l["p_holm"] = round(h, 4)
        l["p"] = round(l["p"], 4)
        l["vantagem"] = bool(l.pop("_base") and h < 0.05)
    return {"testes": len(linhas), "linhas": linhas,
            "aviso": "ativos por baixo dos X-Perps, nao os contratos da OKX; futuros continuos sem ajuste de mudanca de contrato"}


if __name__ == "__main__":
    r = correr(sys.argv[1])
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"), indent=1)
    for l in r["linhas"]:
        p = l["periodos"]
        print(f"{l['ativo']:9s} {l['regra']:5s} {l['modo']:2s} desde {l['desde']} | treino {p['treino']['ret_pct']:+7.1f}% val "
              f"{p['validacao']['ret_pct']:+6.1f}% fora {p['fora']['ret_pct']:+6.1f}% | Sharpe vf {l['validacao_mais_fora']['sharpe']:5.2f}"
              f" vs B&H {l['comprar_manter_vf']['sharpe']:5.2f} | Holm {l['p_holm']:.3f} {'VANTAGEM' if l['vantagem'] else ''}")
