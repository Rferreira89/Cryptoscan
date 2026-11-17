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
DEFAULT_MAX_ASSETS = 100
DEFAULT_WORKERS = 6


def select_liquid_xperps(instruments, tickers, limit=DEFAULT_MAX_ASSETS):
    """Join live linear USD_UM X-Perps to OKX FUTURES tickers and rank by quote volume."""
    ticker_by_id = {
        str(item.get("instId") or ""): item
        for item in (tickers or []) if item.get("instId")
    }

    selected = []
    for base, info in (instruments or {}).items():
        inst_id = str(info.get("inst_id") or "")
        family = str(info.get("inst_family") or "")
        if (not inst_id or not derivatives.is_um_xperp(inst_id)
                or not derivatives.is_um_family(family)
                or info.get("contract_type") != "linear"):
            continue
        ticker = ticker_by_id.get(inst_id)
        if not ticker:
            continue
        # Normaliza para notional USD: contratos * valor USD/contrato.
        # Se só existir volume em moeda-base, converte-o pelo último preço.
        try:
            last = float(ticker.get("last") or 0)
            contracts = float(ticker.get("vol24h") or 0)
            contract_value = float(info.get("contract_value") or 0)
            value_currency = str(info.get("contract_value_currency") or "").upper()
            multiplier = float(info.get("contract_multiplier") or 1)
            if contracts > 0 and contract_value > 0 and multiplier > 0:
                volume_usd = contracts * contract_value * multiplier
                if value_currency != "USD":
                    volume_usd *= last
            else:
                base_volume = float(ticker.get("volCcy24h") or 0)
                volume_usd = base_volume * last
        except (TypeError, ValueError):
            volume_usd = 0.0
        if volume_usd > 0:
            selected.append((volume_usd, base, info))
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
    try:
        candles = derivatives.fetch_okx_xperp_candles(
            info["inst_id"], start_ms, end_ms, request=request, pause_seconds=0)
        clean, report = engine.prepare_30m_candles(candles, now)
    except Exception as exc:
        return info, [], {
            "status": "DATA SOURCE ERROR",
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
        }
    if report.get("status") != "VALID" or len(clean) < engine.MIN_BARS:
        return info, [], report
    candidates = engine.detect_opportunities(clean, info["base"])
    for candidate in candidates:
        candidate.update({
            "venue": "OKX",
            "market_type": "USD_UM_XPERP",
            "instrument_id": info["inst_id"],
            "settlement_currency_target": "USDC",
            "settlement_currency_options": ["USD", "USDC", "USDG"],
            "asset_class": info.get("asset_class", "unclassified"),
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
        "settlement_currency_target": "USDC",
        "settlement_currency_options": ["USD", "USDC", "USDG"],
        "account_settlement_confirmed": False,
        "asset_class_counts": {
            asset_class: sum(1 for info in selected if info.get("asset_class") == asset_class)
            for asset_class in ("crypto", "equity", "precious_metal")
        },
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
