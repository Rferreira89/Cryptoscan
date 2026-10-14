"""Investigacao 2026-10-14: QUEBRA COM COMPRADORES AGRESSIVOS (4H, so
compras). Hipotese 5 da fila do Rui (pedida em 2026-10-11).

HIPOTESE (escrita na fila e no pre-registo de 2026-10-14 antes de testar):
uma quebra de maximo em que a maior parte do volume e de compras a mercado
(taker) mostra procura real; a mesma quebra sem compradores agressivos e
muitas vezes falsa. A autopsia da arena (BREAKOUT, TURTLE, SQUEEZE_BB) diz
que as quebras de 4H revertem neste mercado: esta e a correcao que ataca
essa causa (separar quebras com procura real das outras).

REGRAS (decisao no fecho da vela i de 4H, so com velas ja fechadas):
  mercado : BTC fechou o ultimo dia completo acima da SMA200 diaria
  quebra  : fecho(i) > maximo das 20 velas anteriores (i-20..i-1)
  volume  : volume(i) >= 1,5 x media do volume das 20 velas anteriores
  fluxo   : volume comprador (taker, coluna 7) / volume(i) >= q
  entrada : abertura da vela i+1
  stop    : minimo(i) - 0,1 ATR14, nunca a menos de 1 ATR do fecho(i)
            (se ficar mais perto, desce para fecho - 1 ATR); se ficar a
            mais de 3 ATR do fecho, nao ha operacao
  saida   : um objetivo a 2R (100%); sem stop na entrada; saida ao fim de
            H dias
  carteira: 4 operacoes de 25%, uma por moeda; primeiro a maior parte
            compradora
GRELHA (4): q in {0,55; 0,60} x H in {3, 7}.
Custos, janela (24 meses: 18 desenho + 6 reserva), walk-forward e os 7
criterios: tools/research_rlib.evaluate.

Uso: python -m tools.research_taker_breakout <historico>
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
GRID = [{"q": q, "H": h} for q in (0.55, 0.60) for h in (3, 7)]
N, VOL_K, MIN_ATR, MAX_ATR = 20, 1.5, 1.0, 3.0


def signals(c4, btc_up, q):
    """{t da abertura da entrada: sinal}. A vela i so usa velas 0..i e dias
    completos ja fechados."""
    at = R.atr(c4)
    out = {}
    for i in range(N, len(c4)):
        b, tc = c4[i], c4[i]["t"] + TF
        if at[i] is None or not b.get("v"):
            continue
        prev = c4[i - N:i]
        if not b["c"] > max(x["h"] for x in prev):
            continue
        if b["v"] < VOL_K * sum(x["v"] for x in prev) / N:
            continue
        share = b.get("tb", 0) / b["v"]
        if share < q:
            continue
        if not btc_up.get((tc - R.DAY) // R.DAY):
            continue
        stop = min(b["l"] - 0.1 * at[i], b["c"] - MIN_ATR * at[i])
        if b["c"] - stop > MAX_ATR * at[i] or stop <= 0:
            continue
        out[tc] = {"stop": stop, "tp_r": 2, "partials": [100],
                   "breakeven": False, "rank": -share, "share": share}
    return out


def main(folder, out="backtest/research_taker_breakout.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        if cfg["q"] not in cache:
            cache[cfg["q"]] = {a: signals(data[a], btc_up, cfg["q"]) for a in data}
        return R.simulate(data, cache[cfg["q"]], TF, cfg["H"] * R.DAY, universe)

    res = R.evaluate("QUEBRA_COMPRADORES", GRID, runner, data, TF,
                     lambda cfg: cfg["H"] * R.DAY, 90, majors, base, d0, ds,
                     d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
