"""Market Scanner - Fase 1.

Passo barato: todos os pares (1 pedido por fonte) -> filtro de liquidez.
Passo profundo: so os N mais liquidos -> velas 1D/4H + validacao.
Nesta fase NAO ha sinais: so universo, liquidez e qualidade dos dados.
"""
import math
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from . import (analysis, config, derivatives, events as calendar, ledger,
               liquidity, paper_trend, regime, review,
               signals,
               sources, validate, venue, volume)

MIN_VOLUME_USD = 5_000_000
MAX_SPREAD_BPS = 20
DEEP_N = 40
TIMEFRAMES = ["1d", "4h"]

STABLE_OR_PEGGED = {
    "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDD", "USDP", "BUSD",
    "USD1", "USDS", "RLUSD", "EUR", "EURI", "EURC", "AEUR", "GBP", "BRL",
    "TRY", "WBTC", "WETH", "STETH", "WBETH", "BETH", "PAXG", "XAUT", "XUSD",
    "USDR", "USTC", "BFUSD", "USDQ", "USD0", "SUSDE", "USDTB", "MNT_USD"}
LEVERAGED = re.compile(r"(\d+[LS]|UP|DOWN|BULL|BEAR)$")
# Acoes tokenizadas vistas sem par noutra exchange (as restantes sao
# detetadas automaticamente em tokenized_stocks()).
STOCK_TOKENS = {"NVDAB", "SPCXB", "GOOGLB", "TSLAB", "AVGOB", "SNXXB",
                "KORUB", "SKHYB", "AAPLB", "AMZNB", "METAB", "MSFTB", "COINB",
                "HOODB", "PLTRB", "AMDB", "QQQB", "SPYB"}


def tokenized_stocks(data):
    """Acoes tokenizadas: Binance usa sufixo B (MSTRB), OKX prefixo X
    (XMSTR). Se os dois existem com o mesmo preco, e a mesma acao."""
    out = set(STOCK_TOKENS)
    bn, ok = data.get("binance", {}), data.get("okx", {})
    for b, t in bn.items():
        if len(b) > 2 and b.endswith("B"):
            o = ok.get("X" + b[:-1])
            if o and t["last"] and o["last"] and \
                    abs(t["last"] / o["last"] - 1) < 0.02:
                out.update((b, "X" + b[:-1]))
    return out


def liquidity_score(vol, spread_bps, n_sources):
    v = max(0.0, min(1.0, (math.log10(max(vol, 1)) - 6) / 3))    # $1M -> $1B
    s = max(0.0, min(1.0, 1 - (spread_bps - 2) / 28))            # 2 -> 30 bps
    return round(60 * v + 25 * s + 5 * min(n_sources, 3))


def collect_tickers():
    status, data = {}, {}
    for src in sources.ALL:
        try:
            data[src.name] = src.tickers()
            status[src.name] = {"ok": True, "pairs": len(data[src.name])}
        except sources.SourceError as e:
            status[src.name] = {"ok": False, "error": str(e)[:200]}
    return status, data


def build_universe(data):
    bases = set().union(*[set(d) for d in data.values()]) if data else set()
    uni, stocks = [], tokenized_stocks(data)
    for b in bases:
        if b in STABLE_OR_PEGGED or LEVERAGED.search(b) or b in stocks:
            continue
        per = {s: d[b] for s, d in data.items() if b in d}
        ok = {s: t for s, t in per.items()
              if t["last"] and t["bid"] and t["ask"] and t["ask"] >= t["bid"] > 0
              and t["vol_quote"] is not None}
        if not ok:
            continue
        vol = sum(t["vol_quote"] for t in ok.values())
        spread = min((t["ask"] - t["bid"]) / ((t["ask"] + t["bid"]) / 2) * 1e4
                     for t in ok.values())
        prices = {s: t["last"] for s, t in ok.items()}
        div, div_status = validate.price_divergence(prices)
        chgs = [t["chg_pct"] for t in ok.values() if t["chg_pct"] is not None]
        px = statistics.median(prices.values())
        if abs(px - 1) < 0.004 and chgs and max(abs(x) for x in chgs) < 0.3:
            continue                      # indexado ao dolar: nao e negociavel
        reasons = []
        if vol < MIN_VOLUME_USD:
            reasons.append("volume baixo")
        if spread > MAX_SPREAD_BPS:
            reasons.append("spread excessivo")
        if div_status == validate.INVALID:
            reasons.append("divergencia entre fontes")
        uni.append({
            "asset": b, "price": statistics.median(prices.values()),
            "chg_24h": round(statistics.median(chgs), 2) if chgs else None,
            "volume_24h": round(vol), "spread_bps": round(spread, 2),
            "sources": sorted(ok), "divergence_pct":
                None if div is None else round(div, 3),
            "liquidity_score": liquidity_score(vol, spread, len(ok)),
            "eligible": not reasons, "excluded_for": reasons})
    uni.sort(key=lambda r: -r["volume_24h"])
    return uni


