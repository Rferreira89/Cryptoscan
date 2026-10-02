"""Data Layer: adaptadores de dados publicos (sem chaves de API).

Cada fonte devolve dados normalizados. Uma fonte que falha e reportada
como erro - nunca se inventam nem se preenchem valores.
"""
import json
import urllib.request
import urllib.parse

TIMEOUT = 15
UA = {"User-Agent": "cryptoscan-engine/1.0"}
QUOTE = "USDT"
TF_SECONDS = {"4h": 14400, "1d": 86400}


class SourceError(Exception):
    pass


def _get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # rede, HTTP, JSON
        raise SourceError(f"{type(e).__name__}: {e}") from e


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ticker(base, last, bid, ask, vol_quote, chg_pct):
    return {"base": base, "last": _f(last), "bid": _f(bid), "ask": _f(ask),
            "vol_quote": _f(vol_quote), "chg_pct": chg_pct}


def _candle(ts_ms, o, h, l, c, v, taker_buy=None):
    """tb = volume comprador agressor (negocios executados), se a fonte o der."""
    return {"t": int(ts_ms) // 1000, "o": _f(o), "h": _f(h), "l": _f(l),
            "c": _f(c), "v": _f(v),
            "tb": None if taker_buy is None else _f(taker_buy)}


class Bybit:
    name = "bybit"
    base_url = "https://api.bybit.com"
    _tf = {"4h": "240", "1d": "D"}

    def tickers(self):
        d = _get(self.base_url + "/v5/market/tickers", {"category": "spot"})
        if d.get("retCode") != 0:
            raise SourceError(f"retCode {d.get('retCode')}: {d.get('retMsg')}")
        out = {}
        for x in d["result"]["list"]:
            s = x["symbol"]
            if s.endswith(QUOTE):
                p = _f(x.get("price24hPcnt"))
                out[s[:-len(QUOTE)]] = _ticker(
                    s[:-len(QUOTE)], x.get("lastPrice"), x.get("bid1Price"),
                    x.get("ask1Price"), x.get("turnover24h"),
                    None if p is None else p * 100)
        return out

    def candles(self, base, tf, limit=500):
        d = _get(self.base_url + "/v5/market/kline",
                 {"category": "spot", "symbol": base + QUOTE,
                  "interval": self._tf[tf], "limit": min(limit, 1000)})
        if d.get("retCode") != 0:
            raise SourceError(f"retCode {d.get('retCode')}: {d.get('retMsg')}")
        return [_candle(r[0], r[1], r[2], r[3], r[4], r[5])
                for r in d["result"]["list"]]


class Binance:
    name = "binance"
    base_url = "https://data-api.binance.vision"

    def tickers(self):
        d = _get(self.base_url + "/api/v3/ticker/24hr")
        out = {}
        for x in d:
            s = x["symbol"]
            if s.endswith(QUOTE):
                out[s[:-len(QUOTE)]] = _ticker(
                    s[:-len(QUOTE)], x.get("lastPrice"), x.get("bidPrice"),
                    x.get("askPrice"), x.get("quoteVolume"),
                    _f(x.get("priceChangePercent")))
        return out

    def candles(self, base, tf, limit=500):
        d = _get(self.base_url + "/api/v3/klines",
                 {"symbol": base + QUOTE, "interval": tf,
                  "limit": min(limit, 1000)})
        return [_candle(r[0], r[1], r[2], r[3], r[4], r[5], r[9]) for r in d]

    def book(self, base):
        d = _get(self.base_url + "/api/v3/depth",
                 {"symbol": base + QUOTE, "limit": 500})
        conv = lambda rows: [(float(p), float(q)) for p, q in rows]
        return conv(d["bids"]), conv(d["asks"])


class OKX:
    name = "okx"
    base_url = "https://www.okx.com"
    _tf = {"4h": "4H", "1d": "1Dutc"}

    def tickers(self):
        d = _get(self.base_url + "/api/v5/market/tickers", {"instType": "SPOT"})
        if d.get("code") != "0":
            raise SourceError(f"code {d.get('code')}: {d.get('msg')}")
        out = {}
        for x in d["data"]:
            base, _, quote = x["instId"].partition("-")
            if quote == QUOTE:
                last, op = _f(x.get("last")), _f(x.get("open24h"))
                chg = (last / op - 1) * 100 if last and op else None
                out[base] = _ticker(base, last, x.get("bidPx"), x.get("askPx"),
                                    x.get("volCcy24h"), chg)
        return out

    def candles(self, base, tf, limit=300):
        d = _get(self.base_url + "/api/v5/market/candles",
                 {"instId": f"{base}-{QUOTE}", "bar": self._tf[tf],
                  "limit": min(limit, 300)})
        if d.get("code") != "0":
            raise SourceError(f"code {d.get('code')}: {d.get('msg')}")
        return [_candle(r[0], r[1], r[2], r[3], r[4], r[5]) for r in d["data"]]

    def book(self, base):
        d = _get(self.base_url + "/api/v5/market/books",
                 {"instId": f"{base}-{QUOTE}", "sz": 400})
        if d.get("code") != "0":
            raise SourceError(f"code {d.get('code')}: {d.get('msg')}")
        conv = lambda rows: [(float(r[0]), float(r[1])) for r in rows]
        return conv(d["data"][0]["bids"]), conv(d["data"][0]["asks"])


class KuCoin:
    name = "kucoin"
    base_url = "https://api.kucoin.com"
    _tf = {"4h": "4hour", "1d": "1day"}

    def tickers(self):
        d = _get(self.base_url + "/api/v1/market/allTickers")
        if d.get("code") != "200000":
            raise SourceError(f"code {d.get('code')}: {d.get('msg')}")
        out = {}
        for x in d["data"]["ticker"]:
            base, _, quote = x["symbol"].partition("-")
            if quote == QUOTE:
                p = _f(x.get("changeRate"))
                out[base] = _ticker(base, x.get("last"), x.get("buy"),
                                    x.get("sell"), x.get("volValue"),
                                    None if p is None else p * 100)
        return out

    def candles(self, base, tf, limit=500):
        d = _get(self.base_url + "/api/v1/market/candles",
                 {"symbol": f"{base}-{QUOTE}", "type": self._tf[tf]})
        if d.get("code") != "200000":
            raise SourceError(f"code {d.get('code')}: {d.get('msg')}")
        # [time(s), open, close, high, low, volume, turnover]
        return [_candle(int(r[0]) * 1000, r[1], r[3], r[4], r[2], r[5])
                for r in d["data"][:limit]]


# Ordem = prioridade para velas. Se a primeira falhar usa-se a seguinte e
# marca-se DATA SOURCE FALLBACK.
# A Bybit fica de fora: recusa (HTTP 403) ligacoes vindas dos servidores do
# GitHub. O adaptador mantem-se para quando o motor correr noutro servidor.
ALL = [Binance(), OKX(), KuCoin()]
