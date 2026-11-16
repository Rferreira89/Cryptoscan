"""Read-only derivatives market data for the account's OKX Europe USDC X-Perps.

No private endpoints, credentials, account setting changes or order placement.
X-Perps use the USD_UM instrument family; settlement currency is selected at
account level. Live execution must verify GET /api/v5/account/config reports
settleCcy=USDC before it can submit any order.
"""
import time

from .sources import _get, _candle, SourceError

OKX = "https://www.okx.com"
BAR_MS = 30 * 60 * 1000
PAGE = {"okx": 300}


def _require_range(start_ms, end_ms):
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("intervalo temporal invalido")
    if start_ms % BAR_MS or end_ms % BAR_MS:
        raise ValueError("datas devem estar alinhadas a velas de 30m")


def validate_okx_account_config(config):
    """Fail closed unless the authenticated OKX account is configured for USDC settlement."""
    if not isinstance(config, dict):
        return False, "configuração da conta OKX indisponível"
    if config.get("code") != "0":
        return False, "não foi possível consultar a configuração da conta OKX"
    rows = config.get("data") or []
    if not rows:
        return False, "a OKX não devolveu a configuração da conta"
    settle = str(rows[0].get("settleCcy") or "").upper()
    if settle != "USDC":
        return False, f"liquidação USD-M da conta é {settle or 'desconhecida'}, não USDC"
    return True, "USDC confirmado"


def okx_usdc_xperps(request=_get):
    """Discover live linear OKX USD_UM X-Perps; settlement is account-selected (USDC required)."""
    response = request(OKX + "/api/v5/public/instruments", {"instType": "FUTURES"})
    if not isinstance(response, dict) or response.get("code") != "0":
        raise SourceError(f"OKX FUTURES instruments: resposta inválida {response}")
    out = {}
    for item in response.get("data", []):
        inst_id = item.get("instId", "")
        family = item.get("instFamily", "")
        rule_type = str(item.get("ruleType") or "").lower()
        if (item.get("state") != "live" or not inst_id.endswith("_UM_XPERP")
                or not family.endswith("_UM") or item.get("ctType") != "linear"
                or rule_type == "pre_market"):
            continue
        base = inst_id.split("-")[0]
        try:
            info = {
                "venue": "okx", "market_type": "usd_margined_xperp",
                "inst_id": inst_id, "inst_family": family, "base": base,
                "quote": "USD", "settlement_currency_required": "USDC",
                "settle_currency_metadata": item.get("settleCcy"),
                "contract_value": float(item["ctVal"]),
                "contract_value_currency": item.get("ctValCcy"),
                "contract_multiplier": float(item.get("ctMult") or 1),
                "min_size": float(item["minSz"]), "lot_size": float(item["lotSz"]),
                "tick_size": float(item["tickSz"]),
                "contract_type": item.get("ctType"), "expiry": item.get("expTime"),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"OKX X-Perp com metadados inválidos: {inst_id}") from exc
        if (info["contract_value"] <= 0 or info["min_size"] <= 0
                or info["lot_size"] <= 0 or info["tick_size"] <= 0):
            raise SourceError(f"OKX X-Perp com especificação não positiva: {inst_id}")
        prior = out.get(base)
        if prior is None or str(info.get("expiry") or "") > str(prior.get("expiry") or ""):
            out[base] = info
    return out


def list_account_market(venue, request=_get):
    if venue == "okx":
        return okx_usdc_xperps(request)
    raise ValueError("venue deve ser okx (X-Perps USDC)")


def _okx_candle(row):
    if len(row) < 9:
        raise SourceError("OKX candle sem campo confirm")
    return _candle(row[0], row[1], row[2], row[3], row[4], row[5])


def fetch_okx_xperp_candles(inst_id, start_ms, end_ms, request=_get,
                            pause_seconds=0.12):
    """Fetch confirmed 30m candles for an OKX X-Perp instrument over [start_ms,end_ms)."""
    _require_range(start_ms, end_ms)
    rows, cursor = [], end_ms
    while cursor > start_ms:
        response = request(OKX + "/api/v5/market/history-candles", {
            "instId": inst_id, "bar": "30m", "after": cursor, "limit": PAGE["okx"],
        })
        if not isinstance(response, dict) or response.get("code") != "0":
            raise SourceError(f"OKX X-Perp history-candles: resposta inválida {response}")
        batch = response.get("data") or []
        if not batch:
            break
        for item in batch:
            ts = int(item[0])
            if start_ms <= ts < end_ms and len(item) >= 9 and str(item[8]) == "1":
                rows.append(_okx_candle(item))
        oldest = min(int(item[0]) for item in batch)
        if oldest >= cursor:
            raise SourceError("paginação OKX X-Perp sem progresso")
        cursor = oldest
        if oldest <= start_ms or len(batch) < PAGE["okx"]:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    by_ts = {row["t"]: row for row in rows}
    return [by_ts[t] for t in sorted(by_ts)]


def fetch_okx_xperp_funding_history(inst_id, start_ms, end_ms, request=_get,
                                    pause_seconds=0.12):
    """Fetch realized X-Perp funding. OKX history endpoint is limited to 3 months."""
    if end_ms <= start_ms:
        raise ValueError("intervalo temporal inválido")
    if end_ms - start_ms > 90 * 24 * 60 * 60 * 1000:
        raise ValueError("histórico de funding OKX limitado a 3 meses; reduz o intervalo")
    rows, cursor = [], end_ms
    while cursor > start_ms:
        response = request(OKX + "/api/v5/public/funding-rate-history", {
            "instId": inst_id, "after": cursor, "limit": 100,
        })
        if not isinstance(response, dict) or response.get("code") != "0":
            raise SourceError(f"OKX X-Perp funding history: resposta inválida {response}")
        batch = response.get("data") or []
        if not batch:
            break
        for item in batch:
            ts = int(item["fundingTime"])
            if start_ms <= ts < end_ms:
                rate = item.get("realizedRate")
                if rate in (None, ""):
                    rate = item.get("fundingRate")
                if rate in (None, ""):
                    raise SourceError(f"funding sem taxa realizada em {inst_id} às {ts}")
                rows.append((ts // 1000, float(rate)))
        oldest = min(int(item["fundingTime"]) for item in batch)
        if oldest >= cursor:
            raise SourceError("paginação OKX X-Perp funding sem progresso")
        cursor = oldest
        if oldest <= start_ms or len(batch) < 100:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return sorted(set(rows))
