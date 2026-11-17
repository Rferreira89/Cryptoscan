"""Quick Opportunities -> Telegram bridge.

Formats and sends research-only candidates built from validated, closed 30m
candles. The live scanner currently supplies OKX USD_UM X-Perps. This module
never imports an executor, submits orders, changes account settings or infers
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
    if candidate.get("venue") == "OKX" and candidate.get("market_type") == "USD_UM_XPERP":
        class_labels = {
            "crypto": "Cripto",
            "equity": "Ações/ETF",
            "precious_metal": "Metais preciosos",
        }
        asset_class = class_labels.get(candidate.get("asset_class"), "Classe por confirmar")
        market_line = (
            f"Mercado: OKX USD_UM X-Perp | Classe: {asset_class}"
            f" | Contrato: {candidate.get('instrument_id', '-')}"
            "\nLiquidação do contrato/conta: confirmar separadamente (USD/USDC/USDG)"
        )
        safety_line = (
            "\nSem ordem enviada. Dados dos próprios futuros OKX; edge estatístico "
            "ainda não aprovado e execução desativada."
        )
    else:
        market_line = "Mercado: spot USDC (referência de preço)"
        safety_line = (
            "\nSem ordem enviada. SHORT não é executável em spot. "
            "Edge estatístico ainda não aprovado."
        )
    return (
        f"{ALERT_PREFIX}\n"
        f"Ativo: {asset} | {side} | Estratégia: {family}\n"
        f"{market_line}\n"
        f"Regime: {regime} | Fecho do sinal: {close:.10g}\n"
        f"Stop indicativo: {stop:.10g} | Alvo indicativo: {target:.10g}\n"
        f"Horizonte máximo: {int(candidate.get('max_hold_bars', 8)) * 30} min "
        f"| score exploratório: {candidate.get('score', '-')}"
        f"\nMotivo: {candidate.get('reason', '-')}"
        f"\nID: {_signal_id(candidate)}"
        f"{safety_line}"
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


DIGEST_MAX = 10


def _linha(candidate: dict) -> str:
    classe = {"crypto": "cripto", "equity": "ações/ETF", "precious_metal": "metal"}.get(
        candidate.get("asset_class"), "")
    return (f"• {candidate.get('asset')} {candidate.get('side')} {candidate.get('family')}"
            f"{' (' + classe + ')' if classe else ''} | fecho {float(candidate['signal_close']):.6g}"
            f" | stop {float(candidate['stop']):.6g} | alvo {float(candidate['target']):.6g}"
            f" | {candidate.get('instrument_id', '')}")


def notify_digest(candidates, sender=None, max_items=DIGEST_MAX):
    """(17/11) Uma mensagem por ciclo com os candidatos novos (antes: uma por candidato). Com os 262 X-Perps
    reais a funcionar, a primeira sonda deu 14 candidatos numa vela de 30 min: ~600 mensagens por dia de
    candidatos NAO validados. Ordena por score; os que ficam de fora da lista contam como vistos (mesma vela)."""
    send = sender or alerts.send
    validos = [c for c in candidates if c.get("side") in VALID_SIDES]
    if not validos:
        return []
    validos.sort(key=lambda c: (-float(c.get("score") or 0), str(c.get("asset"))))
    corpo = "\n".join(_linha(c) for c in validos[:max_items])
    resto = len(validos) - max_items
    message = (f"{ALERT_PREFIX}\n{len(validos)} candidato(s) na última vela de 30 min (OKX X-Perps):\n{corpo}"
               + (f"\n… e mais {resto}" if resto > 0 else "")
               + "\nHorizonte máximo 4 h. Sem ordem enviada; edge estatístico ainda não aprovado e execução desativada.")
    result = send(message)
    if not result:
        return []
    return [{"id": _signal_id(c), "message_id": result} for c in validos]


def scan_candles(candles_by_asset, sender=None):
    """Detect candidates from validated, closed 30m candles and notify Telegram.

    candles_by_asset: {asset: chronological list[OHLCV dict]}. The caller must
    identify the source instrument and remove the currently-forming candle.
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



def scan_universe(rows, sources, now, sender=None, max_workers=8):
    """Fetch and validate closed 30m USDC candles for executable scanner assets.

    Only assets already admitted by the main scanner are considered. Each asset
    is fetched from its own USDC ticker sources; invalid/stale data triggers a
    source fallback. No USDT symbol translation or order placement occurs.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(row):
        asset = row["asset"]
        allowed = set(row.get("sources") or [])
        errors = []
        for src in sources:
            if src.name not in allowed:
                continue
            try:
                raw = src.candles(asset, "30m", limit=100)
                clean, report = validate_usdc_ohlcv(raw, now)
                if report.get("status") == "VALID" and len(clean) >= engine.MIN_BARS:
                    return asset, clean, src.name, report, errors
                errors.append(f"{src.name}: {report.get('status')} ({report.get('n', 0)} velas)")
            except Exception as exc:
                errors.append(f"{src.name}: {type(exc).__name__}")
        return asset, [], None, {"status": "DATA INVALID", "n": 0}, errors

    ordered = sorted(rows, key=lambda row: row.get("volume_24h", 0), reverse=True)
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        fetched = list(pool.map(one, ordered))
    candles_by_asset = {asset: candles for asset, candles, _, _, _ in fetched if candles}
    source_by_asset = {asset: src for asset, candles, src, _, _ in fetched if candles}
    scan = scan_candles(candles_by_asset, sender=sender)
    scan.update({
        "assets_requested": len(ordered),
        "assets_with_valid_data": len(candles_by_asset),
        "source_by_asset": source_by_asset,
        "data_errors": {asset: errors for asset, candles, _, _, errors in fetched if errors},
        "telegram_configured": alerts.configured() if sender is None else None,
    })
    return scan


def validate_usdc_ohlcv(candles, now):
    """Validate 30m OHLCV and discard the forming candle using core validator."""
    clean, report = engine.prepare_30m_candles(candles, now)
    if report.get("status") != "VALID":
        return [], report
    return clean, report
