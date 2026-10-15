"""Investigacao 2026-10-15: CAP_MERCADO, sucessor da arena para a
CAPITULACAO (morta em 2026-10-15 por forma recente).

AUTOPSIA (backtest/investigacao.md, 2026-10-15): a vela de capitulacao de
`tools.arena_ringue.sig_capitulacao` so ganha nos dias em que o mercado
inteiro e despejado ao mesmo tempo (venda forcada, sem informacao); isolada
numa moeda perde (venda informada). O filtro do ringue (BTC acima da SMA200)
deita fora precisamente os colapsos gerais.

CORRECAO UNICA (escrita antes de testar, commit 5240ac0): o filtro de mercado
passa a ser "o mercado inteiro capitulou": na vela do sinal ou na anterior,
pelo menos B das moedas com historico nessa vela tiveram o minimo pelo menos
7% abaixo do fecho da vela anterior. Gatilho, stop, objetivos, stop na
entrada depois do 1.o objetivo e saida ao fim de 3 dias: exatamente os de
`sig_capitulacao` (formato G0).
GRELHA (3): B in {0,20; 0,35; 0,50}.
Carteira 4 x 25%, uma por moeda, primeiro o maior volume relativo. Custos,
janela, walk-forward e os 7 criterios: tools/research_rlib.evaluate.

Uso: python -m tools.research_cap_mercado <historico>
"""
import json
import sys

from engine import backtest as B
from tools import research_rlib as R
from tools.arena_ringue import sig_capitulacao
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
HOLD = 3 * R.DAY
FLUSH, MIN_COINS = 0.07, 20
GRID = [{"B": b} for b in (0.20, 0.35, 0.50)]


def breadth(data):
    """{t de abertura da vela: fracao das moedas com minimo >= 7% abaixo do
    fecho anterior}. So usa a propria vela (todas fecham em t + TF)."""
    hit, tot = {}, {}
    for c4 in data.values():
        for i in range(1, len(c4)):
            t = c4[i]["t"]
            if c4[i - 1]["t"] != t - TF:
                continue
            tot[t] = tot.get(t, 0) + 1
            if c4[i]["l"] <= (1 - FLUSH) * c4[i - 1]["c"]:
                hit[t] = hit.get(t, 0) + 1
    return {t: hit.get(t, 0) / n for t, n in tot.items() if n >= MIN_COINS}


def raw_signals(c4):
    """{t da abertura da entrada: (sinal, t da vela do sinal)} so com a vela
    de capitulacao da moeda (sem filtro de mercado)."""
    out = {}
    for i in range(60, len(c4)):
        sig = sig_capitulacao(c4[max(0, i - 299):i + 1])
        if not sig:
            continue
        b = c4[i]
        vavg = sum(x["v"] for x in c4[i - 20:i]) / 20
        out[b["t"] + TF] = ({"stop": sig["stop"], "tp": list(sig["tp"]),
                             "partials": list(sig["partials"]),
                             "breakeven": True, "rank": -b["v"] / vavg},
                            b["t"])
    return out


def signals(raw, br, b_min):
    """Filtra pela capitulacao do mercado (vela do sinal ou a anterior)."""
    out = {}
    for te, (s, t) in raw.items():
        if max(br.get(t, 0), br.get(t - TF, 0)) >= b_min:
            out[te] = s
    return out


def main(folder, out="backtest/research_cap_mercado.json"):
    data, _ = B.load_all(folder)
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    br = breadth(data)
    raw = {a: raw_signals(data[a]) for a in data}

    def runner(cfg, universe):
        sigs = {a: signals(raw[a], br, cfg["B"]) for a in data}
        return R.simulate(data, sigs, TF, HOLD, universe)

    res = R.evaluate("CAP_MERCADO", GRID, runner, data, TF, lambda cfg: HOLD,
                     90, majors, base, d0, ds, d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
