"""Ringue continuo da arena (decisao do Rui, 2026-10-13: "os lutadores nao
estao a morrer").

Problema: ao vivo cada estrategia da 1 a 3 operacoes por semana. Com a
regra de morte a pedir 10 a 20 operacoes, ninguem morria antes de meses.

Solucao: de hora a hora (workflow arena.yml, no GitHub Actions, sem custo
de agentes) cada lutador combate nos ULTIMOS 90 DIAS de mercado, em TODAS
as moedas listadas na Bybit UE, com as MESMAS funcoes do sistema ao vivo
(engine/backtest.candidates e simulate, engine/paper_bounce.signal e plans)
e os mesmos custos. Cada operacao tem controlos ao acaso com a mesma
geometria (engine/arena.control_rs). O resultado ("forma recente") e
escrito em forma.json no ramo `arena` e o scanner junta-o a arena.

Lutadores e regras de selecao (iguais ao que o sistema ao vivo faria):
  PULLBACK, BREAKOUT, LIQUIDITY_SWEEP, RANGE: setups READY com plano,
      confluencia >= min_score e BTC acima da media de 200 dias
  REJEITADOS (Oscar): os mesmos setups com confluencia ABAIXO do minimo,
      ou seja, o que os filtros deitam fora
  BOUNCE_G0/V1/V2/V3: o gatilho e as quatro saidas do papel do Bounce
  TREND_DAILY: tendencia diaria das grandes moedas (sem geometria fixa:
      julgada so pelo R medio)

Limites declarados: os 90 dias sao mercado ja visto por quem desenhou as
estrategias ate ao inicio da janela de reserva; por isso a forma recente
SO PODE MATAR, nunca promover. Subir a dinheiro real continua a exigir 30
operacoes ao vivo (papel ou reais) acima do percentil 95 do acaso.

Uso: python -m tools.arena_ringue <pasta_saida> [dias]
"""
import json
import os
import random
import sys
import time

from engine import arena, backtest as B, config, paper_bounce as PB, paper_trend as PT
from engine import trade

DAYS = 90
H4, DAY = B.H4, B.DAY
NEED_BARS = 6 * (B.analysis.MIN_BARS + 15) + 6 * DAYS   # aquecer o diario
LIVE = ("PULLBACK", "BREAKOUT", "LIQUIDITY_SWEEP", "RANGE")
REPS = 200


def closed(rows, now):
    """Velas de 4H ja fechadas (a Binance devolve a vela em curso no fim)."""
    return [r for r in rows if r["t"] + H4 <= now]


def fetch(base, now):
    from tools import fetch_history as FH
    start = (now - (NEED_BARS + 12) * H4) * 1000
    raw = FH.history(base, "4h", start)
    rows = [{"t": r[0] // 1000, "o": float(r[1]), "h": float(r[2]),
             "l": float(r[3]), "c": float(r[4]), "v": float(r[5]),
             "tb": float(r[9])} for r in raw]
    return closed(rows, now)


