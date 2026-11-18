"""(18/11, investigacao isolada; nada em producao) H18: porque e que o controlo ao acaso da arena da +1,18R a geometria
de SHORT_TURTLE e +0,56R a de TURTLE (mais do que as estrategias)?

Mede, para as MESMAS operacoes (funcao do ringue: AR.generic_trades), varios controlos com a mesma geometria:
  C0  como na arena: entrada ao acaso em +-90 velas de 4H a volta da entrada real (inclui velas DEPOIS da entrada);
  C1  C0 + juros da margem nos shorts (as operacoes reais ja os descontam; o controlo da arena nao);
  C2  so o passado: entrada ao acaso nas 90 velas ANTES da entrada real;
  C3  neutro a tendencia: entrada ao acaso em TODO o historico da moeda (mesma geometria, com juros nos shorts).
Se C0 >> C3, o controlo da arena esta a apanhar a tendencia da janela (beta), nao a mostrar que a entrada e ma.
Uso: python -m tools.investigacao_h18_controlo <pasta_history> <saida.json>"""
import bisect
import json
import random
import statistics
import sys

from engine import arena, backtest as B, short as SH, trade
from tools import arena_ringue as AR

H4, DAY = 4 * 3600, 86400


def controlo(c4, j_lo, j_hi, geo, rng, reps, juros_dia_pct=0.0):
    out = []
    j_hi = min(j_hi, len(c4) - 2)
    if j_hi < j_lo:
        return out
    for _ in range(reps):
        j = rng.randint(j_lo, j_hi)
        b = c4[j]
        e = b["o"]
        plan = {"stop": e * (1 + geo["stop"]), "partials": geo["partials"], "tp": [e * (1 + x) for x in geo["tp"]],
                "max_hold_s": geo.get("max_hold_s"), "no_react_s": geo.get("no_react_s"), "trail_r": geo.get("trail_r")}
        pos = trade.open_position(plan, e, b["t"], arena.FEE_PCT, arena.SLIP_PCT, breakeven=geo["breakeven"], side="LONG")
        k = j
        while not pos["closed"] and k < len(c4) and k - j <= arena.MAX_BARS:
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            k += 1
        if pos["closed"]:
            r = pos["r"]
            if juros_dia_pct:
                dur = (pos.get("closed_at") or b["t"]) - b["t"]
                r -= juros_dia_pct / 100 * max(0, dur) / DAY / abs(geo["stop"])
            out.append(r)
    return out


def medir(trs, bars, juros, rng, reps=30):
    res = {k: [] for k in ("real", "C0", "C1", "C2", "C3")}
    for t in trs:
        c4 = bars[t["asset"]]
        ts = [b["t"] for b in c4]
        i = bisect.bisect_right(ts, t["t"]) - 1
        if i < 0 or not t.get("geo"):
            continue
        res["real"].append(t["r"])
        lo, hi = max(0, i - arena.WINDOW), i + arena.WINDOW
        for k, (a, b, jr) in {"C0": (lo, hi, 0.0), "C1": (lo, hi, juros), "C2": (lo, i - 1, juros),
                              "C3": (60, len(c4) - 2, juros)}.items():
            cs = controlo(c4, a, b, t["geo"], rng, reps, jr)
            if cs:
                res[k].append(statistics.mean(cs))
    return {k: {"n": len(v), "r_medio": round(statistics.mean(v), 4) if v else None} for k, v in res.items()}


def main(folder, dest):
    bars, _ = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    above = AR.btc_above(btc)
    always = {k: True for k in above}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    juros = AR.JUROS_MARGEM_DIA_PCT
    rng = random.Random(18)
    t0 = end - 365 * DAY   # (desempenho) so o ultimo ano; o sinal usa o historico todo para aquecer
    out = {"fim": end, "moedas": len(bars), "juros_margem_dia_pct": juros, "resultados": {}}
    for nome, lado, fn, jb in (("TURTLE", "L", AR.sig_turtle, bars), ("SHORT_TURTLE", "S", AR.SHORT_SIGS["SHORT_TURTLE"], mbars)):
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            src = bars[a] if lado == "L" else mbars[a]
            for _, t in AR.generic_trades(a, src, above if lado == "L" else always, t0, nome, fn):
                if lado == "S":
                    t = dict(t, r=t["r"] - AR.juros_short_r(t, juros))
                trs.append(t)
        trs.sort(key=lambda t: t["t"])
        print(nome, len(trs), "operacoes", flush=True)
        jr = juros if lado == "S" else 0.0
        janelas = {"90d": [t for t in trs if t["t"] >= end - 90 * DAY], "365d": trs}
        out["resultados"][nome] = {j: medir(v, jb, jr, rng) for j, v in janelas.items()}
        print(nome, json.dumps(out["resultados"][nome]), flush=True)
        with open(dest, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
