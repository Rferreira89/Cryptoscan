"""Teste do servidor europeu: o que se consegue ler daqui que o GitHub
(EUA) nao consegue. Nunca imprime chaves nem saldos completos.
Uso: python3 -m tools.eu.teste <saida.json>"""
import json
import sys
import time
import urllib.request

TESTS = {
    "binance_futuros_funding": "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1",
    "binance_futuros_oi": "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=4h&limit=2",
    "bybit_derivados": "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
    "bybit_eu_publico": "https://api.bybit.eu/v5/market/tickers?category=spot&symbol=BTCUSDC",
    "yahoo_sp500_fut": "https://query1.finance.yahoo.com/v8/finance/chart/ES=F?interval=1h&range=120d",
    "yahoo_dxy": "https://query2.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1h&range=120d",
    "yahoo_vix": "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1h&range=5d",
    "stooq_spx": "https://stooq.com/q/d/l/?s=%5Espx&i=d",
    "fred_dolar": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS",
}


def probe(url):
    t = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cryptoscan"}), timeout=15) as r:
            body = r.read(400).decode(errors="replace")
            return {"ok": r.status == 200, "http": r.status, "ms": round((time.time() - t) * 1000), "amostra": body[:120]}
    except Exception as e:
        return {"ok": False, "erro": str(e)[:160]}


def main(out):
    res = {"t": int(time.time()), "testes": {k: probe(u) for k, u in TESTS.items()}}
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as r:
            res["ip"] = r.read().decode()
    except Exception:
        res["ip"] = None
    try:                                     # conta Bybit UE (so leitura)
        from engine import account
        snap = account.snapshot({})
        res["conta_bybit_eu"] = {"ok": bool(snap.get("ok")), "usdc_livre": snap.get("usdc_free"),
                                 "erro": snap.get("error")}
    except Exception as e:
        res["conta_bybit_eu"] = {"ok": False, "erro": str(e)[:160]}
    with open(out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
