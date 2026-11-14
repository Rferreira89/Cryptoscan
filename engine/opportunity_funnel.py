
"""Opportunity Funnel: registo auditável de oportunidades.

Cria eventos em memória ou regista-os em JSONL.
Não gera sinais nem envia ordens.
"""

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

STAGES = {
    "universe_detected",
    "eligibility_passed",
    "eligibility_rejected",
    "deep_analysis_started",
    "deep_analysis_skipped",
    "signal_generated",
    "signal_rejected",
    "execution_candidate",
    "order_submitted",
    "order_rejected",
    "order_filled",
    "order_partial",
    "order_cancelled",
    "position_closed",
    "shadow_result",
}

SIDES = {"LONG", "SHORT", "NONE"}


def _clean_metrics(metrics):
    if metrics is None:
        return {}

    if not isinstance(metrics, dict):
        raise ValueError("metrics tem de ser um dicionário")

    result = {}

    for key, value in metrics.items():
        if isinstance(value, bool):
            result[str(key)] = value
        elif isinstance(value, (int, float)) and math.isfinite(value):
            result[str(key)] = value

    return result


def build_event(
    *,
    stage,
    exchange,
    market,
    symbol,
    side="NONE",
    strategy=None,
    reason=None,
    scan_id=None,
    metrics=None,
):
    """Constrói um evento em memória, sem qualquer escrita em disco."""

    if stage not in STAGES:
        raise ValueError(f"Etapa desconhecida: {stage}")

    if side not in SIDES:
        raise ValueError(f"Direção inválida: {side}")

    if not exchange or not market or not symbol:
        raise ValueError("exchange, market e symbol são obrigatórios")

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scan_id": scan_id,
        "exchange": str(exchange),
        "market": str(market),
        "symbol": str(symbol),
        "side": side,
        "strategy": strategy,
        "stage": stage,
        "reason": reason,
        "metrics": _clean_metrics(metrics),
    }


def record_event(
    path,
    *,
    stage,
    exchange,
    market,
    symbol,
    side="NONE",
    strategy=None,
    reason=None,
    scan_id=None,
    metrics=None,
):
    """Regista um evento em JSONL."""

    event = build_event(
        stage=stage,
        exchange=exchange,
        market=market,
        symbol=symbol,
        side=side,
        strategy=strategy,
        reason=reason,
        scan_id=scan_id,
        metrics=metrics,
    )

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
        file.flush()

    return event
