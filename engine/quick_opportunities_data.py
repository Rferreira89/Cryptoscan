"""Historical public spot data and reproducible research runner for Quick Opportunities.

This module is deliberately disconnected from live scanner/execution code.
Binance public klines are used as the first long-history adapter. Spot candles
are price proxies only: SHORT results are not proof of borrow/perpetual
availability or executable short PnL.
"""
import argparse
import json
import time
from pathlib import Path

from engine.sources import _get, _candle, SourceError, TF_SECONDS
from engine.quick_opportunities import (
    backtest_series, evaluate_by_family, prepare_30m_candles,
)

BINANCE_KLINES = "https://data-api.binance.vision/api/v3/klines"
INTERVAL_MS = {"30m": 30 * 60 * 1000}
PAGE_LIMIT = 1000


def fetch_binance_history(symbol, start_ms, end_ms, interval="30m",
                          request=_get, pause_seconds=0.15):
    """Download a complete [start_ms,end_ms) interval with deterministic paging."""
    if interval not in INTERVAL_MS:
        raise ValueError("intervalo nao suportado")
    if not symbol or not symbol.endswith("USDT"):
        raise ValueError("symbol deve ser um par USDT, por exemplo ETHUSDT")
    step = INTERVAL_MS[interval]
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    if start_ms % step or end_ms % step:
        raise ValueError("start_ms e end_ms devem estar alinhados a velas")
    rows, cursor = [], start_ms
    while cursor < end_ms:
        batch = request(BINANCE_KLINES, {
            "symbol": symbol.upper(), "interval": interval,
            "startTime": cursor, "endTime": end_ms - 1,
            "limit": PAGE_LIMIT,
        })
        if not isinstance(batch, list):
            raise SourceError(f"resposta de klines invalida para {symbol}")
        if not batch:
            break
        for item in batch:
            ts = int(item[0])
            if start_ms <= ts < end_ms:
                rows.append(_candle(ts, item[1], item[2], item[3],
                                    item[4], item[5], item[9]))
        newest = max(int(item[0]) for item in batch)
        next_cursor = newest + step
        if next_cursor <= cursor:
            raise SourceError("paginacao sem progresso; descarga interrompida")
        cursor = next_cursor
        if len(batch) < PAGE_LIMIT:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    by_time = {row["t"]: row for row in rows}
    return [by_time[t] for t in sorted(by_time)]


def run_symbol(symbol, start_ms, end_ms, output_dir,
               fee_pct=0.1, slippage_pct=0.05, funding_pct=0.0,
               request=_get):
    """Fetch, validate, backtest and persist one symbol's isolated results."""
    candles = fetch_binance_history(symbol, start_ms, end_ms, request=request)
    now = int(time.time())
    clean, validation = prepare_30m_candles(candles, now)
    if validation["status"] == "DATA INVALID":
        raise SourceError(f"{symbol}: dados invalidos: {validation['issues']}")
    trades = backtest_series(clean, asset=symbol, fee_pct=fee_pct,
                             slippage_pct=slippage_pct,
                             funding_pct=funding_pct)
    report = {
        "schema_version": 1,
        "engine": "quick_opportunities",
        "venue": "binance_spot",
        "symbol": symbol.upper(),
        "timeframe": "30m",
        "requested_start_ms": start_ms,
        "requested_end_ms": end_ms,
        "candles": len(clean),
        "validation": validation,
        "cost_assumptions_pct": {
            "fee_per_side": fee_pct,
            "slippage_per_side": slippage_pct,
            "funding_per_trade": funding_pct,
            "funding_is_historical": False,
        },
        "short_execution_validated": False,
        "trades": trades,
        "by_family_side_regime": evaluate_by_family(trades),
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.upper().replace("/", "_")
    (out / f"{safe_symbol}_30m.json").write_text(
        json.dumps({"metadata": {k: v for k, v in report.items()
                                 if k not in ("trades", "by_family_side_regime")},
                    "candles": clean}, indent=2),
        encoding="utf-8")
    (out / f"{safe_symbol}_report.json").write_text(
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
    parser.add_argument("--symbols", required=True,
                        help="pares separados por virgula, ex. BTCUSDT,ETHUSDT")
    parser.add_argument("--start", required=True, help="ISO-8601 UTC, ex. 2026-01-01T00:00:00Z")
    parser.add_argument("--end", required=True, help="ISO-8601 UTC exclusivo")
    parser.add_argument("--out", default="backtest/quick-opportunities-data")
    parser.add_argument("--fee-pct", type=float, default=0.1)
    parser.add_argument("--slippage-pct", type=float, default=0.05)
    args = parser.parse_args(argv)
    start_ms, end_ms = _parse_date_ms(args.start), _parse_date_ms(args.end)
    summaries = []
    for symbol in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
        summaries.append(run_symbol(symbol, start_ms, end_ms, args.out,
                                     fee_pct=args.fee_pct,
                                     slippage_pct=args.slippage_pct))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
