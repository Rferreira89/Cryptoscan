"""Afinacao H12 (2026-11-02): short da quebra do minimo de N velas de 4H na
lateral, no metodo do ringue (SHORT_MIN55). Pista do estudo H29.

Corre no ESPELHO (velas 1/preco), como todos os shorts do ringue: no espelho
o sinal e o fecho acima do maximo dos maximos das N velas anteriores (= fecho
real abaixo do minimo dos minimos). Stop a 2 ATR(42) de 4H, objetivo unico a
k R, saida por tempo ao fim de D dias. Fase do BTC (AR._fase_btc, a do ringue,
ou papel_fases.fase, a do H29) nas fases dadas. So velas fechadas. Grelha
escrita antes de testar (afinacao.md, H12).

Uso: python -m tools.afinacao_h12_short_min55 <pasta_history> <saida.json> [S1 S2 ...]
("TUR" calcula as operacoes da SHORT_TURTLE em TUR_CACHE; sem elas a correlacao fica None)
"""
import json
import random
import sys

from engine import backtest as B, paper_bounce as PB, papel_fases as PF, short as SH, trade
from tools import arena_ringue as AR
from tools.afinacao_h09_racio import B_END, B_START, corr_diaria
from tools.afinacao_h10_racio_short import summary

DAY, H4 = AR.DAY, AR.H4
ATR_N = 42
TUR_CACHE = "/tmp/afinacao_h12_short_turtle.json"

# nome: (N velas, objetivo em R, dias, fases, definicao da fase)
GRID = {
    "S1": (55, 2.0, 3, ("lateral",), "ringue"),
    "S2": (55, 2.0, 3, ("lateral",), "h29"),
    "S3": (55, 2.0, 3, ("lateral", "queda"), "ringue"),
    "S4": (120, 2.0, 3, ("lateral",), "ringue"),
    "S5": (55, 1.5, 3, ("lateral",), "ringue"),
    "S6": (55, 2.0, 5, ("lateral",), "ringue"),
}

_H29 = {}


def fase_h29(t):
    """Fase do H29 / papel_fases com os dias fechados do BTC ate t."""
    src = AR.CTX.get("btc") or []
    key = (id(src), len(src), t // DAY)
    if key not in _H29:
        if len(_H29) > 5000:
            _H29.clear()
        _H29[key] = PF.NOMES.get(PF.fase(B.daily(src), t))
    return _H29[key]


def atr_n(m4, n=ATR_N):
    """ATR simples de n velas (como no H29 e em papel_fases), so velas fechadas."""
    if len(m4) < n + 1:
        return None
    w = m4[-(n + 1):]
    tr = [max(w[i]["h"], w[i - 1]["c"]) - min(w[i]["l"], w[i - 1]["c"]) for i in range(1, len(w))]
    return sum(tr) / n


def short_min(n=55, k=2.0, days=3, fases=("lateral",), defin="ringue"):
    """Funcao de sinal de short no espelho (formato SHORT_SIGS)."""
    def f(m4):
        if len(m4) < max(n, ATR_N) + 2:
            return None
        b = m4[-1]
        nivel = max(x["h"] for x in m4[-n - 1:-1])           # = minimo real das N anteriores
        if not b["c"] > nivel:
            return None
        t = b["t"] + H4
        fz = AR._fase_btc(t) if defin == "ringue" else fase_h29(t)
        if fz not in fases:
            return None
        at = atr_n(m4)
        if not at:
            return None
        e = b["c"]
        stop = e - 2 * at
        if stop <= 0 or not 0.005 <= 1 - stop / e <= 0.25:
            return None
        return {"stop": stop, "tp": [e + k * (e - stop)], "partials": [100], "breakeven": True,
                "hold_s": days * DAY, "atr": at,
                "gatilho": f"quebra do mínimo de {n} velas de 4H ({1 / nivel:.6g}) com o mercado lateral"}
    return f


def trades_com_fim(asset, c4, above, t0, key, fn):
    """AR.generic_trades com a hora de fecho (para a simulacao da conta).
    Mesma logica, linha a linha; so acrescenta t_fim."""
    AR.CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if i < busy or t_sig < t0 or not AR._known(t_sig, above):
            continue
        sig = fn(c4[:i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]
        if not (sig["stop"] < px < sig["tp"][0]):
            continue
        pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"], PB.FEE_PCT,
                                  PB.SLIP_PCT, breakeven=True)
        k = i + 1
        fim = None
        while not pos["closed"] and k < len(c4):
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H4)
            if pos["closed"]:
                fim = x["t"] + H4
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append({"asset": asset, "t": pos["opened_at"], "t_fim": fim, "r": pos["r"],
                    "geo": {"stop": sig["stop"] / px - 1, "tp": [x / px - 1 for x in sig["tp"]],
                            "partials": list(sig["partials"]), "breakeven": True,
                            "max_hold_s": sig["hold_s"], "no_react_s": None, "trail_r": None}})
    return out


