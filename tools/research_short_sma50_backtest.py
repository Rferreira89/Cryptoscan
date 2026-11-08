"""Historical PAPER comparison for the BTC SMA50 SHORT regime gate.

Compares the existing CryptoScan SHORT candidates with and without
the research gate. No exchange connection and no order execution.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from multiprocessing import Pool

from engine import backtest as B
from engine import config, short as SH, stats
from tools import run_backtest_short as RBS
from tools.research_short_sma50 import (
    DailyBar,
    approve_existing_short_candidate,
)

DATA = {}
DAILY = {}
BTC_REGIMES = {}


def daily_bars_as_of(rows, signal_time):
    """Return only completed UTC daily candles known at signal time."""
    return [
        DailyBar(
            timestamp=datetime.fromtimestamp(row["t"], timezone.utc),
            open=row["o"],
            high=row["h"],
            low=row["l"],
            close=row["c"],
            volume=row.get("v", 0.0),
        )
        for row in rows
        if row["t"] + B.DAY <= signal_time
    ]


def work_asset(asset):
    """Generate existing SHORT candidates and evaluate them in PAPER."""
    candles = DATA[asset]
    mirrored = SH.mirror(candles)
    candidates = B.candidates(
        asset, mirrored, BTC_REGIMES, RBS.CFG
    )

    output = []
    for candidate in candidates:
        candidate["strategy"] += SH.SUFFIX

        gate = approve_existing_short_candidate(
            True,
            daily_bars_as_of(DAILY["BTC"], candidate["t"]),
            daily_bars_as_of(DAILY[asset], candidate["t"]),
        )

        result = RBS.simulate(candidate, candles)
        output.append((candidate, result, gate.approved, gate.reason))

    return output


def metrics_for(trades, start, end):
    return stats.metrics(trades, max(1, end - start))


def compare_windows(trades, start, split, end):
    development = [
        trade for trade in trades
        if trade["t"] < split and trade["exit_t"] < split
    ]
    holdout = [
        trade for trade in trades
        if trade["t"] >= split
    ]
    crossing = [
        trade for trade in trades
        if trade["t"] < split <= trade["exit_t"]
    ]

    return {
        "all": metrics_for(trades, start, end),
        "development_80pct": metrics_for(development, start, split),
        "holdout_20pct": metrics_for(holdout, split, end),
        "trades_crossing_split_excluded": len(crossing),
    }


def main(history_dir, delisted_dir, destination):
    global DATA, DAILY, BTC_REGIMES

    current, skipped_current = B.load_all(history_dir, min_bars=1500)
    delisted, skipped_delisted = B.load_all(delisted_dir, min_bars=1500)

    DATA = dict(current)
    for asset, candles in delisted.items():
        DATA.setdefault(asset, candles)

    if "BTC" not in DATA:
        raise RuntimeError("BTC history is missing")

    DAILY = {asset: B.daily(candles) for asset, candles in DATA.items()}
    BTC_REGIMES = B.regimes(SH.mirror(DATA["BTC"]))

    start = min(row["t"] for row in DATA["BTC"])
    end = max(row["t"] for row in DATA["BTC"]) + B.H4
    split = start + int(0.8 * (end - start))

    all_candidates = []
    all_results = []
    gated_candidates = []
    gated_results = []
    reasons = Counter()

    assets = [asset for asset in sorted(DATA) if asset != "BTC"]

    with Pool(processes=max(1, min(4, os.cpu_count() or 1))) as pool:
        for rows in pool.imap_unordered(work_asset, assets):
            for candidate, result, approved, reason in rows:
                all_candidates.append(candidate)
                all_results.append(result)
                reasons[reason] += 1

                if approved:
                    gated_candidates.append(candidate)
                    gated_results.append(result)

    # Match the existing SHORT backtest portfolio selection rules.
    portfolio_cfg = dict(config.load(), max_open_positions=4)

    baseline = stats.select(
        all_candidates, all_results, portfolio_cfg
    )
    filtered = stats.select(
        gated_candidates, gated_results, portfolio_cfg
    )

    report = {
        "mode": "PAPER_ONLY",
        "gate": "BTC_SMA50_existing_short_candidates",
        "data": {
            "current_assets_loaded": len(current),
            "delisted_assets_loaded": len(delisted),
            "combined_assets_used": len(DATA),
            "current_assets_skipped": skipped_current,
            "delisted_assets_skipped": skipped_delisted,
            "start_utc": datetime.fromtimestamp(
                start, timezone.utc
            ).isoformat(),
            "end_utc": datetime.fromtimestamp(
                end, timezone.utc
            ).isoformat(),
            "development_holdout_split_utc": datetime.fromtimestamp(
                split, timezone.utc
            ).isoformat(),
        },
        "cost_model": {
            "fee_pct_per_side": RBS.CFG["fee_pct"],
            "slippage_pct": B.SLIP_PCT,
            "borrow_daily_pct_assumed": RBS.BORROW_DAILY_PCT,
            "borrow_cost_note": (
                "Spot-margin borrow assumption used by the existing "
                "SHORT backtest; this is not perpetual funding."
            ),
        },
        "signals": {
            "existing_candidates": len(all_candidates),
            "gate_approved": len(gated_candidates),
            "gate_rejected": len(all_candidates) - len(gated_candidates),
            "approval_rate_pct": round(
                100 * len(gated_candidates) / len(all_candidates), 2
            ) if all_candidates else 0,
            "gate_rejection_reasons": dict(reasons),
        },
        "baseline_without_gate": compare_windows(
            baseline, start, split, end
        ),
        "filtered_with_gate": compare_windows(
            filtered, start, split, end
        ),
        "restrictions": [
            "No new signals are generated by the gate.",
            "No exchange connection or orders are used.",
            "No production configuration is changed.",
            "The final 20% is chronological holdout data.",
            "Results are research evidence, not live authorization.",
        ],
    }

    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    with open(destination, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python -m tools.research_short_sma50_backtest "
            "<history_dir> <delisted_dir> <output.json>"
        )
    main(sys.argv[1], sys.argv[2], sys.argv[3])
