"""Paper-only BTC SMA50 regime gate for existing SHORT candidates.

This module does not generate trading signals, connect to exchanges,
submit orders, or modify production configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class DailyBar:
    """A completed daily candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class GateResult:
    """Result of the paper-only regime filter."""

    approved: bool
    reason: str
    metrics: Optional[dict[str, float]] = None


def _utc_datetime(value: datetime) -> datetime:
    """Normalize a datetime to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def aggregate_4h_to_daily(
    bars: Iterable[DailyBar],
    as_of: Optional[datetime] = None,
) -> list[DailyBar]:
    """Aggregate six complete 4H candles into completed UTC daily candles.

    Only candles starting at 00:00, 04:00, 08:00, 12:00, 16:00
    and 20:00 UTC are accepted. The current UTC day is excluded.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    current_day = _utc_datetime(as_of).date()

    grouped: dict[date, list[DailyBar]] = {}

    for bar in bars:
        timestamp = _utc_datetime(bar.timestamp)

        if timestamp.minute != 0 or timestamp.second != 0:
            continue
        if timestamp.hour not in (0, 4, 8, 12, 16, 20):
            continue
        if timestamp.date() >= current_day:
            continue

        grouped.setdefault(timestamp.date(), []).append(
            DailyBar(
                timestamp=timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )

    daily: list[DailyBar] = []

    expected_hours = (0, 4, 8, 12, 16, 20)

    for day in sorted(grouped):
        candles = sorted(
            grouped[day],
            key=lambda candle: _utc_datetime(candle.timestamp),
        )

        actual_hours = tuple(
            _utc_datetime(candle.timestamp).hour
            for candle in candles
        )

        if actual_hours != expected_hours or len(candles) != 6:
            continue

        daily.append(
            DailyBar(
                timestamp=datetime(
                    day.year,
                    day.month,
                    day.day,
                    tzinfo=timezone.utc,
                ),
                open=candles[0].open,
                high=max(candle.high for candle in candles),
                low=min(candle.low for candle in candles),
                close=candles[-1].close,
                volume=sum(candle.volume for candle in candles),
            )
        )

    return daily


def _sma(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("Insufficient values for moving average")
    return sum(values[-period:]) / period


def _return_pct(current: float, previous: float) -> float:
    if previous <= 0:
        raise ValueError("Previous close must be positive")
    return ((current / previous) - 1.0) * 100.0


def evaluate_short_regime(
    btc_daily: Sequence[DailyBar],
    asset_daily: Sequence[DailyBar],
) -> GateResult:
    """Evaluate whether an existing SHORT candidate passes the paper gate.

    Requirements:
    - At least 55 aligned completed daily candles.
    - BTC below its SMA50.
    - BTC SMA50 below its value five sessions earlier.
    - BTC 30-session return negative.
    - Asset below SMA20 and SMA50.
    - Asset 30-session return negative and weaker than BTC.
    """
    btc_by_date = {
        _utc_datetime(bar.timestamp).date(): bar
        for bar in btc_daily
    }
    asset_by_date = {
        _utc_datetime(bar.timestamp).date(): bar
        for bar in asset_daily
    }

    common_dates = sorted(set(btc_by_date) & set(asset_by_date))

    if len(common_dates) < 55:
        return GateResult(
            approved=False,
            reason="insufficient_aligned_history",
        )

    common_dates = common_dates[-55:]

    btc_closes = [btc_by_date[day].close for day in common_dates]
    asset_closes = [asset_by_date[day].close for day in common_dates]

    if any(value <= 0 for value in btc_closes + asset_closes):
        return GateResult(
            approved=False,
            reason="invalid_close_price",
        )

    btc_sma50 = _sma(btc_closes, 50)
    btc_sma50_previous = _sma(btc_closes[:-5], 50)
    btc_return_30d = _return_pct(btc_closes[-1], btc_closes[-31])

    asset_sma20 = _sma(asset_closes, 20)
    asset_sma50 = _sma(asset_closes, 50)
    asset_return_30d = _return_pct(
        asset_closes[-1],
        asset_closes[-31],
    )

    metrics = {
        "btc_close": btc_closes[-1],
        "btc_sma50": btc_sma50,
        "btc_sma50_five_sessions_ago": btc_sma50_previous,
        "btc_return_30d_pct": btc_return_30d,
        "asset_close": asset_closes[-1],
        "asset_sma20": asset_sma20,
        "asset_sma50": asset_sma50,
        "asset_return_30d_pct": asset_return_30d,
    }

    checks = (
        (btc_closes[-1] < btc_sma50, "btc_not_below_sma50"),
        (
            btc_sma50 < btc_sma50_previous,
            "btc_sma50_not_falling",
        ),
        (btc_return_30d < 0, "btc_30d_return_not_negative"),
        (
            asset_closes[-1] < asset_sma20,
            "asset_not_below_sma20",
        ),
        (
            asset_sma20 < asset_sma50,
            "asset_sma20_not_below_sma50",
        ),
        (
            asset_return_30d < 0,
            "asset_30d_return_not_negative",
        ),
        (
            asset_return_30d < btc_return_30d,
            "asset_not_weaker_than_btc",
        ),
    )

    for passed, reason in checks:
        if not passed:
            return GateResult(
                approved=False,
                reason=reason,
                metrics=metrics,
            )

    return GateResult(
        approved=True,
        reason="paper_short_regime_approved",
        metrics=metrics,
    )


def approve_existing_short_candidate(
    existing_short_signal: bool,
    btc_daily: Sequence[DailyBar],
    asset_daily: Sequence[DailyBar],
) -> GateResult:
    """Approve or reject an existing SHORT signal.

    This function never creates a signal. It only evaluates an
    already-existing candidate and returns a paper-only decision.
    """
    if not existing_short_signal:
        return GateResult(
            approved=False,
            reason="no_existing_short_candidate",
        )

    return evaluate_short_regime(btc_daily, asset_daily)
