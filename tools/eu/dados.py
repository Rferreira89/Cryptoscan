"""Recolha no servidor europeu (corre de 15 em 15 minutos no runner "eu").

Binance Futures (perpetuos USDT, as moedas com mais volume):
  - funding atual e historico (90+ dias, para percentis e para a arena);
  - open interest de 4 em 4 horas (30 dias: o maximo que a Binance da);
  - racio long/short das contas (4H, 100 periodos).
Conta Bybit UE (chave SO DE LEITURA): saldo total e USDC livre.

Escreve dados.json; o workflow publica-o no ramo "europa".
Uso: python3 -m tools.eu.dados <saida.json> [state.json]
"""
import json
import os
import sys
import time

from engine import europa, sources

FAPI = "https://fapi.binance.com"
TOP_N = 120                     # perpetuos com mais volume em 24h
MIN_VOL = 5e6
DAY = 86400


def _get(path, params=None):
    return sources._get(FAPI + path, params)


def universe():
    """[(simbolo, base, volume, variacao24h)] dos perpetuos USDT ativos."""
    info = _get("/fapi/v1/exchangeInfo")
    ok = {s["symbol"] for s in info.get("symbols", [])
          if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
          and s.get("status") == "TRADING"}
    rows = []
    for t in _get("/fapi/v1/ticker/24hr"):
        if t["symbol"] in ok and float(t.get("quoteVolume") or 0) >= MIN_VOL:
            rows.append((t["symbol"], europa.base_of(t["symbol"]),
                         float(t["quoteVolume"]), float(t.get("priceChangePercent") or 0)))
    rows.sort(key=lambda r: -r[2])
    seen, out = set(), []
    for r in rows:                  # um simbolo por moeda (o de mais volume)
        if r[1] not in seen:
            seen.add(r[1])
            out.append(r)
    return out[:TOP_N]


def collect(now):
    prem = {x["symbol"]: x for x in _get("/fapi/v1/premiumIndex")}
    hours = {}
    try:                            # intervalo de funding (4h, 1h) quando nao e 8h
        for x in _get("/fapi/v1/fundingInfo"):
            hours[x["symbol"]] = float(x.get("fundingIntervalHours") or 8)
    except sources.SourceError:
        pass
    out, falhas = {}, []
    for sym, base, vol, chg in universe():
        c = {"s": sym, "vol": round(vol), "chg_24h_pct": round(chg, 2)}
        p = prem.get(sym) or {}
        c["funding_now"] = sources._f(p.get("lastFundingRate"))
        c["funding_h"] = hours.get(sym, 8.0)
        try:
            fr = _get("/fapi/v1/fundingRate", {"symbol": sym, "limit": 1000})
            c["funding"] = [(int(x["fundingTime"]) // 1000, round(float(x["fundingRate"]), 8))
                            for x in fr if x.get("fundingRate") not in (None, "")]
        except sources.SourceError as e:
            falhas.append(f"{base} funding: {str(e)[:40]}")
        try:
            oi = _get("/futures/data/openInterestHist",
                      {"symbol": sym, "period": "4h", "limit": 180})
            c["oi"] = [(int(x["timestamp"]) // 1000 + 4 * 3600,   # fecho do periodo
                        round(float(x["sumOpenInterest"]), 4)) for x in oi]
            if oi:
                c["oi_usd"] = round(float(oi[-1]["sumOpenInterestValue"]))
        except sources.SourceError as e:
            falhas.append(f"{base} OI: {str(e)[:40]}")
        try:
            ls = _get("/futures/data/globalLongShortAccountRatio",
                      {"symbol": sym, "period": "4h", "limit": 100})
            c["ls"] = [(int(x["timestamp"]) // 1000, round(float(x["longShortRatio"]), 4))
                       for x in ls]
        except sources.SourceError as e:
            falhas.append(f"{base} L/S: {str(e)[:40]}")
        out[base] = c
        time.sleep(0.2)
    return out, falhas


def main(dest, state_path=None):
    now = int(time.time())
    res = {"t": now, "fonte": "binance-futures", "moedas": {}, "falhas": []}
    try:
        res["moedas"], res["falhas"] = collect(now)
    except Exception as e:
        res["falhas"].append(f"binance: {type(e).__name__}: {str(e)[:80]}")
    try:
        from engine import account
        state = {}
        if state_path and os.path.exists(state_path):
            with open(state_path) as f:
                state = json.load(f)
        res["conta"] = account.snapshot(state, now)
    except Exception as e:
        res["conta"] = {"ok": False, "error": f"{type(e).__name__}"[:80], "t": now}
    res["t"] = int(time.time())
    with open(dest, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    c = res["conta"]
    print(f"moedas={len(res['moedas'])} falhas={len(res['falhas'])} "
          f"conta={'ok' if c.get('ok') else c.get('error')}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
