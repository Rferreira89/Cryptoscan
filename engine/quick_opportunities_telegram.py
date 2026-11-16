"""Quick Opportunities -> Telegram bridge.

Consumes already-fetched, closed 30m USDC candles. It deliberately does not
import an exchange executor, submit orders, change account settings or infer
that a candidate has a statistical edge.
"""
from __future__ import annotations

import hashlib

from . import alerts
from . import quick_opportunities as engine

ALERT_PREFIX = "⚠️ QUICK OPPORTUNITY — CANDIDATO NÃO VALIDADO"
VALID_SIDES = {"LONG", "SHORT"}


def _signal_id(candidate: dict) -> str:
    raw = "|".join(str(candidate.get(k, "")) for k in
                   ("asset", "family", "side", "signal_t"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def format_candidate(candidate: dict) -> str:
    side = candidate.get("side")
    if side not in VALID_SIDES:
        raise ValueError("lado inválido")
    asset = str(candidate.get("asset") or "UNKNOWN")
    family = str(candidate.get("family") or "unknown")
    regime = str(candidate.get("regime") or "unknown")
    close = float(candidate["signal_close"])
    stop = float(candidate["stop"])
    target = float(candidate["target"])
    signal_t = int(candidate["signal_t"])
    return (
        f"{ALERT_PREFIX}\n"
        f"Ativo: {asset} | {side} | Estratégia: {family}\n"
        f"Regime: {regime} | Fecho do sinal: {close:.10g}\n"
        f"Stop indicativo: {stop:.10g} | Alvo indicativo: {target:.10g}\n"
        f"Horizonte máximo: {int(candidate.get('max_hold_bars', 8)) * 30} min "
        f"| score exploratório: {candidate.get('score', '-')}"
        f"\nMotivo: {candidate.get('reason', '-')}"
        f"\nID: {_signal_id(candidate)}"
        "\nSem ordem enviada. Spot USDC é apenas fonte de preço; SHORT "
        "não é executável em spot. Edge estatístico ainda não aprovado."
    )


def notify_candidates(candidates, sender=None):
    """Send one deduplicable Telegram alert per distinct candle/family/side.

    sender is injectable for deterministic tests. The production default is
    the existing alert engine, preserving TELEGRAM_BOT_TOKEN/CHAT_ID handling.
    """
    send = sender or alerts.send
    sent = []
    for candidate in candidates:
        if candidate.get("side") not in VALID_SIDES:
            continue
        message = format_candidate(candidate)
        result = send(message)
        if result:
            sent.append({"id": _signal_id(candidate), "message_id": result})
    return sent


def scan_candles(candles_by_asset, sender=None):
    """Detect candidates from validated, closed 30m candles and notify Telegram.

    candles_by_asset: {asset: chronological list[OHLCV dict]}. The caller must
    fetch only USDC-quoted markets and remove the currently-forming candle.
    """
    candidates = []
    for asset, candles in sorted(candles_by_asset.items()):
        if len(candles) < engine.MIN_BARS:
            continue
        found = engine.detect_opportunities(candles, asset)
        candidates.extend(found)
    sent = notify_candidates(candidates, sender=sender)
    return {"assets_scanned": len(candles_by_asset),
            "candidates": candidates, "telegram_sent": sent}


def validate_usdc_ohlcv(candles, now):
    """Validate 30m OHLCV and discard the forming candle using core validator."""
    clean, report = engine.prepare_30m_candles(candles, now)
    if report.get("status") != "VALID":
        return [], report
    return clean, report
