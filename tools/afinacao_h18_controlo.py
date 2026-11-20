"""Afinacao H18 (2026-11-20): o acaso do ringue (arena.control_rs, +-90 velas
a volta do sinal) favorece o momento e castiga a sobrevenda?

Os lutadores nao mudam (TURTLE, SHORT_TURTLE; informativos BOUNCE_X30 =
AR.sig_x30, com a saida G0, e SHORT_X30). So muda o controlo ao acaso:
  S  atual: entradas em [i-90, i+90] (arena.control_rs)
  F  so para a frente: entradas em [i+1, i+90]
  U  incondicional: entrada uniforme em qualquer vela da moeda dentro da
     janela avaliada, sem ligacao a data do sinal
A gestao da operacao de controlo e a mesma de arena.control_rs.
Grelha e criterios escritos antes de testar (backtest/afinacao.md, H18).

Uso: python -m tools.afinacao_h18_controlo <pasta_history> <saida.json>
"""
import bisect
import calendar
import json
import random
import sys

from engine import arena, backtest as B, short as SH, trade
from tools import arena_ringue as AR

DAY, H4 = AR.DAY, AR.H4
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2024, 10, 11, 0, 0, 0))
REPS = 200
LUTADORES = {               # chave: (lado, funcao)
    "TURTLE": ("L", AR.sig_turtle),
    "SHORT_TURTLE": ("S", AR.SHORT_SIGS["SHORT_TURTLE"]),
    "BOUNCE_X30": ("L", AR.sig_x30),          # informativo (sobrevenda)
    "SHORT_X30": ("S", AR.SHORT_SIGS["SHORT_X30"]),   # informativo
}
CANDIDATOS = ("TURTLE", "SHORT_TURTLE")
CAUDA = 600                 # velas passadas a cada sinal (o ringue ao vivo usa ~500-1000)


def cauda(fn, n=CAUDA):
    """So as ultimas n velas fechadas: evita o custo quadratico em 5 anos."""
    return lambda c4: fn(c4[-n:])


def faixa(c4, t_entry, modo, w0, w1):
    """(lo, hi) das velas onde o controlo pode entrar, ou None."""
    ts = [b["t"] for b in c4]
    i = bisect.bisect_right(ts, t_entry) - 1
    if i < 0:
        return None
    last = len(c4) - 2
    if modo == "S":
        lo, hi = max(0, i - arena.WINDOW), min(last, i + arena.WINDOW)
    elif modo == "F":
        lo, hi = i + 1, min(last, i + arena.WINDOW)
    else:                                   # U: toda a janela avaliada
        lo = bisect.bisect_left(ts, w0)
        hi = min(last, bisect.bisect_left(ts, w1) - 1)
    return (lo, hi) if lo <= hi else None


def controlo(c4, t_entry, geo, rng, modo, w0, w1, reps=REPS):
    """Igual a arena.control_rs, mudando so a faixa de entradas."""
    f = faixa(c4, t_entry, modo, w0, w1)
    if not f:
        return []
    out = []
    for _ in range(reps):
        j = rng.randint(*f)
        b = c4[j]
        e = b["o"]
        plan = {"stop": e * (1 + geo["stop"]), "partials": geo["partials"],
                "tp": [e * (1 + x) for x in geo["tp"]],
                "max_hold_s": geo.get("max_hold_s"), "no_react_s": geo.get("no_react_s"),
                "trail_r": geo.get("trail_r")}
        pos = trade.open_position(plan, e, b["t"], arena.FEE_PCT, arena.SLIP_PCT,
                                  breakeven=geo["breakeven"], side="LONG")
        k = j
        while not pos["closed"] and k < len(c4) and k - j <= arena.MAX_BARS:
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            k += 1
        if pos["closed"]:
            out.append(round(pos["r"], 3))
    return out


def julgar(trs, bars, modo, w0, w1, seed=7):
    rng = random.Random(seed)
    rs = [t["r"] for t in trs]
    if not rs:
        return {"n": 0}
    lists = [controlo(bars[t["asset"]], t["t"], t["geo"], rng, modo, w0, w1) for t in trs]
    ls = [c for c in lists if c]
    mean = sum(rs) / len(rs)
    out = {"n": len(rs), "avg_r": round(mean, 3), "com_controlo": len(ls)}
    if len(ls) < max(1, len(rs) // 2):
        return out
    means = sorted(sum(rng.choice(c) for c in ls) / len(ls) for _ in range(1000))
    out.update(acaso_mediana=round(means[500], 3), acaso_p95=round(means[949], 3),
               percentil=round(100 * sum(1 for m in means if m < mean) / 1000, 1))
    return out


def operacoes(lado, fn, key, bars, mbars, above, always, t0):
    out = []
    for a in sorted(bars):
        if a == "BTC":
            continue
        if lado == "L":
            out += [t for _, t in AR.generic_trades(a, bars[a], above, t0, key, cauda(fn))]
        else:
            for _, t in AR.generic_trades(a, mbars[a], always, t0, key, cauda(fn)):
                t = dict(t, side="SHORT")
                j = AR.juros_short_r(t, AR.JUROS_MARGEM_DIA_PCT)
                out.append(dict(t, r=t["r"] - j))
    return sorted(out, key=lambda t: t["t"])


def passa(j, nmin):
    return bool(j.get("n", 0) >= nmin and j["avg_r"] > 0 and j.get("acaso_p95") is not None
                and j["avg_r"] > j["acaso_p95"])


def main(folder, dest):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    always = {k: True for k in above}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    jan = {"L": (end - 365 * DAY, end), "C": (end - 90 * DAY, end), "B": (B_START, B_END)}
    res = {"moedas": len(bars), "fim": end, "lutadores": {}}
    for key, (lado, fn) in LUTADORES.items():
        trs = operacoes(lado, fn, key, bars, mbars, above, always, B_START)
        jb = bars if lado == "L" else mbars
        r = res["lutadores"][key] = {}
        for w, (w0, w1) in jan.items():
            sub = [t for t in trs if w0 <= t["t"] < w1]
            r[w] = {m: julgar(sub, jb, m, w0, w1) for m in "SFU"}
            if w == "L":
                for rg in ("subida", "lateral", "queda"):
                    s2 = [t for t in sub if rmap.get((t["t"] - DAY) // DAY) == rg]
                    r["L_" + rg] = {m: julgar(s2, jb, m, w0, w1) for m in "SFU"}
            print(key, w, json.dumps(r[w]), flush=True)
        for rg in ("subida", "lateral", "queda"):
            print(key, "L", rg, json.dumps(r["L_" + rg]), flush=True)
    # criterios pre-registados
    ver = {}
    for key in CANDIDATOS:
        r = res["lutadores"][key]
        ok = all(passa(r["L"][m], 30) and passa(r["B"][m], 30) for m in "FU") \
            and passa(r["L_lateral"]["U"], 20)
        ver[key] = ok
    def med(k, w, m):
        return res["lutadores"][k][w][m].get("acaso_mediana")
    vies = all(med(k, w, "S") is not None and med(k, w, "U") is not None and med(k, w, "S") > med(k, w, "U")
               for k in CANDIDATOS for w in ("L", "B")) and \
        all(med("BOUNCE_X30", w, "S") < med("BOUNCE_X30", w, "U") for w in ("L", "B"))
    res["veredicto"] = {"correcao_passa": ver, "vies_provado": vies}
    print(json.dumps(res["veredicto"]))
    json.dump(res, open(dest, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
