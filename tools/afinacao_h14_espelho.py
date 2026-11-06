"""Afinacao H14 (2026-11-06): vies do espelho nos shorts do ringue.

O ringue avalia os shorts no ESPELHO (velas 1/preco). Ao vivo o short executa
nos niveis do espelho convertidos para preco real (tools/arena_ringue.short_live).
Aqui cada sinal do espelho e simulado das duas formas:
  (a) no espelho, exatamente como AR.generic_trades;
  (b) em preco real com engine/trade side="SHORT" (mesmos niveis convertidos,
      entrada na abertura seguinte, comissao e slippage do ringue);
  (c) (b) menos o juro do emprestimo (20%/ano sobre o valor, toda a duracao).
Acaso: (a) contra entradas ao acaso no espelho; (b) contra shorts reais ao acaso
com a geometria real (arena.control_rs side="SHORT").
Grelha escrita antes de testar (afinacao.md, H14). Nao e um sinal novo.

Uso: python -m tools.afinacao_h14_espelho <pasta_history> <saida.json> [M1 M2 ...]
"""
import bisect
import calendar
import json
import random
import sys

from engine import arena, backtest as B, paper_bounce as PB, short as SH, trade
from tools import arena_ringue as AR

DAY, H4 = AR.DAY, AR.H4
JURO = 0.20
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2024, 10, 11, 0, 0, 0))
GRID = {"M1": "SHORT_X30", "M2": "SHORT_ISOLADA", "M3": "SHORT_FALSO_ROMP", "M4": "SHORT_TURTLE"}
REGIME_PRINCIPAL = {"M1": "queda", "M2": "queda", "M3": "queda", "M4": "lateral"}


# ---------- B.daily rapido (mesmo resultado: so dias completos ate a vela) ----------
_FULL = {}


def registar_diario(series):
    """Guarda o diario completo de uma serie (real ou espelho)."""
    if series:
        _FULL[(series[0]["t"], series[0]["o"])] = (B.daily(series), None)


_daily_orig = B.daily


def daily_rapido(c4):
    full = _FULL.get((c4[0]["t"], c4[0]["o"])) if c4 else None
    if full is None:
        return _daily_orig(c4)
    d, _ = full
    ts = [x["t"] for x in d]
    k = bisect.bisect_right(ts, c4[-1]["t"] + H4 - DAY)
    return d[:k]


# ---------- simulacao ----------

def _sim(plan, px, t_open, bars, i0, hold_s, side):
    pos = trade.open_position(dict(plan, max_hold_s=None), px, t_open, PB.FEE_PCT,
                              PB.SLIP_PCT, breakeven=True, side=side)
    k = i0
    while not pos["closed"] and k < len(bars):
        x = bars[k]
        trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
        if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= hold_s:
            d = 1 if side == "LONG" else -1
            trade._sell(pos, pos["remaining"], x["c"] * (1 - d * pos["slip"]))
            trade._finish(pos, "TIME", x["t"] + H4)
        k += 1
    return pos, k


def juro_r(pos):
    """Juro do emprestimo em R (sobre o valor de entrada, toda a duracao: conservador)."""
    horas = (pos["closed_at"] - pos["opened_at"]) / 3600
    return JURO * horas / (365 * 24) * pos["entry"] / pos["risk_unit"]


def pares_trades(asset, real, m4, t0, key, fn):
    """Como AR.generic_trades no espelho (sem filtro do BTC), com a mesma operacao
    tambem simulada em preco real."""
    AR.CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(m4) - 1):
        t_sig = m4[i]["t"] + H4
        if i < busy or t_sig < t0:
            continue
        sig = fn(m4[:i + 1])
        if not sig:
            continue
        pm = m4[i + 1]["o"]
        if not (sig["stop"] < pm < sig["tp"][0]):
            continue
        pos_m, k = _sim(sig, pm, m4[i + 1]["t"], m4, i + 1, sig["hold_s"], "LONG")
        if not pos_m["closed"]:
            continue
        busy = k
        px = real[i + 1]["o"]
        plan_r = dict(sig, stop=1 / sig["stop"], tp=[1 / x for x in sig["tp"]])
        pos_r, _ = _sim(plan_r, px, real[i + 1]["t"], real, i + 1, sig["hold_s"], "SHORT")
        if not pos_r["closed"]:
            continue
        geo = {"partials": list(sig["partials"]), "breakeven": True, "max_hold_s": sig["hold_s"],
               "no_react_s": sig.get("no_react_s"), "trail_r": sig.get("trail_r")}
        jr = juro_r(pos_r)
        out.append({"asset": asset, "t": pos_m["opened_at"], "r": pos_m["r"],
                    "r_real": pos_r["r"], "r_real_juro": round(pos_r["r"] - jr, 3),
                    "juro_r": round(jr, 4), "horas": (pos_r["closed_at"] - pos_r["opened_at"]) / 3600,
                    "geo": dict(geo, stop=sig["stop"] / pm - 1, tp=[x / pm - 1 for x in sig["tp"]]),
                    "geo_real": dict(geo, stop=plan_r["stop"] / px - 1, tp=[x / px - 1 for x in plan_r["tp"]])})
    return out


