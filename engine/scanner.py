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

from . import sources, validate

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
    uni = []
    for b in bases:
        if b in STABLE_OR_PEGGED or LEVERAGED.search(b):
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
            _, rep = validate.validate_candles(
                raw, sources.TF_SECONDS[tf], now, validate.MIN_HISTORY[tf]
                if src.name != "okx" else min(validate.MIN_HISTORY[tf], 200))
            used = src.name
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
    return out


def run(now=None):
    now = int(now or time.time())
    status, data = collect_tickers()
    live = [s for s in sources.ALL if status[s.name]["ok"]]
    result = {"generated_at": now, "phase": 1, "sources": status,
              "thresholds": {"min_volume_usd": MIN_VOLUME_USD,
                             "max_spread_bps": MAX_SPREAD_BPS,
                             "deep_n": DEEP_N},
              "signals": "Fase 1: sem sinais. So universo, liquidez e dados."}
    if not live:
        result.update(status_global="DATA SOURCE ERROR", universe=[])
        return result
    uni = build_universe(data)
    eligible = [r for r in uni if r["eligible"]][:DEEP_N]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for row, deep in zip(eligible, ex.map(
                lambda r: deep_check(r, live, now), eligible)):
            row.update(deep)
    result.update(
        status_global="OK" if len(live) == len(sources.ALL) else "DEGRADED",
        counts={"pairs_seen": len(uni),
                "eligible": sum(r["eligible"] for r in uni),
                "deep_checked": len(eligible),
                "data_valid": sum(r.get("data_status") == validate.VALID
                                  for r in eligible),
                "data_invalid": sum(r.get("data_status") == validate.INVALID
                                    for r in eligible)},
        universe=[r for r in uni if r["volume_24h"] >= 1_000_000][:150])
    return result
