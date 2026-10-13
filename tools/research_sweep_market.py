"""Investigacao 2026-10-13: SWEEP_MERCADO, sucessor da arena do
LIQUIDITY_SWEEP (morto em 2026-10-13 por forma recente).

AUTOPSIA (backtest/investigacao.md, 2026-10-13): nos ultimos 24 meses o
LIQUIDITY_SWEEP ao vivo deu -0,29R em 154 operacoes. Quando a abertura
seguinte ja esta dentro da zona de entrada e a operacao abre logo, -0,17R;
quando a ordem limite fica a espera e so e preenchida depois, com o preco a
voltar para baixo, -0,54R. Selecao adversa da ordem limite.

CORRECAO UNICA (escrita e guardada em commit antes de testar, dff0269):
mesmo setup, stop, objetivos e vendas parciais do LIQUIDITY_SWEEP ao vivo
(engine/backtest.candidates: score >= minimo; BTC acima da SMA200 no ultimo
dia fechado); a operacao abre a mercado na abertura da vela de 4H seguinte
ao sinal ou nao abre.
GRELHA (2): A = abre sempre (se a abertura estiver entre o stop e o 1.o
objetivo); B = so abre se a abertura estiver no topo da zona de entrada ou
abaixo. Stop na entrada depois do 1.o objetivo, 30 dias no maximo.
Carteira, custos, janela, walk-forward e criterios: tools/research_rlib.

Uso: python -m tools.research_sweep_market <historico> <cache> [cache2 ...]
(cache = pastas com <MOEDA>.pkl contendo (candidatos, ...) de
engine/backtest.candidates; as que faltarem sao geradas)
"""
import json
import os
import pickle
import sys

from engine import backtest as B, config
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
STRATEGY = "LIQUIDITY_SWEEP"
GRID = [{"V": "A"}, {"V": "B"}]
HOLD = 30 * R.DAY
CFG = dict(config.load(), swing_leverage=1.0, capital_usdc=None,
           fixed_position_usdc=None)


def load_candidates(data, caches):
    """{moeda: candidatos} juntando as caches (sem repetidos)."""
    reg = None
    out = {}
    for a in sorted(data):
        seen, cs = set(), []
        for d in caches:
            fn = os.path.join(d, a + ".pkl")
            if not os.path.exists(fn):
                if d != caches[0]:
                    continue
                reg = reg or B.regimes(data["BTC"])
                got = B.candidates(a, data[a], reg, CFG)
                os.makedirs(d, exist_ok=True)
                pickle.dump((got,), open(fn, "wb"))
            for c in pickle.load(open(fn, "rb"))[0]:
                if c["i"] not in seen:
                    seen.add(c["i"])
                    cs.append(c)
        out[a] = sorted(cs, key=lambda c: c["i"])
    return out


def _plan_fn(plan, variant):
    top = plan["entry_zone"][1]

    def f(o):
        if variant == "B" and o > top:
            return None
        return {"stop": plan["stop"], "tp": list(plan["tp"]),
                "partials": list(plan["partials"]), "breakeven": True}
    return f


def signals(cands, c4, btc_up, variant, min_score=None):
    """{t da abertura da vela seguinte ao sinal: sinal}. O candidato da vela
    i foi decidido no fecho de i so com velas ate i; o filtro do BTC usa o
    ultimo dia fechado antes desse fecho."""
    ms = CFG["min_score"] if min_score is None else min_score
    out = {}
    for c in cands:
        if c["strategy"] != STRATEGY or c["score"] < ms:
            continue
        if not btc_up.get((c["t"] - R.DAY) // R.DAY):
            continue
        if c["i"] + 1 >= len(c4):
            continue
        t = c4[c["i"] + 1]["t"]
        if t != c["t"]:                     # abertura seguinte = fecho de i
            continue
        out[t] = {"plan_fn": _plan_fn(c["plan"], variant),
                  "stop": c["plan"]["stop"], "rank": -c["score"]}
    return out


def main(folder, caches, out="backtest/research_sweep_market.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    cands = load_candidates(data, caches)
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    sig = {v: {a: signals(cands[a], data[a], btc_up, v) for a in data}
           for v in ("A", "B")}

    def runner(cfg, universe):
        return R.simulate(data, sig[cfg["V"]], TF, HOLD, universe)

    res = R.evaluate("SWEEP_MERCADO", GRID, runner, data, TF, lambda c: HOLD,
                     90, majors, base, d0, ds, d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2:]), indent=1))
