import urllib.request, json
for ex in ("bybit_eu", "bybit-eu", "bybiteu"):
    for page in (1, 2):
        url = f"https://api.coingecko.com/api/v3/exchanges/{ex}/tickers?page={page}&order=volume_desc"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cryptoscan-probe", "accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode())
            t = d["tickers"]
            print(ex, page, "OK", len(t))
            if page == 1: print(json.dumps(t[0])[:900])
            print(" ".join(f"{x['base']}/{x['target']}" for x in t))
        except Exception as e:
            print(ex, page, "FAIL", type(e).__name__, str(e)[:100]); break