def deep_check(row, src_order, now):
    """Velas + validacao para um ativo. Usa a 1a fonte que responder."""
    out = {"timeframes": {}, "flags": []}
    clean = {}
    for tf in TIMEFRAMES:
        rep, used = None, None
        for i, src in enumerate(src_order):
            if src.name not in row["sources"]:
                continue
            try:
                raw = src.candles(row["asset"], tf)
            except sources.SourceError as e:
                rep = {"status": "DATA SOURCE ERROR", "issues": [str(e)[:120]],
                       "n": 0}
                continue
            cs, rep = validate.validate_candles(
                raw, sources.TF_SECONDS[tf], now, validate.MIN_HISTORY[tf])
            used = src.name
            if rep["status"] != validate.INVALID:
                clean[tf] = cs
            if i > 0 and "DATA SOURCE FALLBACK" not in out["flags"]:
                out["flags"].append("DATA SOURCE FALLBACK")
            break
        rep = rep or {"status": "DATA SOURCE ERROR", "issues": ["sem fonte"],
                      "n": 0}
        rep["source"] = used
        out["timeframes"][tf] = rep
    sts = [r["status"] for r in out["timeframes"].values()]
    if any(s in (validate.INVALID, "DATA SOURCE ERROR") for s in sts):
        out["data_status"] = validate.INVALID
    elif any(s == validate.DEGRADED for s in sts) or row["divergence_pct"] and \
            row["divergence_pct"] > 0.5:
        out["data_status"] = validate.DEGRADED
    else:
        out["data_status"] = validate.VALID
    n_issues = sum(len(r["issues"]) for r in out["timeframes"].values())
    out["data_quality"] = (0 if out["data_status"] == validate.INVALID
                           else max(50, 100 - 10 * n_issues
                                    - (0 if len(row["sources"]) > 1 else 10)))
    # Sem dados validos nao ha analise (hierarquia: 1. dados validos?)
    out["_c4"] = clean.get("4h")
    out["_c1"] = clean.get("1d")
    usable = (out["data_status"] != validate.INVALID
              and len(clean) == len(TIMEFRAMES))
    out["analysis"] = analysis.multi(clean) if usable else None
    if usable:
        for tf in TIMEFRAMES:
            a = out["analysis"][tf]
            if a["ok"]:
                a["volume"] = volume.analyse(clean[tf])
                a["liquidity"] = liquidity.analyse(clean[tf])
    # Livro de ordens: so para medir slippage real de uma ordem pequena.
    out["book"] = None
    for src in src_order:
        if src.name in row["sources"] and hasattr(src, "book"):
            try:
                m = liquidity.book_metrics(*src.book(row["asset"]))
                out["book"] = dict(m, source=src.name) if m else None
            except (sources.SourceError, KeyError, IndexError, ValueError):
                continue
            break
    return out


def add_derivatives(rows, now):
    """Derivados para os ativos analisados. Devolve o estado da fonte."""
    try:
        snap = derivatives.market_snapshot()
    except (sources.SourceError, KeyError, TypeError) as e:
        for r in rows:
            r["derivatives"] = None
        return {"ok": False, "error": str(e)[:200]}
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda r: derivatives.analyse(
            r["asset"], r["price"], snap, now), rows))
    for r, d in zip(rows, res):
        r["derivatives"] = d
    return {"ok": True, "with_perp": sum(d is not None for d in res),
            "incomplete": sum(bool(d and d["missing"]) for d in res)}


