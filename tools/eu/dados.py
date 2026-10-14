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


# macroeconomia (Yahoo Finance, velas de 1 hora, 120 dias): futuros do
# S&P 500, indice do dolar, VIX (medo) e juro a 10 anos dos EUA
MACRO = {"SP": "ES=F", "DXY": "DX-Y.NYB", "VIX": "%5EVIX", "US10Y": "%5ETNX"}
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"


def macro():
    out, falhas = {}, []
    for k, sym in MACRO.items():
        try:
            import urllib.request
            req = urllib.request.Request(YAHOO + sym + "?interval=1h&range=120d",
                                         headers={"User-Agent": "Mozilla/5.0 cryptoscan"})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.loads(r.read().decode())["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            # (fecho da vela, preco); velas sem preco ficam de fora
            out[k] = [(int(t) + 3600, round(c, 4)) for t, c in zip(ts, cl) if c is not None]
        except Exception as e:
            falhas.append(f"macro {k}: {type(e).__name__}"[:60])
    return out, falhas


KEEP_HIST = 90 * DAY            # historico proprio de OI e long/short (a Binance so da 30 / 16 dias)


def merge_hist(new, old, now, keep=KEEP_HIST):
    """Junta series [(t, v)] do ficheiro anterior com as novas, sem repetir
    instantes, e guarda so os ultimos 'keep' segundos."""
    m = {int(t): v for t, v in (old or [])}
    m.update({int(t): v for t, v in (new or [])})
    return [[t, m[t]] for t in sorted(m) if t >= now - keep]


BOOK_KEEP = 60 * DAY


def book_imbalance(bids, asks, band=0.01):
    """(compras - vendas) / total em USD dentro de +-1% do preco medio."""
    try:
        bb, ba = float(bids[0][0]), float(asks[0][0])
    except (IndexError, ValueError, TypeError):
        return None
    mid = (bb + ba) / 2
    b = sum(float(p) * float(q) for p, q in bids if float(p) >= mid * (1 - band))
    a = sum(float(p) * float(q) for p, q in asks if float(p) <= mid * (1 + band))
    return round((b - a) / (b + a), 4) if b + a else None


def record_book(moedas, prev_path, dest_dir, now):
    """Grava o desequilibrio do livro de ordens (Binance Futures) de hora a
    hora em livro.json (60 dias), para o ringue o poder testar mais tarde."""
    try:
        prev = json.load(open(prev_path)) if prev_path and os.path.exists(prev_path) else {}
    except Exception:
        prev = {}
    hist = prev.get("moedas") or {}
    hour = (now // 3600) * 3600
    for b, c in moedas.items():
        try:
            d = _get("/fapi/v1/depth", {"symbol": c["s"], "limit": 100})
            v = book_imbalance(d.get("bids") or [], d.get("asks") or [])
        except Exception:
            v = None
        if v is None:
            continue
        old = {int(t): x for t, x in hist.get(b) or []}
        old[hour] = v                               # um valor por hora (o ultimo)
        hist[b] = [[t, old[t]] for t in sorted(old) if t >= now - BOOK_KEEP]
        time.sleep(0.05)
    with open(os.path.join(dest_dir, "livro.json"), "w") as f:
        json.dump({"t": now, "fonte": "binance-futures depth ±1%", "moedas": hist}, f, separators=(",", ":"))
    return len(hist)


def main(dest, state_path=None, prev_path=None, book_prev=None):
    now = int(time.time())
    res = {"t": now, "fonte": "binance-futures", "moedas": {}, "falhas": []}
    try:
        res["moedas"], res["falhas"] = collect(now)
    except Exception as e:
        res["falhas"].append(f"binance: {type(e).__name__}: {str(e)[:80]}")
    # historico acumulado: OI (4H) e rácio long/short alem do que a Binance guarda,
    # para os lutadores que dependem deles (Dalia, Leandro) terem combates longos
    try:
        prev = json.load(open(prev_path)) if prev_path and os.path.exists(prev_path) else {}
    except Exception:
        prev = {}
    for b, c in res["moedas"].items():
        pc = (prev.get("moedas") or {}).get(b) or {}
        for k in ("oi", "ls"):
            if c.get(k) or pc.get(k):
                c[k] = merge_hist(c.get(k), pc.get(k), now)
    try:                                     # liquidacoes da escuta (se existir)
        from tools.eu import liquidacoes
        # so as moedas acompanhadas (o canal traz centenas): ficheiro leve
        res["liq"] = {b: v for b, v in liquidacoes.resumo().items() if b in res["moedas"]}
        res["liq_escuta"] = bool(liquidacoes.vivo())
        try:
            import glob
            lg = os.path.join(liquidacoes.DIR, "escuta.log")
            res["liq_diag"] = {"ficheiros": [os.path.basename(f) + f":{os.path.getsize(f)}"
                                             for f in glob.glob(os.path.join(liquidacoes.DIR, "2*.jsonl"))],
                               "log": open(lg).read()[-300:] if os.path.exists(lg) else ""}
        except Exception:
            pass
    except Exception as e:
        res["liq"], res["liq_escuta"] = {}, False
        res["falhas"].append(f"liquidações: {type(e).__name__}")
    try:                                     # livro de ordens (historico proprio)
        res["livro_moedas"] = record_book(res["moedas"], book_prev, os.path.dirname(dest) or ".", now)
    except Exception as e:
        res["falhas"].append(f"livro: {type(e).__name__}")
    res["macro"], fm = macro()
    res["falhas"] += fm
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
    main(*sys.argv[1:5])
