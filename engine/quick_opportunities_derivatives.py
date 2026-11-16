"""Public linear perpetual-futures data adapters for Quick Opportunities.

OKX instruments are USDT-settled linear SWAPs (the OKX perpetual contract
market). Bybit uses linear USDT contracts where available. This module is
read-only: no private endpoints, credentials, margin changes or orders.
"""
import time

from .sources import _get, _candle, SourceError

OKX = "https://www.okx.com"
BYBIT = "https://api.bybit.com"
BAR_MS = 30 * 60 * 1000
PAGE = {"okx": 300, "bybit": 1000}


def _require_range(start_ms, end_ms):
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    if start_ms % BAR_MS or end_ms % BAR_MS:
        raise ValueError("datas devem estar alinhadas a velas de 30m")


def okx_linear_usdt_swaps(request=_get):
    """Return live OKX linear USDT-settled perpetual instruments by base asset."""
    response = request(OKX + "/api/v5/public/instruments",
                       {"instType": "SWAP"})
    if not isinstance(response, dict) or response.get("code") != "0":
        raise SourceError(f"OKX instruments SWAP: resposta invalida {response}")
    out = {}
    for item in response.get("data", []):
        if (item.get("state") != "live" or item.get("settleCcy") != "USDT"
                or item.get("ctType") != "linear"
                or not item.get("instId", "").endswith("-USDT-SWAP")):
            continue
        try:
            info = {
                "venue": "okx", "market_type": "linear_perpetual",
                "inst_id": item["instId"], "base": item["instId"].split("-")[0],
                "quote": "USDT", "settle": item["settleCcy"],
                "contract_value": float(item["ctVal"]),
                "contract_value_currency": item.get("ctValCcy"),
                "contract_multiplier": float(item.get("ctMult") or 1),
                "min_size": float(item["minSz"]), "lot_size": float(item["lotSz"]),
                "tick_size": float(item["tickSz"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"OKX contrato com metadados invalidos: {item}") from exc
        if info["contract_value"] <= 0 or info["min_size"] <= 0 or info["lot_size"] <= 0:
            raise SourceError(f"OKX contrato com especificacao nao positiva: {item['instId']}")
        out[info["base"]] = info
    return out


def bybit_linear_usdt_perpetuals(request=_get):
    """Return live Bybit linear USDT perpetual contracts by base asset."""
    response = request(BYBIT + "/v5/market/instruments-info", {
        "category": "linear", "limit": 1000,
    })
    if not isinstance(response, dict) or response.get("retCode") != 0:
        raise SourceError(f"Bybit instruments linear: resposta invalida {response}")
    out = {}
    for item in response.get("result", {}).get("list", []):
        if (item.get("status") != "Trading" or item.get("quoteCoin") != "USDT"
                or item.get("settleCoin") != "USDT"
                or item.get("contractType") != "LinearPerpetual"):
            continue
        symbol = item.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue
        lot = item.get("lotSizeFilter") or {}
        price = item.get("priceFilter") or {}
        try:
            out[symbol[:-4]] = {
                "venue": "bybit", "market_type": "linear_perpetual",
                "inst_id": symbol, "base": symbol[:-4], "quote": "USDT",
                "settle": "USDT", "contract_value": 1.0,
                "contract_value_currency": "base",
                "min_size": float(lot["minOrderQty"]),
                "lot_size": float(lot["qtyStep"]),
                "tick_size": float(price["tickSize"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"Bybit contrato com metadados invalidos: {symbol}") from exc
    return out


def list_linear_perpetuals(venue, request=_get):
    if venue == "okx":
        return okx_linear_usdt_swaps(request)
    if venue == "bybit":
        return bybit_linear_usdt_perpetuals(request)
    raise ValueError("venue deve ser okx ou bybit")


def _okx_candle(row):
    if len(row) < 9:
        raise SourceError("OKX candle sem campo confirm")
    return _candle(row[0], row[1], row[2], row[3], row[4], row[5])


def fetch_okx_swap_candles(inst_id, start_ms, end_ms, request=_get,
                           pause_seconds=0.12):
    """Fetch confirmed OKX SWAP 30m candles over [start_ms,end_ms)."""
    _require_range(start_ms, end_ms)
    rows, cursor = [], end_ms
    while cursor > start_ms:
        response = request(OKX + "/api/v5/market/history-candles", {
            "instId": inst_id, "bar": "30m", "after": cursor,
            "limit": PAGE["okx"],
        })
        if not isinstance(response, dict) or response.get("code") != "0":
            raise SourceError(f"OKX history-candles: resposta invalida {response}")
        batch = response.get("data") or []
        if not batch:
            break
        for item in batch:
            ts = int(item[0])
            if start_ms <= ts < end_ms and str(item[8]) == "1":
                rows.append(_okx_candle(item))
        oldest = min(int(item[0]) for item in batch)
        if oldest >= cursor:
            raise SourceError("paginacao OKX SWAP sem progresso")
        cursor = oldest
        if oldest <= start_ms or len(batch) < PAGE["okx"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    by_ts = {row["t"]: row for row in rows}
    return [by_ts[t] for t in sorted(by_ts)]


def fetch_bybit_linear_candles(symbol, start_ms, end_ms, request=_get,
                               pause_seconds=0.12):
    """Fetch Bybit linear USDT perpetual 30m candles over [start_ms,end_ms)."""
    _require_range(start_ms, end_ms)
    rows, cursor = [], start_ms
    while cursor < end_ms:
        response = request(BYBIT + "/v5/market/kline", {
            "category": "linear", "symbol": symbol,
            "interval": "30", "start": cursor, "end": end_ms - 1,
            "limit": PAGE["bybit"],
        })
        if not isinstance(response, dict) or response.get("retCode") != 0:
            raise SourceError(f"Bybit linear kline: resposta invalida {response}")
        batch = response.get("result", {}).get("list") or []
        if not batch:
            break
        for item in batch:
            ts = int(item[0])
            if start_ms <= ts < end_ms:
                rows.append(_candle(item[0], item[1], item[2], item[3],
                                    item[4], item[5]))
        newest = max(int(item[0]) for item in batch)
        next_cursor = newest + BAR_MS
        if next_cursor <= cursor:
            raise SourceError("paginacao Bybit linear sem progresso")
        cursor = next_cursor
        if len(batch) < PAGE["bybit"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    by_ts = {row["t"]: row for row in rows}
    return [by_ts[t] for t in sorted(by_ts)]


def fetch_okx_funding_history(inst_id, start_ms, end_ms, request=_get,
                              pause_seconds=0.12):
    """Return realized OKX funding events as (timestamp_seconds, rate).

    OKX documents only three months of funding-rate history. Refuse longer
    requests rather than silently running a backtest with missing carry costs.
    """
    if end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    if end_ms - start_ms > 90 * 24 * 60 * 60 * 1000:
        raise ValueError("OKX funding history is limited to 3 months; shorten the interval")
    rows, cursor = [], end_ms
    while cursor > start_ms:
        response = request(OKX + "/api/v5/public/funding-rate-history", {
            "instId": inst_id, "after": cursor, "limit": 100,
        })
        if not isinstance(response, dict) or response.get("code") != "0":
            raise SourceError(f"OKX funding history: resposta invalida {response}")
        batch = response.get("data") or []
        if not batch:
            break
        for item in batch:
            ts = int(item["fundingTime"])
            if start_ms <= ts < end_ms:
                rate = item.get("realizedRate")
                if rate in (None, ""):
                    rate = item.get("fundingRate")
                rows.append((ts // 1000, float(rate)))
        oldest = min(int(item["fundingTime"]) for item in batch)
        if oldest >= cursor:
            raise SourceError("paginacao OKX funding sem progresso")
        cursor = oldest
        if oldest <= start_ms or len(batch) < 100:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return sorted(set(rows))


def fetch_bybit_funding_history(symbol, start_ms, end_ms, request=_get,
                                pause_seconds=0.12):
    """Return Bybit linear funding events as (timestamp_seconds, rate)."""
    if end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    rows, cursor = [], start_ms
    while cursor < end_ms:
        response = request(BYBIT + "/v5/market/funding/history", {
            "category": "linear", "symbol": symbol,
            "startTime": cursor, "endTime": end_ms - 1, "limit": 200,
        })
        if not isinstance(response, dict) or response.get("retCode") != 0:
            raise SourceError(f"Bybit funding history: resposta invalida {response}")
        batch = response.get("result", {}).get("list") or []
        if not batch:
            break
        for item in batch:
            ts = int(item["fundingRateTimestamp"])
            if start_ms <= ts < end_ms:
                rows.append((ts // 1000, float(item["fundingRate"])))
        newest = max(int(item["fundingRateTimestamp"]) for item in batch)
        next_cursor = newest + 1
        if next_cursor <= cursor:
            raise SourceError("paginacao Bybit funding sem progresso")
        cursor = next_cursor
        if len(batch) < 200:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return sorted(set(rows))


def fetch_funding_history(venue, instrument, start_ms, end_ms, request=_get):
    if venue == "okx":
        return fetch_okx_funding_history(instrument, start_ms, end_ms, request)
    if venue == "bybit":
        return fetch_bybit_funding_history(instrument, start_ms, end_ms, request)
    raise ValueError("venue deve ser okx ou bybit")
