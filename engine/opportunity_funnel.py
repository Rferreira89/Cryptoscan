
"""Opportunity Funnel: registo auditável de oportunidades.

Cria eventos em memória ou regista-os em JSONL.
Não gera sinais nem envia ordens.

O registo em disco é passivo: falhas de I/O não devem
interromper o scanner ou o processo de trading.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

logger = logging.getLogger(__name__)

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


def _required_text(value, field):
    """Valida texto obrigatório."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} tem de ser texto não vazio")
    return value.strip()


def _optional_text(value, field):
    """Valida texto opcional."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field} tem de ser texto ou None")

    return value.strip() or None


def _clean_metrics(metrics):
    """Mantém apenas métricas JSON seguras e numéricas."""

    if metrics is None:
        return {}

    if not isinstance(metrics, dict):
        raise ValueError("metrics tem de ser um dicionário")

    result = {}

    for key, value in metrics.items():
        if not isinstance(key, str) or not key.strip():
            continue

        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, int):
            result[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            result[key] = value

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
    """Constrói um evento em memória, sem escrita em disco."""

    if not isinstance(stage, str) or stage not in STAGES:
        raise ValueError(f"Etapa desconhecida: {stage!r}")

    if not isinstance(side, str) or side not in SIDES:
        raise ValueError(f"Direção inválida: {side!r}")

    exchange = _required_text(exchange, "exchange")
    market = _required_text(market, "market")
    symbol = _required_text(symbol, "symbol")

    strategy = _optional_text(strategy, "strategy")
    reason = _optional_text(reason, "reason")
    scan_id = _optional_text(scan_id, "scan_id")

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scan_id": scan_id,
        "exchange": exchange,
        "market": market,
        "symbol": symbol,
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
    """Regista um evento JSONL sem propagar falhas de I/O.

    Devolve o evento quando a gravação é concluída.
    Devolve None quando ocorre uma falha de escrita.

    Erros de validação dos dados continuam a ser explícitos.
    """

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

    try:
        if path is None:
            raise ValueError("path não pode ser None")

        destination = Path(path)
        payload = json.dumps(
            event,
            ensure_ascii=False,
            allow_nan=False,
        )

        destination.parent.mkdir(parents=True, exist_ok=True)

        with destination.open("a", encoding="utf-8") as file:
            file.write(payload + "\n")
            file.flush()

        return event

    except (OSError, TypeError, ValueError):
        logger.exception(
            "Opportunity Funnel: falha ao registar evento "
            "(exchange=%s, market=%s, symbol=%s, stage=%s)",
            event["exchange"],
            event["market"],
            event["symbol"],
            event["stage"],
        )
        return None