def conta(trs, t_a, t_b, slots=1, reps=50, juro=0.20, seed=11):
    """Conta com o valor todo dividido por `slots` posicoes; com varios sinais
    ao mesmo tempo escolhe ao acaso; juros compostos; juro do emprestimo do
    short 20%/ano. Devolve (fator mediano, queda maxima mediana, ops)."""
    sub = sorted([t for t in trs if t_a <= t["t"] < t_b], key=lambda t: (t["t"], t["asset"]))
    if not sub:
        return None
    facs, dds, ns = [], [], []
    for r in range(reps):
        rng = random.Random(seed + r)
        eq, pico, dd, livres, n = 1.0, 1.0, 0.0, [], 0
        grupos = {}
        for t in sub:
            grupos.setdefault(t["t"], []).append(t)
        for tt in sorted(grupos):
            livres = [x for x in livres if x > tt]
            g = grupos[tt][:]
            rng.shuffle(g)
            for t in g:
                if len(livres) >= slots:
                    break
                ret = t["r"] * abs(t["geo"]["stop"]) - juro * (t["t_fim"] - t["t"]) / DAY / 365
                eq *= 1 + ret / slots
                livres.append(t["t_fim"])
                n += 1
                pico = max(pico, eq)
                dd = max(dd, 1 - eq / pico)
        facs.append(eq)
        dds.append(dd)
        ns.append(n)
    facs.sort()
    dds.sort()
    return {"fator": round(facs[len(facs) // 2], 3), "queda_max": round(dds[len(dds) // 2], 3),
            "ops": sorted(ns)[len(ns) // 2]}


def btc_hold(btc, t_a, t_b):
    w = [x for x in btc if t_a <= x["t"] < t_b]
    if len(w) < 2:
        return None
    pico, dd = w[0]["c"], 0.0
    for x in w:
        pico = max(pico, x["c"])
        dd = max(dd, 1 - x["c"] / pico)
    return {"fator": round(w[-1]["c"] / w[0]["o"], 3), "queda_max": round(dd, 3)}


def turtle(bars, mbars, always, cache, build=True):
    """Operacoes da SHORT_TURTLE (referencia dos clones), guardadas em `cache`
    (o sinal das Tartarugas e lento: ~30 s por moeda)."""
    try:
        with open(cache) as f:
            return json.load(f)
    except (OSError, ValueError):
        if not build:
            return None
    tur = []
    for a in sorted(bars):
        if a != "BTC":
            tur += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, "STUR",
                                                    AR.SHORT_SIGS["SHORT_TURTLE"])]
    with open(cache, "w") as f:
        json.dump(tur, f)
    return tur


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    always = {k: True for k in AR.btc_above(btc)}            # shorts: sem filtro do BTC
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {},
           "btc_hold": {"B": btc_hold(btc, B_START, B_END), "A": btc_hold(btc, B_END, end)}}
    tur = turtle(bars, mbars, always, TUR_CACHE, build=only == ["TUR"])
    if only == ["TUR"]:
        return
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            trs += trades_com_fim(a, mbars[a], always, B_START, key, short_min(*cfg))
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, mbars, rmap) for k, v in w.items()}
        res["janelas"][key]["corr_short_turtle"] = None if tur is None else {
            "B": corr_diaria(w["B"], [t for t in tur if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in tur if t["t"] >= B_END])}
        res["janelas"][key]["conta"] = {
            f"{h}_{s}pos": conta(trs, *((B_START, B_END) if h == "B" else (B_END, end)), slots=s)
            for h in ("B", "A") for s in (1, 2)}
        for k in ("B", "A", "C90", "L365"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor",
                                                 "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        print(key, "corr", res["janelas"][key]["corr_short_turtle"],
              "conta", res["janelas"][key]["conta"], "btc", res["btc_hold"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
