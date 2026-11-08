
# Research: BTC SMA50 Short Regime Gate

## 1. Objective

Investigate whether a BTC SMA50 bearish-regime filter can improve the quality of existing SHORT candidates.

This research is isolated from production and does not authorize live trading.

## 2. Execution mode

**PAPER ONLY**

The research module:
- Does not connect to exchanges.
- Does not submit, modify, or cancel orders.
- Does not open or close positions.
- Does not change production configuration.
- Does not activate any trading strategy.

## 3. Regime conditions

An existing SHORT candidate is approved for paper evaluation only when all conditions are met:

1. At least 55 aligned completed daily candles are available.
2. BTC closes below its SMA50.
3. BTC SMA50 is below its value five sessions earlier.
4. BTC 30-session return is negative.
5. The candidate asset closes below its SMA20.
6. The asset SMA20 is below its SMA50.
7. The asset 30-session return is negative.
8. The asset underperforms BTC over the same 30-session period.

## 4. Data requirements

- Use completed UTC daily candles.
- Aggregate six valid 4-hour candles per day.
- Exclude the current incomplete UTC day.
- Align BTC and asset candles by date.
- Reject insufficient or invalid price history.

## 5. Signal handling

The filter evaluates an existing SHORT candidate.

It must never generate a new trading signal by itself.

A rejected candidate remains rejected for this research evaluation.

## 6. Validation plan

Before considering any promotion:

- Run historical backtests.
- Include fees, spread, slippage and funding costs.
- Compare results against the existing SHORT baseline.
- Use chronological out-of-sample validation.
- Measure expectancy, profit factor, drawdown and trade frequency.
- Check robustness across different market regimes and assets.
- Avoid promotion based only on a small sample.

## 7. Promotion restrictions

No strategy may be activated in REAL mode based solely on this research.

Any production change requires separate explicit approval.

## 8. Current status

- Research branch: `research/short-regime-paper-20261108`
- Initial implementation: committed.
- Unit tests: committed.
- Documentation: in progress.
- Production changes: none authorized.