def acaso(trs, src, side, geo_key, r_key, seed=8):
    """(mediana, p95, percentil) do R medio contra controlos ao acaso."""
    lists = [arena.control_rs(src[t["asset"]], t["t"], t[geo_key], side,
                              random.Random(seed + i), reps=AR.REPS) for i, t in enumerate(trs)]
    ls = [c for c in lists if c]
    if not ls:
        return None, None, None
    r2 = random.Random(seed + 2)
    means = sorted(sum(r2.choice(c) for c in ls) / len(ls) for _ in range(1000))
    mean = sum(t[r_key] for t in trs) / len(trs)
    return (round(means[500], 3), round(means[949], 3),
            round(100 * sum(1 for m in means if m < mean) / len(means), 1))


def resumo(trs, bars, mbars):
    if not trs:
        return {"n": 0}
    n = len(trs)
    avg = lambda k, xs=trs: round(sum(t[k] for t in xs) / len(xs), 3)
    h = n // 2
    med_m, p95_m, pc_m = acaso(trs, mbars, "LONG", "geo", "r")
    med_r, p95_r, pc_r = acaso(trs, bars, "SHORT", "geo_real", "r_real")
    return {"n": n, "r_espelho": avg("r"), "r_real": avg("r_real"), "r_real_juro": avg("r_real_juro"),
            "vies": round(avg("r_real") - avg("r"), 3), "juro_medio_r": avg("juro_r"),
            "horas_media": round(sum(t["horas"] for t in trs) / n, 1),
            "stop_medio_pct": round(100 * sum(abs(t["geo_real"]["stop"]) for t in trs) / n, 2),
            "metades_real_juro": [avg("r_real_juro", trs[:h]), avg("r_real_juro", trs[h:])] if h >= 5 else None,
            "acaso_espelho": {"mediana": med_m, "p95": p95_m, "percentil": pc_m},
            "acaso_real": {"mediana": med_r, "p95": p95_r, "percentil": pc_r}}


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    for s in list(bars.values()) + list(mbars.values()):
        registar_diario(s)
    B.daily = daily_rapido                      # so neste estudo (mesmo resultado, mais rapido)
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "lutadores": {}}
    for m, key in GRID.items():
        if only and m not in only:
            continue
        fn = AR.SHORT_SIGS[key]
        trs = []
        for a in sorted(bars):
            if a != "BTC":
                trs += pares_trades(a, bars[a], mbars[a], B_START, key, fn)
        trs.sort(key=lambda t: t["t"])
        out = {}
        jan = {"L365": [t for t in trs if t["t"] >= end - 365 * DAY],
               "B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END]}
        for w, xs in jan.items():
            out[w] = {"todos": resumo(xs, bars, mbars) if w == "L365" else {"n": len(xs)}}
            for rg in ("subida", "lateral", "queda"):
                sub = [t for t in xs if rmap.get((t["t"] - DAY) // DAY) == rg]
                if rg == REGIME_PRINCIPAL[m] or w == "L365":
                    out[w][rg] = resumo(sub, bars, mbars)
        res["lutadores"][m] = {"chave": key, "janelas": out}
        print(m, key, json.dumps({w: {k: (v.get("n"), v.get("r_espelho"), v.get("r_real"), v.get("r_real_juro"),
                                          (v.get("acaso_real") or {}).get("p95"), (v.get("acaso_real") or {}).get("percentil"))
                                      for k, v in o.items()} for w, o in out.items()}), flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    B.daily = _daily_orig


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
