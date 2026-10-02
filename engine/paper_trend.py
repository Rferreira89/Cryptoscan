"""Paper trading (Fase 6) da hipotese TENDENCIA diaria + filtro de mercado.

ATENCAO: esta estrategia NAO passou a validacao (falhou a reserva e nao
bateu a referencia). Corre apenas em papel, para acumular evidencia real
fora da amostra. Nenhuma operacao daqui deve ser feita com dinheiro.

Regras (iguais as testadas em tools/research.py, configuracao escolhida
pelo walk-forward): compra quando o fecho diario supera o maximo dos 20
dias anteriores com o preco acima da media de 200 dias; stop inicial a
2 ATR(20); sai quando o fecho diario fica abaixo do minimo dos 20 dias
anteriores. Risco de 1% por operacao, maximo de 4 posicoes, so grandes
moedas de 2021 listadas na Bybit UE.
"""
from . import risk

MAJORS21 = ["BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "DOT", "LTC",
            "LINK", "BCH", "XLM", "UNI", "AVAX", "TRX", "ATOM", "FIL", "ALGO",
            "AAVE", "NEAR", "ICP", "HBAR", "CRV", "INJ"]
N, M, K_ATR = 20, 20, 2.0
MAX_POS, CAP, SLIP = 4, 0.25, 0.001


def _atr(c, n=20):
    tr = [max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - c[i - 1]["c"]),
              abs(c[i]["l"] - c[i - 1]["c"])) for i in range(len(c) - n, len(c))]
    return sum(tr) / n


def market_filter(c1_btc, state, now):
    """BTC acima/abaixo da media de 200 dias. Devolve (info, eventos)."""
    if not c1_btc or len(c1_btc) < 200:
        return None, []
    close = c1_btc[-1]["c"]
    sma = sum(x["c"] for x in c1_btc[-200:]) / 200
    above = close > sma
    prev = state.get("market_filter")
    ev = []
    if prev is None or prev["above"] != above:
        if prev is not None:
            ev.append({"t": now, "event": "MARKET_FILTER", "id": "market",
                       "above": above, "close": close, "sma200": sma})
        state["market_filter"] = prev = {"above": above, "since": now}
    return {"btc_above_sma200": above, "close": close, "sma200": round(sma, 2),
            "distance_pct": round((close / sma - 1) * 100, 1),
            "since": prev["since"]}, ev


RECORD = "⚠️ Não validada (desde ago. 2025: -1% nas grandes moedas)."


def check_stops(state, prices, cfg, now):
    """So stops, com os precos dados (passagens de 5 minutos)."""
    st = state.get("paper_trend")
    if not st:
        return []
    ev, fee = [], cfg["fee_pct"] / 100
    for a in list(st["positions"]):
        px = prices.get(a)
        if px is not None and px <= st["positions"][a]["stop0"]:
            _close(st, ev, a, min(px, st["positions"][a]["stop0"]), "STOP",
                   fee, now, cfg)
    return ev


def _close(st, ev, a, px, reason, fee, now, cfg):
    p = st["positions"].pop(a)
    exit_px = px * (1 - SLIP)
    risk_unit = p["entry"] - p["stop0"] + fee * (p["entry"] + p["stop0"])
    r = (exit_px - p["entry"] - fee * (exit_px + p["entry"])) / risk_unit
    st["equity"] *= 1 + r * p["risk_frac"]
    rec = dict(p, asset=a, exit=exit_px, exit_t=now, r=round(r, 2),
               reason=reason)
    st["closed"] = (st["closed"] + [rec])[-200:]
    ev.append({"t": now, "event": "PAPER_SELL", "id": f"paper-{a}",
               "asset": a, "price": exit_px, "r": rec["r"],
               "reason": reason, "pair": p["pair"],
               "real": bool(cfg.get("real_money_unvalidated"))})


