"""Backtesting Engine.

Reproduz o mercado vela a vela de 4H. Em cada vela fechada o motor ve
apenas o passado e decide com as MESMAS funcoes do sistema ao vivo
(analysis, regime, strategies, risk, confluence, signals.decide,
trade.step). Custos: comissao por lado, slippage na entrada e no stop.

Limitacoes assumidas e declaradas nos resultados:
- universo = ativos hoje listados na Bybit UE (vies de sobrevivencia)
- sem dados historicos de derivados: essa familia fica neutra (0.5)
- precos da Binance em USDT, nao da Bybit UE em USDC
"""
import csv
import gzip
import os

from . import analysis, liquidity, regime, signals, trade, validate, volume

H4, DAY = 14400, 86400
WINDOW = 499                       # igual ao que o sistema ao vivo recebe
EXPIRY_BARS = 3
SLIP_PCT = 0.05
VENUE_OK = {"pair": "BT/USDC", "volume_usd": 1e9, "spread_pct": 0.02,
            "stale": False, "url": None}


def load(path):
    out = []
    with gzip.open(path, "rt") as f:
        for r in csv.reader(f):
            out.append({"t": int(r[0]), "o": float(r[1]), "h": float(r[2]),
                        "l": float(r[3]), "c": float(r[4]), "v": float(r[5]),
                        "tb": float(r[6])})
    return out


def clean(c):
    """Aplica o validador; se o historico for invalido devolve None."""
    cs, rep = validate.validate_candles(c, H4, c[-1]["t"] + 2 * H4, 0)
    return cs, rep


def daily(c4):
    """Velas diarias (UTC) so de dias completos: 6 velas de 4H."""
    out, cur = [], []
    for x in c4:
        if cur and x["t"] // DAY != cur[0]["t"] // DAY:
            if len(cur) == 6:
                out.append(_agg(cur))
            cur = []
        cur.append(x)
    if len(cur) == 6:
        out.append(_agg(cur))
    return out


def _agg(b):
    return {"t": b[0]["t"], "o": b[0]["o"], "h": max(x["h"] for x in b),
            "l": min(x["l"] for x in b), "c": b[-1]["c"],
            "v": sum(x["v"] for x in b), "tb": sum(x["tb"] for x in b)}


def _tf(c):
    a = analysis.timeframe(c)
    if a["ok"]:
        a["volume"] = volume.analyse(c)
        a["liquidity"] = liquidity.analyse(c)
    return a


def regimes(c4):
    """{dia: regime} conhecido no fecho desse dia (para o contexto BTC)."""
    d1 = daily(c4)
    out = {}
    for k in range(analysis.MIN_BARS, len(d1) + 1):
        a = analysis.timeframe(d1[max(0, k - WINDOW):k])
        out[d1[k - 1]["t"] // DAY] = regime.classify(a)["regime"]
    return out


def candidates(asset, c4, btc_regimes, cfg, start_t=0, end_t=None):
    """Todos os setups READY com plano valido. Sem filtro de score."""
    cfg0 = dict(cfg, min_score=0, swing_leverage=1.0, capital_usdc=None)
    d1 = daily(c4)
    d_idx, a1, out = 0, None, []
    first = max(analysis.MIN_BARS, 1)
    for i in range(first, len(c4)):
        t_close = c4[i]["t"] + H4
        if end_t and t_close > end_t:
            break
        # dias completamente fechados ate ao fecho desta vela
        moved = False
        while d_idx < len(d1) and d1[d_idx]["t"] + DAY <= t_close:
            d_idx += 1
            moved = True
        if d_idx < analysis.MIN_BARS or t_close < start_t:
            if moved:
                a1 = None
            continue
        if moved or a1 is None:
            a1 = _tf(d1[max(0, d_idx - WINDOW):d_idx])
        w4 = c4[max(0, i + 1 - WINDOW):i + 1]
        a4 = _tf(w4)
        if not (a1["ok"] and a4["ok"]):
            continue
        row = {"asset": asset, "price": c4[i]["c"], "data_status": "VALID",
               "data_quality": 100, "liquidity_score": 80, "derivatives": None,
               "analysis": {"1d": a1, "4h": a4,
                            "mtf_conflict": analysis.mtf_conflict(a1, a4)}}
        btc = btc_regimes.get((t_close - DAY) // DAY)
        d = signals.decide(row, w4, cfg0, dict(VENUE_OK, last=c4[i]["c"]),
                           btc, False)
        if d.get("state") == "READY" and d.get("plan"):
            out.append({"asset": asset, "i": i, "t": t_close,
                        "strategy": d["strategy"], "score": d["score"],
                        "regime": d["regime"], "btc_regime": btc,
                        "n_conflicts": len(d["conflicts"]), "plan": d["plan"],
                        "families": d["families"]})
    return out


def simulate(cand, c4, cfg, slip_pct=SLIP_PCT, breakeven=True,
             expiry=EXPIRY_BARS):
    """Executa um candidato. Devolve dict com resultado ou status."""
    p, i = cand["plan"], cand["i"]
    top = p["entry_zone"][1]
    pos = None
    for j in range(i + 1, min(i + 1 + expiry, len(c4))):
        b = c4[j]
        if b["o"] <= p["stop"]:
            return {"status": "INVALIDATED"}
        if b["l"] <= top:
            at_open = b["o"] <= top
            fill = b["o"] if at_open else top
            pos = trade.open_position(p, fill, b["t"], cfg["fee_pct"], slip_pct,
                                      breakeven)
            h = b["h"] if at_open else fill      # sem credito de TP a meio da vela
            ev = trade.step(pos, fill, max(h, fill), b["l"], b["c"], b["t"] + H4)
            k = j
            break
        if b["h"] > p["tp"][0]:
            return {"status": "INVALIDATED"}
    if pos is None:
        return {"status": "EXPIRED"}
    while not pos["closed"]:
        k += 1
        if k >= len(c4):
            return {"status": "OPEN_AT_END"}
        b = c4[k]
        trade.step(pos, b["o"], b["h"], b["l"], b["c"], b["t"] + H4)
    return {"status": "CLOSED", "r": pos["r"], "exit": pos["exit_reason"],
            "entry_t": pos["opened_at"], "exit_t": pos["closed_at"],
            "tp_hit": pos["tp_hit"], "risk_pct": p["risk_pct"],
            "bars": k - j + 1}


def load_all(folder, min_bars=2500):
    data, skipped = {}, {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".csv.gz"):
            continue
        a = fn[:-7]
        cs, rep = clean(load(os.path.join(folder, fn)))
        if rep["status"] == validate.INVALID:
            skipped[a] = "; ".join(rep["issues"])
        elif len(cs) < min_bars:
            skipped[a] = f"historico curto ({len(cs)} velas)"
        else:
            data[a] = cs
    return data, skipped
