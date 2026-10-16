"""Investigacao 2026-10-16: RESILIENTE (4H, so compras). Hipotese nova
(fila do Rui vazia), escrita antes de testar (commit 1ec4bb7).

LOGICA: quando o BTC cai forte numa vela de 4H quase todas as moedas caem com
ele; uma moeda que quase nao cai tem compradores a absorver a venda (procura
propria), e essa procura continua quando a pressao do BTC passa. Riscos
declarados: nasceu depois do ATRASO_BTC (mesma reserva), noticia propria ja
esgotada, efeito arbitrado a 4H, amostra curta.

REGRAS (decisao no fecho da vela i de 4H, so velas ja fechadas):
  mercado : BTC fechou o ultimo dia completo acima da SMA200 diaria
  queda   : fecho do BTC na vela i <= (1 - X) x fecho do BTC na vela i-1
  aguenta : retorno da moeda na mesma vela >= 1/4 do retorno do BTC
  entrada : abertura da vela i+1
  stop    : fecho(i) - 1,5 ATR14; um objetivo a 2R; sem stop na entrada;
            saida ao fim de H dias
  carteira: 4 x 25%, uma por moeda, primeiro a maior resiliencia
GRELHA (4): X in {1,5%; 2,5%} x H in {1, 3} dias.

Uso: python -m tools.research_resiliente <historico>
"""
import json
import sys

from engine import backtest as B
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
GRID = [{"X": x, "H": h} for x in (0.015, 0.025) for h in (1, 3)]
LAG, STOP_ATR = 0.25, 1.5


def btc_moves(btc):
    """{t de abertura da vela: retorno fecho/fecho anterior do BTC}."""
    return {btc[i]["t"]: btc[i]["c"] / btc[i - 1]["c"] - 1
            for i in range(1, len(btc)) if btc[i - 1]["t"] == btc[i]["t"] - TF}


def signals(c4, moves, btc_up, x):
    at = R.atr(c4)
    out = {}
    for i in range(1, len(c4)):
        b, tc = c4[i], c4[i]["t"] + TF
        m = moves.get(b["t"])
        if m is None or m > -x or at[i] is None or c4[i - 1]["t"] != b["t"] - TF:
            continue
        r = b["c"] / c4[i - 1]["c"] - 1
        if r < LAG * m:
            continue
        if not btc_up.get((tc - R.DAY) // R.DAY):
            continue
        stop = b["c"] - STOP_ATR * at[i]
        if stop <= 0:
            continue
        out[tc] = {"stop": stop, "tp_r": 2, "partials": [100],
                   "breakeven": False, "rank": -(r - m)}
    return out


def main(folder, out="backtest/research_resiliente.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    moves = btc_moves(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data and a != "BTC"]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        if cfg["X"] not in cache:
            cache[cfg["X"]] = {a: signals(data[a], moves, btc_up, cfg["X"])
                               for a in data if a != "BTC"}
        return R.simulate(data, cache[cfg["X"]], TF, cfg["H"] * R.DAY, universe)

    res = R.evaluate("RESILIENTE", GRID, runner, data, TF,
                     lambda cfg: cfg["H"] * R.DAY, 90, majors, base, d0, ds,
                     d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
