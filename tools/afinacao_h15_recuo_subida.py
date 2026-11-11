"""Afinacao H15 (2026-11-11): o Recuo (PULLBACK) do motor so na fase de subida.

Candidatos do PULLBACK com as mesmas funcoes do ao vivo (backtest.candidates);
fase do BTC do dia fechado anterior (arena_ringue.regime_by_day). Grelha escrita
antes de testar (afinacao.md, H15):
  P0 PULLBACK, metodo do ringue (backtest.simulate), todas as fases
  P1 P0 so na subida
  P2 o lutador RECUO_SUBIDA (NEW_SIGS): entrada a mercado na abertura seguinte
  P3 P0 so na lateral (controlo)
  P4 P1 com todos os scores
Custos: 0,25% de comissao e 0,1% de slippage por lado.

Uso: python -m tools.afinacao_h15_recuo_subida <pasta_history> <saida.json>
"""
import json
import os
import pickle
import sys
from multiprocessing import Pool

from engine import backtest as B, config
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random
from tools.afinacao_h09_racio import B_END, B_START
from tools.afinacao_h10_racio_short import summary

DAY, H4 = AR.DAY, AR.H4
SLIP = 0.1
_G = {}


def _cands(a):
    cfg = config.load()
    c4 = _G["bars"][a]
    out = [cd for cd in B.candidates(a, c4, _G["reg"], cfg, start_t=B_START)
           if cd["strategy"] == "PULLBACK"]
    for cd in out:
        cd.pop("families", None)
    return a, out


def recuo_plano(plan, score):
    """Plano do PULLBACK no formato NEW_SIGS (stop, objetivos e parciais do motor)."""
    return {"stop": plan["stop"], "tp": list(plan["tp"]), "partials": list(plan["partials"]),
            "breakeven": True, "hold_s": 30 * DAY, "atr": plan.get("atr"),
            "gatilho": f"recuo numa tendência com o mercado em subida (score {score})"}


def _init(bars, reg):
    _G.update(bars=bars, reg=reg)


def ring_trades(cands, bars, cfg, above, fases, score_min):
    """Metodo do ringue (live_trades) com slippage de 0,1%."""
    out = []
    for a, cs in cands.items():
        for cd in cs:
            if score_min and cd["score"] < score_min:
                continue
            if not AR._known(cd["t"], above) and cfg.get("require_btc_above_sma200"):
                continue
            if fases and _G["rmap"].get((cd["t"] - DAY) // DAY) not in fases:
                continue
            res = B.simulate(cd, bars[a], cfg, slip_pct=SLIP)
            if res["status"] != "CLOSED":
                continue
            p = cd["plan"]
            ref = p["entry_zone"][1]
            out.append({"asset": a, "t": res["entry_t"], "r": res["r"],
                        "geo": {"stop": p["stop"] / ref - 1, "tp": [x / ref - 1 for x in p["tp"]],
                                "partials": list(p["partials"]), "breakeven": True}})
    return sorted(out, key=lambda t: t["t"])


def fighter_trades(cands, bars, above, score_min):
    """P2: o lutador no metodo generic_trades (sinal na ultima vela fechada)."""
    out = []
    for a, cs in cands.items():
        by_i = {cd["i"]: cd for cd in cs if cd["score"] >= score_min
                and _G["rmap"].get((cd["t"] - DAY) // DAY) == "subida"}

        def fn(c4, by_i=by_i):
            cd = by_i.get(len(c4) - 1)
            return cd and recuo_plano(cd["plan"], cd["score"])
        out += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, "P2", fn)]
    return sorted(out, key=lambda t: t["t"])


def main(folder, dest, cache=None):
    assert AR.PB.SLIP_PCT == SLIP          # generic_trades: 0,1% por lado
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    reg, above = B.regimes(btc), AR.btc_above(btc)
    _G.update(rmap=AR.regime_by_day(btc))
    cfg = config.load()
    if cache and os.path.exists(cache):
        cands = pickle.load(open(cache, "rb"))
    else:
        alts = sorted(a for a in bars if a != "BTC")
        with Pool(2, initializer=_init, initargs=(bars, reg)) as p:
            cands = dict(p.map(_cands, alts, chunksize=1))
        if cache:
            pickle.dump(cands, open(cache, "wb"))
    end = max(x["t"] for x in btc) + H4
    rmap = _G["rmap"]
    l0 = end - 365 * DAY
    grid = {"P0": lambda: ring_trades(cands, bars, cfg, above, None, cfg["min_score"]),
            "P1": lambda: ring_trades(cands, bars, cfg, above, ("subida",), cfg["min_score"]),
            "P2": lambda: fighter_trades(cands, bars, above, cfg["min_score"]),
            "P3": lambda: ring_trades(cands, bars, cfg, above, ("lateral",), cfg["min_score"]),
            "P4": lambda: ring_trades(cands, bars, cfg, above, ("subida",), 0)}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "slip_pct": SLIP, "janelas": {}}
    for key, f in grid.items():
        trs = f()
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "A_limpa": [t for t in trs if B_END <= t["t"] < l0],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= l0]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        for k, x in res["janelas"][key].items():
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        with open(dest, "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