def run(now=None, state=None, cfg=None):
    """Devolve (resultado, estado, eventos de auditoria)."""
    now = int(now or time.time())
    state = state if state is not None else {}
    cfg = cfg or config.load()
    status, data = collect_tickers()
    live = [s for s in sources.ALL if status[s.name]["ok"]]
    result = {"generated_at": now, "phase": 4, "sources": status,
              "config": cfg,
              "thresholds": {"min_volume_usd": MIN_VOLUME_USD,
                             "max_spread_bps": MAX_SPREAD_BPS,
                             "deep_n": DEEP_N},
              "signals_note": "Estrategias NAO validadas por backtest. "
                              "O score não é uma probabilidade."}
    if not live:
        result.update(status_global="DATA SOURCE ERROR", universe=[])
        return result, state, []
    try:
        ven = venue.fetch(cfg["quote"])
        result["venue_source"] = {"ok": True, "pairs": len(ven)}
    except (sources.SourceError, KeyError, TypeError) as e:
        ven = None
        result["venue_source"] = {"ok": False, "error": str(e)[:200]}

    uni = build_universe(data)
    for r in uni:
        v = ven.get(r["asset"]) if ven else None
        r["on_venue"] = v is not None
        r["venue"] = v
        if ven is not None and v is None and r["eligible"]:
            r["eligible"] = False
            r["excluded_for"].append("não listado na Bybit UE")
    eligible = [r for r in uni if r["eligible"]][:DEEP_N]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for row, deep in zip(eligible, ex.map(
                lambda r: deep_check(r, live, now), eligible)):
            row.update(deep)
    analysed = [r for r in eligible if r.get("analysis")]
    result["derivatives_source"] = add_derivatives(analysed, now)

    # Regimes: o do BTC e contexto para todos; mudancas reduzem confianca.
    prev = state.get("regimes", {})
    regs, changed = {}, {}
    for r in analysed:
        reg = regime.classify(r["analysis"]["1d"])["regime"]
        old = prev.get(r["asset"], {})
        since = old.get("since", now) if old.get("regime") == reg else now
        regs[r["asset"]] = {"regime": reg, "since": since,
                            "previous": old.get("regime")
                            if old.get("regime") != reg else old.get("previous")}
        changed[r["asset"]] = bool(old) and now - since < 86400
    state["regimes"] = regs
    btc_reg = regs.get("BTC", {}).get("regime")
    result["market_regime"] = {"btc": btc_reg}

    daily = {r["asset"]: r.pop("_c1", None) for r in eligible}
    result["market_filter"], events = paper_trend.market_filter(
        daily.get("BTC"), state, now)
    market_ok = bool(result["market_filter"]
                     and result["market_filter"]["btc_above_sma200"])
    ev_block = calendar.block(now)
    block = (f"{ev_block['name']} dentro da janela de risco"
             if ev_block else None)
    disabled, ev = review.update(state, now)
    events += ev
    result.update(next_event=calendar.next_event(now), event_block=block,
                  calendar_stale=calendar.stale(now),
                  disabled_strategies=disabled)
    for r in eligible:
        c4 = r.pop("_c4", None)
        if ven is None:
            r["decision"] = {"decision": "NO TRADE", "validated": False,
                             "reason": "DATA SOURCE ERROR: lista da Bybit UE "
                                       "indisponível", "checks": []}
        else:
            r["decision"] = signals.decide(r, c4, cfg, ven.get(r["asset"]),
                                           btc_reg, changed.get(r["asset"], False),
                                           market_ok, block, set(disabled))
    events += signals.update_state(state, eligible, cfg, now, daily)
    result["halt"] = state.get("halt")
    result["paper_trend"], ev = paper_trend.update(
        state, eligible, daily, cfg, now, market_ok,
        state.get("halt") or block
        or ("desligada" if "TREND_DAILY" in disabled else None))
    events += ev
    led = ledger.apply(state, events)
    result["journal"] = ledger.view(led)
    result["active_signals"] = [s for s in state["signals"].values()
                                if s["status"] in ("ACTIVE", "TRIGGERED")]
    result["track_record"] = state.get("track", {})
    result["closed_signals"] = sorted(
        (s for s in state["signals"].values()
         if s["status"] in ("EXPIRED", "INVALIDATED", "CLOSED")),
        key=lambda s: -s["closed_at"])[:15]
    ok_all = len(live) == len(sources.ALL) and ven is not None
    dec = [r["decision"]["decision"] for r in eligible]
    result.update(
        status_global="OK" if ok_all else "DEGRADED",
        counts={"pairs_seen": len(uni),
                "eligible": sum(r["eligible"] for r in uni),
                "deep_checked": len(eligible),
                "data_valid": sum(r.get("data_status") == validate.VALID
                                  for r in eligible),
                "data_invalid": sum(r.get("data_status") == validate.INVALID
                                    for r in eligible),
                "long": sum(r["decision"]["decision"] == "LONG"
                            and r["decision"].get("mode") == "REAL"
                            for r in eligible),
                "paper": sum(r["decision"]["decision"] == "LONG"
                             and r["decision"].get("mode") == "PAPER"
                             for r in eligible),
                "watchlist": dec.count("WATCHLIST"),
                "no_trade": dec.count("NO TRADE")},
        universe=eligible)
    return result, state, events
