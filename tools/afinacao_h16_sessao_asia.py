"""Afinacao H16 (2026-11-13): reverter o movimento da sessao asiatica na
lateral (SESSAO_ASIA, compra; SHORT_SESSAO_ASIA, short).

Sazonalidade intradiaria. Sessao asiatica = 00:00 a 08:00 UTC (as velas de
4H com abertura 00:00 e 04:00); o sinal so se avalia na vela que fecha as
08:00 UTC. Movimento = fecho das 08:00 / abertura das 00:00 - 1. Fase do BTC
(_fase_btc, dia fechado anterior) = lateral. Compra a queda / short a subida;
objetivo na abertura da sessao, stop no extremo da sessao -+ 0,5 ATR(14) 4H,
saida por tempo ao fim de 16 h. Controlos A5/A6 na sessao europeia
(08:00 a 16:00, fecho as 16:00). Grelha escrita antes de testar
(backtest/afinacao.md, H16).

Uso: python -m tools.afinacao_h16_sessao_asia <pasta_history> <saida.json> [A1 A2 ...]
"""
import json
import sys

from engine import backtest as B, paper_bounce as PB, short as SH
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random
from tools.afinacao_h09_racio import B_END, B_START, corr_diaria
from tools.afinacao_h10_racio_short import summary

DAY, H4 = AR.DAY, AR.H4

# nome: (lado, limiar do movimento, hora de fecho da sessao em s)
# lado "L" compra a queda (mov <= -lim); "S" faz short a subida (mov >= +lim)
ASIA, EURO = 8 * 3600, 16 * 3600
GRID = {
    "A1": ("L", -0.03, ASIA),
    "A2": ("S", 0.03, ASIA),
    "A3": ("S", 0.05, ASIA),
    "A4": ("L", -0.05, ASIA),
    "A5": ("L", -0.03, EURO),   # controlo de A1/A4 na sessao europeia
    "A6": ("S", 0.03, EURO),    # controlo de A2/A3 na sessao europeia
}


def sessao_sig(lado, lim, fecho_s):
    """Funcao de sinal (formato NEW_SIGS / SHORT_SIGS), so velas fechadas.

    Nas velas espelho (short) os precos vem invertidos (SH.mirror): uma
    subida real vira queda no espelho, por isso o lado "S" procura a mesma
    'queda' no espelho que o "L" procura nos precos reais. Para manter o
    limiar legivel em precos reais, o short aplica -lim ao movimento do
    espelho (equivalente a +lim no real)."""
    def f(c4):
        b = c4[-1]
        if (b["t"] + H4) % DAY != fecho_s or len(c4) < 300:
            return None
        if AR._fase_btc(b["t"] + H4) != "lateral":
            return None
        abr = c4[-2]                       # vela que abre a sessao
        mov = b["c"] / abr["o"] - 1
        if lado == "L":
            if mov > lim:                  # lim negativo: queda forte o suficiente
                return None
        else:
            if -mov > lim:                 # no espelho procura a queda = subida real
                return None
        at = PB.atr(c4[-100:])[-1]
        if not at:
            return None
        lo = min(abr["l"], b["l"])
        e, stop = b["c"], lo - 0.5 * at
        if e - stop <= 0 or not 0.01 <= 1 - stop / e <= 0.10:
            return None
        tp = abr["o"]                      # abertura da sessao
        if tp < e * 1.01:
            return None
        sessao = "asiática" if fecho_s == ASIA else "europeia"
        return {"stop": stop, "tp": [tp], "partials": [100], "breakeven": True,
                "hold_s": 16 * 3600, "atr": at,
                "gatilho": f"reversão do movimento da sessão {sessao} "
                           f"({100 * mov:+.1f}%) com o BTC lateral"}
    return f


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    always = {k: True for k in above}                  # shorts: sem filtro do BTC
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}

    # referencias para a correlacao: BOUNCE_X30 (compras) e SHORT_X30 (shorts)
    ref_l, ref_s = [], []
    for a in sorted(bars):
        if a == "BTC":
            continue
        ref_l += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, "X30", AR.sig_x30)]
        ref_s += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, "SX30",
                                                  AR.SHORT_SIGS["SHORT_X30"])]

    for key, (lado, lim, fecho_s) in GRID.items():
        if only and key not in only:
            continue
        fn = sessao_sig(lado, lim, fecho_s)
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            if lado == "L":
                trs += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, key, fn)]
            else:
                for _, t in AR.generic_trades(a, mbars[a], always, B_START, key, fn):
                    t = dict(t, side="SHORT")
                    j = AR.juros_short_r(t, AR.JUROS_MARGEM_DIA_PCT)
                    trs.append(dict(t, r=t["r"] - j, juros_r=round(j, 4)))
        trs.sort(key=lambda t: t["t"])
        ref = ref_l if lado == "L" else ref_s
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        res["janelas"][key]["corr_x30"] = {
            "B": corr_diaria(w["B"], [t for t in ref if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in ref if t["t"] >= B_END])}
        for k in ("B", "A", "C90", "L365"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor")},
                  flush=True)
        print(key, "corr_x30", res["janelas"][key]["corr_x30"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