def update(state, rows, daily, cfg, now, market_ok=True, halted=None):
    """rows: ativos analisados; daily: {ativo: velas diarias fechadas}."""
    st = state.setdefault("paper_trend", {"equity": 1.0, "positions": {},
                                          "closed": [], "last_day": {}})
    fee = cfg["fee_pct"] / 100
    ev = []
    # limite de operacoes partilhado com os sinais de 4H
    live = [s for s in state.get("signals", {}).values()
            if s["status"] in ("ACTIVE", "TRIGGERED")
            and s.get("mode", "REAL") == "REAL"]
    live_4h, live_assets = len(live), {s["asset"] for s in live}
    max_pos = min(MAX_POS, cfg.get("max_open_positions", MAX_POS))

    def close(a, px, reason):
        _close(st, ev, a, px, reason, fee, now, cfg)

    for r in rows:
        a, c = r["asset"], daily.get(r["asset"])
        if a not in MAJORS21 or not c or len(c) < 201 or not r.get("venue"):
            continue
        px, last = r["price"], c[-1]
        new_day = last["t"] > st["last_day"].get(a, 0)
        if a in st["positions"]:
            p = st["positions"][a]
            if px <= p["stop0"]:
                close(a, min(px, p["stop0"]), "STOP")
            elif new_day and last["c"] < min(x["l"] for x in c[-1 - M:-1]):
                close(a, px, "TRAIL")
        elif new_day and len(st["positions"]) + live_4h < max_pos \
                and a not in live_assets and not halted and \
                (market_ok or not cfg.get("require_btc_above_sma200")):
            sma = sum(x["c"] for x in c[-200:]) / 200
            atr = _atr(c)
            brk = last["c"] > max(x["h"] for x in c[-1 - N:-1])
            late = px > last["c"] + atr          # nao perseguir o preco
            if brk and last["c"] > sma and not late and atr > 0:
                entry = px * (1 + SLIP)
                stop = entry - K_ATR * atr
                risk_unit = entry - stop + fee * (entry + stop)
                rp = min(cfg["risk_pct"],
                         cfg.get("unvalidated_risk_pct", cfg["risk_pct"]))
                lev = risk.leverage_for((entry - stop) / entry, cfg)
                frac = min(rp * lev["use"] / 100 / (risk_unit / entry),
                           CAP * lev["use"])
                cap = cfg.get("capital_usdc")
                fixed = cfg.get("fixed_position_usdc")
                if cap and fixed:
                    frac = min(fixed, cap * lev["use"]) / cap
                    if cap * frac * risk_unit / entry > \
                            cfg.get("max_risk_usdc", float("inf")) + 1e-9:
                        st["last_day"][a] = last["t"]
                        continue             # stop demasiado largo
                pos_usdc = cap * frac if cap else None
                if cap and pos_usdc < cfg.get("min_order_usdc", 5.0):
                    st["last_day"][a] = last["t"]
                    continue                 # abaixo da ordem minima
                st["positions"][a] = {
                    "entry": entry, "stop0": stop, "entry_t": now,
                    "pair": r["venue"]["pair"], "position_pct": round(frac * 100, 1),
                    "risk_frac": frac * risk_unit / entry}
                ev.append({"t": now, "event": "PAPER_BUY", "id": f"paper-{a}",
                           "asset": a, "price": entry, "stop": stop,
                           "pair": r["venue"]["pair"],
                           "position_pct": round(frac * 100, 1),
                           "risk_pct": round(frac * risk_unit / entry * 100, 2),
                           "stop_pct": round(risk_unit / entry * 100, 2),
                           "position_usdc": round(pos_usdc, 2) if cap else None,
                           "leverage": lev["use"],
                           "leverage_reason": (
                               "reduzida pelo stop largo, para manter a "
                               "liquidação longe do stop"
                               if lev["use"] < cfg.get("swing_leverage", 1)
                               else "condições normais"),
                           "collateral_pct": round(frac * 100 / lev["use"], 1),
                           "liquidation_est": entry * (1 - 1 / lev["use"] + risk.MMR)
                           if lev["use"] > 1 else None,
                           "real": bool(cfg.get("real_money_unvalidated"))})
        if new_day:
            st["last_day"][a] = last["t"]
    rs = [x["r"] for x in st["closed"]]
    summary = {"equity_pct": round((st["equity"] - 1) * 100, 2),
               "positions": st["positions"], "closed": st["closed"][-15:],
               "n": len(rs),
               "win_rate": round(100 * sum(x > 0 for x in rs) / len(rs), 1)
               if rs else None,
               "total_r": round(sum(rs), 2)}
    return summary, ev
