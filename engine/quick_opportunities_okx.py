"""Quick Opportunities exclusively on OKX USD_UM X-Perps.

Read-only market discovery and Telegram research alerts. This module never
imports an executor, reads private account state, changes leverage, or submits
orders. Public X-Perp availability does not prove that the user's account has
USDC settlement enabled; execution must retain the separate fail-closed guard.
"""
from concurrent.futures import ThreadPoolExecutor

from . import quick_opportunities as engine
from . import quick_opportunities_derivatives as derivatives
from . import quick_opportunities_telegram as telegram
from .sources import _get, SourceError

OKX = "https://www.okx.com"
BAR_MS = 30 * 60 * 1000
CANDLE_COUNT = 100
DEFAULT_MAX_ASSETS = 60
DEFAULT_WORKERS = 6


def select_liquid_xperps(instruments, tickers, limit=DEFAULT_MAX_ASSETS):
    """Join live linear USD_UM X-Perps to OKX FUTURES tickers and rank by quote volume."""
    by_id = {}
    for item in tickers or []:
        inst_id = str(item.get("instId") or "")
        try:
            volume = float(item.get("volCcy24h") or item.get("vol24h") or 0)
        except (TypeError, ValueError):
            volume = 0.0
        if inst_id and volume > 0:
            by_id[inst_id] = volume

    selected = []
    for base, info in (instruments or {}).items():
        inst_id = str(info.get("inst_id") or "")
        family = str(info.get("inst_family") or "")
        if (not inst_id or "_UM_XPERP-" not in inst_id
                or not family.endswith("_UM")
                or info.get("contract_type") != "linear"):
            continue
        volume = by_id.get(inst_id)
        if volume is None:
            continue
        selected.append((volume, base, info))
    selected.sort(key=lambda row: (-row[0], row[1]))
    return [
        {**info, "base": base, "volume_24h_contract_quote": volume}
        for volume, base, info in selected[:max(1, int(limit))]
    ]


def _public_universe(request=_get, limit=DEFAULT_MAX_ASSETS):
    instruments = derivatives.okx_usdc_xperps(request=request)
    response = request(OKX + "/api/v5/market/tickers", {"instType": "FUTURES"})
    if not isinstance(response, dict) or response.get("code") != "0":
        raise SourceError("OKX FUTURES tickers: resposta inválida")
    selected = select_liquid_xperps(
        instruments, response.get("data") or [], limit=limit)
    return selected, len(instruments)


def _fetch_one(info, start_ms, end_ms, now, request):
    candles = derivatives.fetch_okx_xperp_candles(
        info["inst_id"], start_ms, end_ms, request=request, pause_seconds=0)
    clean, report = engine.prepare_30m_candles(candles, now)
    if report.get("status") != "VALID" or len(clean) < engine.MIN_BARS:
        return info, [], report
    candidates = engine.detect_opportunities(clean, info["base"])
    for candidate in candidates:
        candidate.update({
            "venue": "OKX",
            "market_type": "USD_UM_XPERP",
            "instrument_id": info["inst_id"],
            "settlement_currency_required": "USDC",
            "source_timeframe": "30m",
        })
    return info, candidates, report


def scan_okx_xperps(now, seen_ids=None, sender=None,
                    max_assets=DEFAULT_MAX_ASSETS,
                    max_workers=DEFAULT_WORKERS, request=_get):
    """Scan the most liquid live OKX X-Perps on confirmed 30m candles.

    seen_ids is a persistent dict in scanner state: event IDs are marked only
    after Telegram accepts the message, preventing repeat alerts across runs.
    """
    now = int(now)
    end_ms = (now * 1000 // BAR_MS) * BAR_MS
    start_ms = end_ms - CANDLE_COUNT * BAR_MS
    if end_ms <= start_ms:
        return {"status": "ERROR", "error": "intervalo de velas inválido"}

    selected, instruments_seen = _public_universe(request=request, limit=max_assets)
    if not selected:
        return {
            "status": "NO_MARKETS", "venue": "OKX",
            "market_type": "USD_UM_XPERP", "instruments_seen": instruments_seen,
            "assets_requested": 0, "assets_with_valid_data": 0,
            "candidates": [], "telegram_sent": [],
        }

    fetcher = lambda info: _fetch_one(info, start_ms, end_ms, now, request)
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        fetched = list(pool.map(fetcher, selected))

    candidates = [candidate for _, found, _ in fetched for candidate in found]
    errors = {
        info["base"]: report
        for info, found, report in fetched
        if not found and report.get("status") != "VALID"
    }

    seen = seen_ids if isinstance(seen_ids, dict) else {}
    # Bound persistent state and retain enough history to deduplicate retries.
    for event_id, timestamp in list(seen.items()):
        try:
            if now - int(timestamp) > 7 * 86400:
                del seen[event_id]
        except (TypeError, ValueError):
            del seen[event_id]

    fresh = []
    for candidate in candidates:
        event_id = telegram._signal_id(candidate)
        if event_id not in seen:
            fresh.append(candidate)

    sent = telegram.notify_candidates(fresh, sender=sender)
    for item in sent:
        seen[item["id"]] = now

    return {
        "status": "OK",
        "venue": "OKX",
        "market_type": "USD_UM_XPERP",
        "settlement_currency_required": "USDC",
        "account_settlement_confirmed": False,
        "instruments_seen": instruments_seen,
        "assets_requested": len(selected),
        "assets_with_valid_data": sum(
            1 for _, _, report in fetched if report.get("status") == "VALID"),
        "source_timeframe": "30m",
        "candle_count_requested": CANDLE_COUNT,
        "candidates": candidates,
        "telegram_sent": sent,
        "data_errors": errors,
    }
