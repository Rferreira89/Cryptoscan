"""Public historical spot data pipeline for the isolated Quick Opportunities engine.

Bybit and OKX are supported as independent venues. This module never calls
private endpoints and never creates orders. Spot candles are price proxies:
SHORT results do not prove margin/borrow/perpetual executability.
"""
import argparse
import json
import time
from pathlib import Path

from engine.sources import _get, _candle, SourceError
from engine.quick_opportunities import (
    backtest_series, evaluate_by_family, prepare_30m_candles,
)
from engine import quick_opportunities_derivatives as DERIV

INTERVAL_MS = {"30m": 30 * 60 * 1000}
BINANCE_KLINES = "https://data-api.binance.vision/api/v3/klines"
BYBIT_KLINES = "https://api.bybit.eu/v5/market/kline"
OKX_HISTORY = "https://www.okx.com/api/v5/market/history-candles"
PAGE_LIMITS = {"binance": 1000, "bybit": 1000, "okx": 300}


def _validate_request(symbol, start_ms, end_ms, interval):
    if interval not in INTERVAL_MS:
        raise ValueError("intervalo nao suportado")
    if not symbol or not symbol.upper().endswith("USDT"):
        raise ValueError("symbol deve ser um par USDT, por exemplo ETHUSDT")
    step = INTERVAL_MS[interval]
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    if start_ms % step or end_ms % step:
        raise ValueError("start_ms e end_ms devem estar alinhados a velas")


def _convert_binance(item):
    return _candle(item[0], item[1], item[2], item[3], item[4], item[5], item[9])


def _convert_bybit(item):
    # Bybit v5 kline: [startTime, open, high, low, close, volume, turnover]
    return _candle(item[0], item[1], item[2], item[3], item[4], item[5])


def _convert_okx(item):
    # OKX history-candles: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    return _candle(item[0], item[1], item[2], item[3], item[4], item[5])