def btc_above(btc4):
    """{dia: BTC acima da SMA200 no fecho desse dia}."""
    d = B.daily(btc4)
    out = {}
    for k in range(199, len(d)):
        sma = sum(x["c"] for x in d[k - 199:k + 1]) / 200
        out[d[k]["t"] // DAY] = d[k]["c"] > sma
    return out


def _known(t, above):
    """Filtro de mercado conhecido no instante t (fecho do dia anterior)."""
    return above.get((t - DAY) // DAY)


# ---------- estrategias de 4H do sistema ao vivo ----------

def live_trades(asset, c4, reg, above, cfg, t0):
    out = []
    for cd in B.candidates(asset, c4, reg, cfg, start_t=t0):
        ok_mkt = _known(cd["t"], above)
        if not ok_mkt and cfg.get("require_btc_above_sma200"):
            continue
        res = B.simulate(cd, c4, cfg)
        if res["status"] != "CLOSED":
            continue
        k = cd["strategy"] if cd["score"] >= cfg["min_score"] else "REJEITADOS"
        p = cd["plan"]
        ref = p["entry_zone"][1]
        out.append((k, {"asset": asset, "t": res["entry_t"], "r": res["r"],
                        "geo": {"stop": p["stop"] / ref - 1,
                                "tp": [x / ref - 1 for x in p["tp"]],
                                "partials": list(p["partials"]),
                                "breakeven": True}}))
    return out


# ---------- Oversold Bounce (as quatro saidas do papel) ----------

def bounce_trades(asset, c4, above, cfg, t0):
    out, busy = [], {}
    for i in range(PB.HIGH_BARS + 30, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if t_sig < t0 or not _known(t_sig, above):
            continue
        sig = PB.signal(c4[max(0, i - 299):i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]                       # abertura seguinte
        a4 = a1 = None
        try:
            a4 = B._tf(c4[max(0, i + 1 - B.WINDOW):i + 1])
            d1 = [x for x in B.daily(c4[:i + 1]) if x["t"] + DAY <= t_sig]
            a1 = B._tf(d1[-B.WINDOW:])
            if not (a4.get("ok") and a1.get("ok")):
                a4 = a1 = None
        except Exception:
            a4 = a1 = None
        for g, p in PB.plans(sig, px, a4, a1, cfg).items():
            if busy.get(g, 0) > i:                # uma de cada vez por moeda
                continue
            pos = trade.open_position(p, px, c4[i + 1]["t"], PB.FEE_PCT,
                                      PB.SLIP_PCT, breakeven=p["breakeven"])
            k = i + 1
            while not pos["closed"] and k < len(c4):
                x = c4[k]
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= PB.GEOS[g]["hold"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                    trade._finish(pos, "TIME", x["t"] + H4)
                k += 1
            if not pos["closed"]:
                continue
            busy[g] = k
            out.append(("BOUNCE_" + g, {"asset": asset, "t": pos["opened_at"],
                                        "r": pos["r"], "hold": PB.GEOS[g]["hold"],
                                        "geo": {"stop": p["stop"] / px - 1,
                                                "tp": [x / px - 1 for x in p["tp"]],
                                                "partials": list(p["partials"]),
                                                "breakeven": p["breakeven"]}}))
    return out


# ---------- tendencia diaria (grandes moedas) ----------

def trend_trades(asset, c4, above, cfg, t0):
    if asset not in PT.MAJORS21:
        return []
    d = B.daily(c4)
    fee, out, pos = cfg["fee_pct"] / 100, [], None
    for k in range(201, len(d)):
        day = d[k]
        if pos:
            if day["l"] <= pos["stop"]:
                ex = min(day["o"], pos["stop"]) * (1 - PT.SLIP)
            elif d[k - 1]["c"] < min(x["l"] for x in d[k - 1 - PT.M:k - 1]):
                ex = day["o"] * (1 - PT.SLIP)
            else:
                continue
            ru = pos["entry"] - pos["stop"] + fee * (pos["entry"] + pos["stop"])
            out.append(("TREND_DAILY", {"asset": asset, "t": pos["t"],
                                        "r": (ex - pos["entry"] - fee * (ex + pos["entry"])) / ru,
                                        "geo": None}))
            pos = None
            continue
        prev = d[k - 1]                            # dia fechado, decide hoje
        if day["t"] < t0 or not above.get(prev["t"] // DAY):
            continue
        sma = sum(x["c"] for x in d[k - 200:k]) / 200
        if prev["c"] > max(x["h"] for x in d[k - 1 - PT.N:k - 1]) and prev["c"] > sma:
            atr = PT._atr(d[:k])
            e = day["o"] * (1 + PT.SLIP)
            if atr > 0:
                pos = {"entry": e, "stop": e - PT.K_ATR * atr, "t": day["t"]}
    return out


# ---------- juntar tudo ----------

def judge(trs, bars, rng):
    """Resumo de um lutador com o teste contra o acaso."""
    rs = [t["r"] for t in trs]
    lists = []
    for t in trs:
        if t.get("geo"):
            lists.append(arena.control_rs(bars[t["asset"]], t["t"], t["geo"],
                                          "LONG", rng, reps=REPS))
    has_ctrl = bool(lists) and sum(1 for c in lists if c) >= max(1, len(rs) // 2)
    med, p95 = arena._dist(lists, rng) if has_ctrl else (None, None)
    mean = sum(rs) / len(rs)
    return {"n": len(rs), "wins": sum(1 for x in rs if x > 0),
            "avg_r": round(mean, 3), "total_r": round(sum(rs), 2),
            "ultimas": [round(x, 2) for x in rs[-10:]],
            "acaso_mediana": None if med is None else round(med, 3),
            "acaso_p95": None if p95 is None else round(p95, 3),
            "veredicto": arena.verdict(len(rs), mean, med, p95, has_ctrl)}


def run(bars, cfg, now, days=DAYS, seed=7):
    t0 = now - days * DAY
    btc = bars.get("BTC")
    reg, above = B.regimes(btc), btc_above(btc)
    groups = {k: [] for k in LIVE + ("REJEITADOS", "BOUNCE_G0", "BOUNCE_V1",
                                     "BOUNCE_V2", "BOUNCE_V3", "TREND_DAILY")}
    for a, c4 in sorted(bars.items()):
        try:
            for k, t in live_trades(a, c4, reg, above, cfg, t0):
                groups.setdefault(k, []).append(t)
            for k, t in bounce_trades(a, c4, above, cfg, t0):
                groups[k].append(t)
            for k, t in trend_trades(a, c4, above, cfg, t0):
                groups[k].append(t)
        except Exception as e:                       # uma moeda nao para o ringue
            print(f"{a}: {type(e).__name__}: {e}", file=sys.stderr)
    rng = random.Random(seed)
    out = {}
    for k, trs in groups.items():
        trs.sort(key=lambda t: t["t"])
        out[k] = judge(trs, bars, rng) if trs else {
            "n": 0, "wins": 0, "avg_r": None, "total_r": 0, "ultimas": [],
            "acaso_mediana": None, "acaso_p95": None, "veredicto": "A COMPETIR"}
    return {"atualizado": int(now), "janela_dias": days,
            "desde": int(t0), "moedas": len(bars), "lutadores": out}


def main(dest, days=DAYS):
    from engine import venue
    now = int(time.time())
    cfg = config.load()
    bars, falhas = {}, []
    listed = sorted(set(venue.fetch("USDC")) | {"BTC"})
    for base in listed:
        try:
            c = fetch(base, now)
        except Exception as e:
            falhas.append(f"{base}: {str(e)[:50]}")
            continue
        if len(c) >= NEED_BARS:
            bars[base] = c
        time.sleep(0.1)
    if "BTC" not in bars:
        raise SystemExit("sem velas do BTC: ringue nao corre")
    t = time.time()
    res = run(bars, cfg, now, days)
    res["segundos"] = round(time.time() - t)
    res["falhas"] = falhas[:20]
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "forma.json"), "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res["lutadores"].items():
        print(f"{k:16s} n={v['n']:4d} R={v['avg_r']} acaso={v['acaso_mediana']}"
              f"/{v['acaso_p95']} -> {v['veredicto']}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else DAYS)
