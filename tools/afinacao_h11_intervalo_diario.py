"""Afinacao H11 (2026-10-30): reversao do intervalo no diario, so na lateral
(INTERVALO_DIARIO).

Diario agregado das velas de 4H fechadas (AR._diario); o sinal so se avalia
na vela de 4H que fecha o dia UTC. Intervalo = as N velas diarias ANTERIORES
a de hoje, largura 10% a 40%; ADX(14) diario < A; fecho de hoje no terco
inferior e nao abaixo do minimo do intervalo; gatilho: fecho acima do maximo
(ou do fecho) de ontem. Stop no minimo (intervalo ou hoje) - 0,5 ATR diario,
distancia 1% a 15%; objetivo no meio do intervalo (>= 1,5%); saida por tempo.
Fase do BTC (AR._fase_btc) nas fases dadas. Grelha escrita antes de testar
(afinacao.md, H11).

Uso: python -m tools.afinacao_h11_intervalo_diario <pasta_history> <saida.json> [R1 R2 ...]
"""
import json
import random
import sys

from engine import backtest as B, indicators as I, paper_bounce as PB
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random
from tools.afinacao_h09_racio import B_END, B_START, corr_diaria
from tools.afinacao_h10_racio_short import summary

DAY, H4 = AR.DAY, AR.H4

# nome: (N dias, ADX maximo, gatilho, dois objetivos, dias, fases do BTC)
GRID = {
    "R1": (30, 20, "maximo", False, 10, ("lateral",)),
    "R2": (30, 20, "fecho", False, 10, ("lateral",)),
    "R3": (20, 20, "maximo", False, 10, ("lateral",)),
    "R4": (30, 25, "maximo", False, 10, ("lateral",)),
    "R5": (30, 20, "maximo", True, 15, ("lateral",)),
    "R6": (30, 20, "maximo", False, 10, ("subida", "lateral")),
}


def intervalo_diario(n=30, adx_max=20, gatilho="maximo", dois=False, days=10,
                     fases=("lateral",), larg=(0.10, 0.40)):
    """Funcao de sinal de compra (formato NEW_SIGS), so velas fechadas."""
    def f(c4):
        if len(c4) < 6 * (n + 60) or (c4[-1]["t"] + H4) % DAY:
            return None                                  # so na vela que fecha o dia
        if AR._fase_btc(c4[-1]["t"] + H4) not in fases:
            return None
        d = AR._diario(c4[-6 * (n + 70):])
        if len(d) < n + 40 or d[-1]["t"] + DAY != c4[-1]["t"] + H4:
            return None
        hoje, ontem, rng = d[-1], d[-2], d[-n - 1:-1]
        hi, lo = max(x["h"] for x in rng), min(x["l"] for x in rng)
        if lo <= 0 or not larg[0] <= hi / lo - 1 <= larg[1]:
            return None
        ad = I.adx(d[-80:])[-1]
        at = PB.atr(d[-80:])[-1]
        if ad is None or at is None or ad >= adx_max:
            return None
        c, w = hoje["c"], hi - lo
        if not lo <= c <= lo + w / 3:
            return None
        if not c > (ontem["h"] if gatilho == "maximo" else ontem["c"]):
            return None
        stop = min(lo, hoje["l"]) - 0.5 * at
        if stop <= 0 or not 0.01 <= 1 - stop / c <= 0.15:
            return None
        tp1, tp2 = lo + w / 2, lo + 2 * w / 3
        if tp1 < c * 1.015:
            return None
        return {"stop": stop, "tp": [tp1, tp2] if dois else [tp1],
                "partials": [50, 50] if dois else [100], "breakeven": True,
                "hold_s": days * DAY, "atr": at,
                "gatilho": f"intervalo de {n} dias (largura {100 * (hi / lo - 1):.0f}%, ADX diário "
                           f"{ad:.0f}): terço inferior a virar para cima, BTC lateral"}
    return f


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    ref = []
    for a in sorted(bars):
        if a != "BTC":
            ref += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, "X30", AR.sig_x30)]
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            trs += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, key,
                                                    intervalo_diario(*cfg))]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        res["janelas"][key]["corr_bounce_x30"] = {
            "B": corr_diaria(w["B"], [t for t in ref if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in ref if t["t"] >= B_END])}
        for k in ("B", "A", "C90", "L365"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor",
                                                 "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        print(key, "corr", res["janelas"][key]["corr_bounce_x30"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
