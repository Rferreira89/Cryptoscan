"""Derivatives Engine (perpetuos da OKX).

Unica bolsa de derivados acessivel a partir do GitHub (Binance e Bybit
recusam). Os valores sao de UMA bolsa, nao do mercado inteiro, e isso fica
registado em "venue". Campo que falhe fica a None e entra em "missing".

Funding extremo NAO e sinal contrario: e um fator de risco.
"""
import threading
import time

from . import sources

BASE = "https://www.okx.com"
_lock = threading.Lock()
_last = {}
_GAP = {"rubik": 0.45, "public": 0.12}     # limites de pedidos da OKX


def _get(kind, path, params):
    with _lock:
        wait = _last.get(kind, 0) + _GAP[kind] - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[kind] = time.time()
    d = sources._get(BASE + path, params)
    if d.get("code") != "0":
        raise sources.SourceError(f"code {d.get('code')}: {d.get('msg')}")
    return d["data"]


def pctile(value, hist):
    hist = [h for h in hist if h is not None]
    if value is None or len(hist) < 20:
        return None
    return round(100 * sum(1 for h in hist if h <= value) / len(hist))


def quadrant(price_chg, oi_chg, eps=1.0):
    if price_chg is None or oi_chg is None:
        return None
    if abs(oi_chg) < eps or abs(price_chg) < eps / 2:
        return "FLAT"
    if price_chg > 0:
        return "LONG_BUILDUP" if oi_chg > 0 else "SHORT_COVERING"
    return "SHORT_BUILDUP" if oi_chg > 0 else "LONG_LIQUIDATION"


def market_snapshot():
    """3 pedidos para o mercado todo: tickers, OI e especificacoes."""
    f = sources._f
    tick = {x["instId"]: x for x in
            _get("public", "/api/v5/market/tickers", {"instType": "SWAP"})}
    oi = {x["instId"]: f(x.get("oiUsd")) for x in
          _get("public", "/api/v5/public/open-interest", {"instType": "SWAP"})}
    spec = {x["instId"]: f(x.get("ctVal")) for x in
            _get("public", "/api/v5/public/instruments", {"instType": "SWAP"})
            if x.get("state") == "live"}
    return {"tick": tick, "oi": oi, "ctval": spec}


def flags(d):
    out = []
    fp, lp = d.get("funding_pctile"), d.get("ls_pctile")
    apr = d.get("funding_apr")
    if fp is not None and apr is not None:
        if fp >= 95 and apr > 15:
            out.append("FUNDING_EXTREME_POSITIVE")
        elif fp <= 5 and apr < -5:
            out.append("FUNDING_EXTREME_NEGATIVE")
    if lp is not None and fp is not None:
        if lp >= 90 and fp >= 75:
            out.append("CROWDED_LONGS")
        elif lp <= 10 and fp <= 25:
            out.append("CROWDED_SHORTS")
    oc = d.get("oi_chg_24h_pct")
    if oc is not None:
        if oc >= 10:
            out.append("LEVERAGE_EXPANSION")
        elif oc <= -10:
            out.append("LEVERAGE_CONTRACTION")
    return out


def analyse(base, spot_price, snap, now):
    f = sources._f
    inst = f"{base}-USDT-SWAP"
    if inst not in snap["ctval"] or inst not in snap["tick"]:
        return None
    d = {"venue": "okx", "missing": [], "oi_usd": snap["oi"].get(inst)}
    last = f(snap["tick"][inst].get("last"))
    d["basis_pct"] = round((last / spot_price - 1) * 100, 3) \
        if last and spot_price else None

    def step(name, fn):
        try:
            fn()
        except (sources.SourceError, KeyError, IndexError, TypeError,
                ValueError):
            d["missing"].append(name)

    def funding():
        d.update(funding_rate=None, funding_apr=None, funding_pctile=None)
        cur = _get("public", "/api/v5/public/funding-rate", {"instId": inst})[0]
        rate = f(cur["fundingRate"])
        hours = (int(cur["nextFundingTime"]) - int(cur["fundingTime"])) / 3.6e6
        if not 0 < hours <= 24:
            hours = 8.0
        hist = _get("public", "/api/v5/public/funding-rate-history",
                    {"instId": inst, "limit": 100})
        d.update(funding_rate=rate, funding_interval_h=hours,
                 funding_apr=round(rate * 24 / hours * 365 * 100, 1),
                 funding_pctile=pctile(rate, [f(h["fundingRate"]) for h in hist]))

    def oi_hist():
        d.update(oi_chg_24h_pct=None, price_chg_24h_pct=None, positioning=None)
        h = _get("rubik", "/api/v5/rubik/stat/contracts/open-interest-history",
                 {"instId": inst, "period": "4H", "limit": 7})
        now_c, old_c = f(h[0][2]), f(h[6][2])        # em moeda, nao em USD
        d["oi_chg_24h_pct"] = round((now_c / old_c - 1) * 100, 2)
        t = snap["tick"][inst]
        d["price_chg_24h_pct"] = round(
            (f(t["last"]) / f(t["open24h"]) - 1) * 100, 2)
        d["positioning"] = quadrant(d["price_chg_24h_pct"], d["oi_chg_24h_pct"])

    def ls_ratio():
        d.update(ls_ratio=None, ls_pctile=None)
        h = _get("rubik",
                 "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract",
                 {"instId": inst, "period": "4H", "limit": 100})
        d["ls_ratio"] = round(f(h[0][1]), 2)
        d["ls_pctile"] = pctile(f(h[0][1]), [f(x[1]) for x in h])

    def liquidations():
        d["liquidations"] = None
        rows = _get("public", "/api/v5/public/liquidation-orders",
                    {"instType": "SWAP", "instFamily": f"{base}-USDT",
                     "state": "filled", "limit": 100})
        det = [x for r in rows for x in r.get("details", [])
               if int(x["ts"]) / 1000 >= now - 86400]
        ctv = snap["ctval"][inst]
        usd = lambda side: round(sum(
            f(x["sz"]) * ctv * f(x["bkPx"]) for x in det
            if x["posSide"] == side))
        oldest = min((int(x["ts"]) / 1000 for x in det), default=now)
        d["liquidations"] = {"long_usd": usd("long"), "short_usd": usd("short"),
                             "hours_covered": round((now - oldest) / 3600, 1),
                             "truncated": len(det) >= 100}

    step("funding", funding)
    step("open_interest_history", oi_hist)
    step("long_short_ratio", ls_ratio)
    step("liquidations", liquidations)
    d["flags"] = flags(d)
    return d