def fetch_binance_history(symbol, start_ms, end_ms, interval="30m",
                          request=_get, pause_seconds=0.15):
    """Download a complete [start_ms,end_ms) Binance Spot interval."""
    _validate_request(symbol, start_ms, end_ms, interval)
    step, rows, cursor = INTERVAL_MS[interval], [], start_ms
    while cursor < end_ms:
        batch = request(BINANCE_KLINES, {
            "symbol": symbol.upper(), "interval": interval,
            "startTime": cursor, "endTime": end_ms - 1,
            "limit": PAGE_LIMITS["binance"],
        })
        if not isinstance(batch, list):
            raise SourceError(f"resposta Binance invalida para {symbol}")
        if not batch:
            break
        rows.extend(_convert_binance(x) for x in batch
                    if start_ms <= int(x[0]) < end_ms)
        newest = max(int(x[0]) for x in batch)
        cursor_next = newest + step
        if cursor_next <= cursor:
            raise SourceError("paginacao Binance sem progresso")
        cursor = cursor_next
        if len(batch) < PAGE_LIMITS["binance"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return _dedupe(rows)


def fetch_bybit_history(symbol, start_ms, end_ms, interval="30m",
                        request=_get, pause_seconds=0.15):
    """Download Bybit Spot klines in ascending time using start/end paging."""
    _validate_request(symbol, start_ms, end_ms, interval)
    step, rows, cursor = INTERVAL_MS[interval], [], start_ms
    while cursor < end_ms:
        response = request(BYBIT_KLINES, {
            "category": "spot", "symbol": symbol.upper(),
            "interval": "30", "start": cursor, "end": end_ms - 1,
            "limit": PAGE_LIMITS["bybit"],
        })
        if not isinstance(response, dict) or response.get("retCode") != 0:
            raise SourceError(f"resposta Bybit invalida: {response}")
        batch = response.get("result", {}).get("list", [])
        if not batch:
            break
        rows.extend(_convert_bybit(x) for x in batch
                    if start_ms <= int(x[0]) < end_ms)
        newest = max(int(x[0]) for x in batch)
        next_cursor = newest + step
        if next_cursor <= cursor:
            raise SourceError("paginacao Bybit sem progresso")
        cursor = next_cursor
        if len(batch) < PAGE_LIMITS["bybit"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return _dedupe(rows)


def fetch_okx_history(symbol, start_ms, end_ms, interval="30m",
                      request=_get, pause_seconds=0.15):
    """Download OKX history-candles backwards, then return ascending candles."""
    _validate_request(symbol, start_ms, end_ms, interval)
    step, rows = INTERVAL_MS[interval], []
    # OKX 'after' requests candles older than the supplied timestamp.
    cursor = end_ms
    while cursor > start_ms:
        response = request(OKX_HISTORY, {
            "instId": symbol.upper().replace("USDT", "-USDT"),
            "bar": "30m", "after": cursor, "limit": PAGE_LIMITS["okx"],
        })
        if not isinstance(response, dict) or response.get("code") != "0":
            raise SourceError(f"resposta OKX invalida: {response}")
        batch = response.get("data", [])
        if not batch:
            break
        # Ignore the still-forming candle (confirm != 1).
        rows.extend(_convert_okx(x) for x in batch
                    if int(x[0]) >= start_ms and int(x[0]) < end_ms
                    and (len(x) < 9 or str(x[8]) == "1"))
        oldest = min(int(x[0]) for x in batch)
        next_cursor = oldest
        if next_cursor >= cursor:
            raise SourceError("paginacao OKX sem progresso")
        cursor = next_cursor
        if oldest <= start_ms or len(batch) < PAGE_LIMITS["okx"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return _dedupe(rows)


def _dedupe(rows):
    by_time = {row["t"]: row for row in rows}
    return [by_time[t] for t in sorted(by_time)]


FETCHERS = {
    "binance": fetch_binance_history,
    "bybit": fetch_bybit_history,
    "okx": fetch_okx_history,
}


def fetch_history(venue, symbol, start_ms, end_ms, interval="30m",
                  request=_get, pause_seconds=0.15):
    try:
        fetcher = FETCHERS[venue.lower()]
    except KeyError as exc:
        raise ValueError("venue deve ser binance, bybit ou okx") from exc
    return fetcher(symbol, start_ms, end_ms, interval=interval,
                   request=request, pause_seconds=pause_seconds)


def run_symbol(symbol, start_ms, end_ms, output_dir, venue="bybit",
               fee_pct=0.1, slippage_pct=0.05, funding_pct=0.0,
               request=_get):
    """Fetch, validate, backtest and persist one venue/symbol research run."""
    venue = venue.lower()
    candles = fetch_history(venue, symbol, start_ms, end_ms, request=request)
    # Validate against the requested historical boundary, not the wall clock.
    validation_time = end_ms // 1000
    clean, validation = prepare_30m_candles(candles, validation_time)
    if validation["status"] == "DATA INVALID":
        raise SourceError(f"{venue}/{symbol}: dados invalidos: {validation['issues']}")
    trades = backtest_series(clean, asset=symbol, fee_pct=fee_pct,
                             slippage_pct=slippage_pct,
                             funding_pct=funding_pct)
    report = {
        "schema_version": 2, "engine": "quick_opportunities",
        "venue": venue, "market_type": "spot", "symbol": symbol.upper(),
        "timeframe": "30m", "requested_start_ms": start_ms,
        "requested_end_ms": end_ms, "candles": len(clean),
        "validation": validation,
        "cost_assumptions_pct": {
            "fee_per_side": fee_pct, "slippage_per_side": slippage_pct,
            "funding_per_trade": funding_pct, "funding_is_historical": False,
        },
        "short_execution_validated": False, "trades": trades,
        "by_family_side_regime": evaluate_by_family(trades),
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.upper().replace("/", "_")
    (out / f"{venue}_{safe_symbol}_30m.json").write_text(
        json.dumps({"metadata": {k: v for k, v in report.items()
                                 if k not in ("trades", "by_family_side_regime")},
                    "candles": clean}, indent=2), encoding="utf-8")
    (out / f"{venue}_{safe_symbol}_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report



def run_derivatives_symbol(symbol, start_ms, end_ms, output_dir, venue="okx",
                           fee_pct=0.05, slippage_pct=0.05, request=_get):
    """Backtest verified linear perpetual contracts with historical funding."""
    venue = venue.lower()
    instruments = DERIV.list_linear_perpetuals(venue, request=request)
    info = instruments.get(symbol.upper())
    if not info:
        raise SourceError(f"{venue}/{symbol}: contrato linear USDT perpétuo indisponível")
    if venue == "okx":
        candles = DERIV.fetch_okx_swap_candles(info["inst_id"], start_ms, end_ms, request=request)
    else:
        candles = DERIV.fetch_bybit_linear_candles(info["inst_id"], start_ms, end_ms, request=request)
    funding = DERIV.fetch_funding_history(venue, info["inst_id"], start_ms, end_ms, request=request)
    clean, validation = prepare_30m_candles(candles, end_ms // 1000)
    if validation["status"] == "DATA INVALID":
        raise SourceError(f"{venue}/{symbol}: dados invalidos: {validation['issues']}")
    trades = backtest_series(clean, asset=symbol, fee_pct=fee_pct,
                             slippage_pct=slippage_pct, funding_events=funding)
    report = {
        "schema_version": 3, "engine": "quick_opportunities",
        "venue": venue, "market_type": "linear_perpetual", "instrument": info,
        "symbol": symbol.upper(), "timeframe": "30m",
        "requested_start_ms": start_ms, "requested_end_ms": end_ms,
        "candles": len(clean), "funding_events": len(funding),
        "funding_source": "historical_exchange_realized_rates",
        "validation": validation,
        "cost_assumptions_pct": {"fee_per_side": fee_pct,
                                 "slippage_per_side": slippage_pct,
                                 "funding_historical": True},
        "short_execution_validated": False, "trades": trades,
        "by_family_side_regime": evaluate_by_family(trades),
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{venue}_{symbol.upper()}_linear_perpetual_30m.json").write_text(
        json.dumps({"metadata": {k: v for k, v in report.items()
                                 if k not in ("trades", "by_family_side_regime")},
                    "candles": clean, "funding_events": funding},
                   indent=2), encoding="utf-8")
    (out / f"{venue}_{symbol.upper()}_linear_perpetual_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


def _parse_date_ms(value):
    from datetime import datetime, timezone
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datas devem incluir fuso horario, preferencialmente Z")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Quick Opportunities research backtest")
    parser.add_argument("--venue", choices=("bybit", "okx", "binance", "both", "okx-futures", "bybit-futures", "both-futures"),
                        default="both")
    parser.add_argument("--symbols", required=True,
                        help="pares separados por virgula, ex. BTCUSDT,ETHUSDT")
    parser.add_argument("--start", required=True, help="ISO-8601 UTC")
    parser.add_argument("--end", required=True, help="ISO-8601 UTC exclusivo")
    parser.add_argument("--out", default="backtest/quick-opportunities-data")
    parser.add_argument("--fee-pct", type=float, default=0.1)
    parser.add_argument("--slippage-pct", type=float, default=0.05)
    args = parser.parse_args(argv)
    start_ms, end_ms = _parse_date_ms(args.start), _parse_date_ms(args.end)
    venues = (("bybit", "okx-futures") if args.venue == "both" else
              ("bybit-futures", "okx-futures") if args.venue == "both-futures" else
              (args.venue,))
    summaries = []
    for venue in venues:
        for symbol in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
            if venue.endswith("-futures"):
                summaries.append(run_derivatives_symbol(
                    symbol, start_ms, end_ms, args.out,
                    venue=venue.removesuffix("-futures"),
                    fee_pct=args.fee_pct, slippage_pct=args.slippage_pct))
            else:
                summaries.append(run_symbol(symbol, start_ms, end_ms, args.out,
                                             venue=venue, fee_pct=args.fee_pct,
                                             slippage_pct=args.slippage_pct))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
