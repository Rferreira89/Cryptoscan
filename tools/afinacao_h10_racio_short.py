"""Afinacao H10 (2026-10-28): short do racio moeda/BTC esticado, so na queda
(SHORT_RACIO). Espelho da R4 da H9.

Corre no ESPELHO (velas 1/preco), como todos os shorts do ringue. Racio do
espelho = fecho do espelho x fecho real do BTC (= 1 / racio real). Sinal: z do
racio do espelho na vela anterior <= -Z, racio do espelho a virar para cima e
espelho a fechar acima do fecho anterior (preco real a cair); RSI 4H do
espelho >= 35 (RSI real <= 65, fora da sobrecompra); fase do BTC em queda
(ou fora da subida, na Q6). Stop a k ATR, objetivo no preco que devolve o
racio a media. So velas fechadas. Grelha escrita antes de testar
(afinacao.md, H10).

Uso: python -m tools.afinacao_h10_racio_short <pasta_history> <saida.json> [Q1 Q2 ...]
"""
import json
import random
import sys
import time

from engine import backtest as B, paper_bounce as PB, short as SH
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random
from tools.afinacao_h09_racio import B_END, B_START, btc_close, corr_diaria

DAY, H4 = AR.DAY, AR.H4

# nome: (N velas, Z, k ATR, dias, RSI minimo do espelho ou None, fases do BTC)
GRID = {
    "Q1": (120, 2.5, 2.0, 3, 35, ("queda",)),
    "Q2": (120, 2.0, 2.0, 3, 35, ("queda",)),
    "Q3": (120, 2.5, 3.0, 5, 35, ("queda",)),
    "Q4": (120, 2.5, 2.0, 3, None, ("queda",)),
    "Q5": (60, 2.5, 2.0, 3, 35, ("queda",)),
    "Q6": (120, 2.5, 2.0, 3, 35, ("queda", "lateral")),
}

# episodios de queda da janela A (regime_by_day do BTC), para o criterio
EPISODIOS_A = {"nov-dez 2025": (1763251200, 1765670400),     # 2025-11-16 .. 2025-12-14
               "fev-mar 2026": (1769817600, 1772582400),     # 2026-01-31 .. 2026-03-04
               "jun 2026": (1780272000, 1782950400)}         # 2026-06-01 .. 2026-07-02


def racio_m_z(m4, n):
    """(z da vela anterior, racio anterior, racio atual, media) do racio do
    espelho (fecho do espelho x fecho real do BTC), ou None."""
    if len(m4) < n + 2:
        return None
    rs = []
    for x in m4[-(n + 1):]:
        b = btc_close(x["t"])
        if not b:
            return None
        rs.append(x["c"] * b)
    base = rs[:-1]
    m = sum(base) / n
    sd = (sum((v - m) ** 2 for v in base) / n) ** 0.5
    if sd <= 0:
        return None
    return (base[-1] - m) / sd, base[-1], rs[-1], m


def racio_short(n, z, k, days, rsi_min=35, fases=("queda",)):
    """Funcao de sinal de short no espelho (formato SHORT_SIGS)."""
    def f(m4):
        if len(m4) < max(n + 2, 120) or not m4[-1]["c"] > m4[-2]["c"]:
            return None
        if AR._fase_btc(m4[-1]["t"] + H4) not in fases:
            return None
        q = racio_m_z(m4, n)
        if not q:
            return None
        z0, r0, r1, m = q
        if z0 > -z or not r1 > r0:
            return None
        w = m4[-200:]
        if rsi_min is not None:
            rs = PB.rsi([x["c"] for x in w])[-1]
            if rs is None or rs < rsi_min:
                return None
        at = PB.atr(w[-100:])[-1]
        if at is None:
            return None
        e = m4[-1]["c"]
        stop = e - k * at
        if stop <= 0 or not 0.005 <= 1 - stop / e <= 0.20:
            return None
        tp = e * m / r1
        if tp < e * 1.01:
            return None
        return {"stop": stop, "tp": [tp], "partials": [100], "breakeven": True,
                "hold_s": days * DAY, "atr": at,
                "gatilho": f"rácio com o BTC {-z0:.1f} desvios acima da média a virar para baixo, BTC em queda"}
    return f


def summary(trs, bars, rmap, seed=7):
    if not trs:
        return {"n": 0}
    j = AR.judge(trs, bars, random.Random(seed))
    j["percentil_acaso"] = pct_vs_random(trs, bars)
    by_a, years = {}, {}
    for t in trs:
        by_a.setdefault(t["asset"], []).append(t["r"])
        years.setdefault(time.gmtime(t["t"]).tm_year, []).append(t["r"])
    best = max(by_a, key=lambda a: sum(by_a[a]))
    rest = [t["r"] for t in trs if t["asset"] != best]
    j.update(sem_melhor=best, avg_sem_melhor=round(sum(rest) / len(rest), 3) if rest else None,
             anos={y: [len(v), round(sum(v) / len(v), 3)] for y, v in sorted(years.items())},
             por_regime={})
    for rg in ("subida", "lateral", "queda"):
        sub = [t for t in trs if rmap.get((t["t"] - DAY) // DAY) == rg]
        if sub:
            s = AR.judge(sub, bars, random.Random(seed))
            j["por_regime"][rg] = {k: s[k] for k in ("n", "avg_r", "acaso_mediana", "acaso_p95")}
            j["por_regime"][rg]["percentil_acaso"] = pct_vs_random(sub, bars)
    return j


def episodios(trs):
    out = {}
    for nome, (a, b) in EPISODIOS_A.items():
        rs = [t["r"] for t in trs if a <= t["t"] < b + 3 * DAY]
        out[nome] = [len(rs), round(sum(rs) / len(rs), 3) if rs else None]
    return out


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    always = {k: True for k in AR.btc_above(btc)}            # shorts: sem filtro do BTC
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    iso = []
    for a in sorted(bars):
        if a != "BTC":
            iso += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, "SISO",
                                                    AR.sig_short_isolada)]
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            trs += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, key,
                                                    racio_short(*cfg))]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, mbars, rmap) for k, v in w.items()}
        res["janelas"][key]["episodios_A"] = episodios(w["A"])
        res["janelas"][key]["corr_short_isolada"] = {
            "B": corr_diaria(w["B"], [t for t in iso if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in iso if t["t"] >= B_END])}
        for k in ("B", "A", "C90", "L365"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor",
                                                 "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        print(key, "episodios A", res["janelas"][key]["episodios_A"],
              "corr", res["janelas"][key]["corr_short_isolada"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
