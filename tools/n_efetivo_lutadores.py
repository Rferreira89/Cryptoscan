"""Numero efetivo de testes independentes entre os lutadores de compra do
ringue (auditoria de 2026-11-11).

O diario diz "com 26 testes, ~74% de probabilidade de pelo menos um falso
positivo" assumindo testes independentes. Muitos lutadores sao variantes da
mesma entrada (a familia do Oversold Bounce tem 15), por isso os testes estao
correlacionados. Aqui mede-se essa correlacao nos resultados DIARIOS (soma do
R das operacoes abertas em cada dia; dia sem operacao = 0), so na janela de
DESENHO (os 18 meses antes da reserva), e converte-se em numero efetivo de
testes (Nyholt, Li-Ji, participacao).

Nao seleciona nada nem decide nada: so mede quantas apostas diferentes
existem de facto entre as que ja foram testadas.

Uso: python -m tools.n_efetivo_lutadores <pasta_history> [saida.json]
"""
import json
import sys

from engine import backtest as B
from tools import arena_ringue as R
from tools import estatistica_multipla as E
from tools.triagem_anomalias import CORTE

DAY, H4 = 86400, 4 * 3600
SEM_DADOS = {"BOUNCE_LSR", "BOUNCE_MACRO", "BOUNCE_MEDO", "MAIORES_FUNDING"}   # precisam de dados ao vivo


def operacoes_lutadores(pasta, corte=CORTE, meses=18):
    bars, _ = B.load_all(pasta, min_bars=1500)
    bars = {a: [x for x in c if x["t"] + H4 <= corte] for a, c in bars.items()}
    btc = bars["BTC"]
    above = R.btc_above(btc)
    R.CTX.update(btc=btc, bars=bars, funding={}, oi={}, macro={}, ls={}, rank={})
    R.CTX.pop("_amp", None)
    t0 = corte - int(meses * 30.44 * DAY)
    out = {}
    for k, fn in R.NEW_SIGS.items():
        if k in SEM_DADOS:
            continue
        trs = []
        for a, c4 in bars.items():
            trs += [[int(t["t"]), a, round(t["r"], 4)] for _, t in R.generic_trades(a, c4, above, t0, k, fn)]
        out[k] = trs
    return {"t0": t0, "corte": corte, "ops": out}


def calcular(ops, min_ops=30):
    series = {}
    for k, trs in ops.items():
        if len(trs) < min_ops:
            continue
        d = {}
        for t, _, r in trs:
            d[t // DAY] = d.get(t // DAY, 0.0) + r
        series[k] = d
    nomes, m = E.matriz_correlacao(series)
    ne = E.n_efetivo_testes(m)
    pares = sorted(((m[i][j], nomes[i], nomes[j]) for i in range(len(nomes)) for j in range(i + 1, len(nomes))),
                   reverse=True)
    return {"lutadores": nomes, "n_efetivo": ne,
            "pares_mais_correlacionados": [[a, b, round(r, 3)] for r, a, b in pares[:10]],
            "correlacao_media": round(sum(r for r, _, _ in pares) / len(pares), 3) if pares else None,
            "prob_fp_independentes": round(E.prob_falso_positivo(len(nomes)), 3),
            "prob_fp_efetivo": round(E.prob_falso_positivo(ne["nyholt"]), 3)}


if __name__ == "__main__":
    o = operacoes_lutadores(sys.argv[1])
    res = calcular(o["ops"])
    res["janela"] = [o["t0"], o["corte"]]
    res["operacoes_por_lutador"] = {k: len(v) for k, v in o["ops"].items()}
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
