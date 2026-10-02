import urllib.request
URLS = {
 "bybit_eu_time": "https://api.bybit.eu/v5/market/time",
 "bybit_eu_tickers": "https://api.bybit.eu/v5/market/tickers?category=spot",
 "bybit_eu_instr": "https://api.bybit.eu/v5/market/instruments-info?category=spot&limit=1000",
 "bybit_eu_linear": "https://api.bybit.eu/v5/market/instruments-info?category=linear&limit=5",
 "bybit_eu_kline": "https://api.bybit.eu/v5/market/kline?category=spot&symbol=BTCUSDC&interval=240&limit=2",
 "bybit_eu_fee": "https://api.bybit.eu/v5/market/orderbook?category=spot&symbol=BTCUSDC&limit=5",
 "bybit_nl": "https://api.bybit.nl/v5/market/time",
}
import json
for name, url in URLS.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cryptoscan-probe"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode(errors="replace")
        print(f"{name}: OK len={len(body)} {body[:700]}")
        if name in ("bybit_eu_instr",):
            d = json.loads(body)["result"]["list"]
            import collections
            print("N", len(d), collections.Counter(x["quoteCoin"] for x in d), collections.Counter(x["status"] for x in d))
            print("USDC bases:", sorted(x["baseCoin"] for x in d if x["quoteCoin"]=="USDC"))
            print("EUR bases:", sorted(x["baseCoin"] for x in d if x["quoteCoin"]=="EUR"))
            print("USDT bases:", sorted(x["baseCoin"] for x in d if x["quoteCoin"]=="USDT")[:400])
            print("sample", [x for x in d if x["symbol"] in ("LINKUSDC","BTCUSDC","LINKEUR")])
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__} {str(e)[:120]}")
    print()
