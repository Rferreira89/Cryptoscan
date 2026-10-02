"""Sonda de disponibilidade de dados (Fase 3). Nao faz parte do motor."""
import urllib.request

URLS = {
 "binance_fut_premium": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
 "binance_fut_oi_hist": "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=4h&limit=3",
 "binance_spot_klines": "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=2",
 "binance_spot_depth": "https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=5",
 "okx_funding": "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP",
 "okx_funding_hist": "https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=3",
 "okx_oi_all": "https://www.okx.com/api/v5/public/open-interest?instType=SWAP",
 "okx_swap_tickers": "https://www.okx.com/api/v5/market/tickers?instType=SWAP",
 "okx_rubik_oi_vol": "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy=BTC&period=1D",
 "okx_rubik_oi_hist": "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?instId=BTC-USDT-SWAP&period=4H&limit=3",
 "okx_rubik_ls": "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1D",
 "okx_rubik_ls_contract": "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract?instId=SUI-USDT-SWAP&period=4H&limit=3",
 "okx_rubik_taker": "https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy=BTC&instType=SPOT&period=1D",
 "okx_liquidations": "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&instFamily=BTC-USDT&state=filled&limit=3",
 "okx_swap_candles": "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=4H&limit=2",
 "okx_books": "https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=5",
 "kucoin_fut_contracts": "https://api-futures.kucoin.com/api/v1/contracts/active",
 "bybit_tickers_linear": "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
 "bybit_alt_host": "https://api.bytick.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
}
for name, url in URLS.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cryptoscan-probe"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode(errors="replace")
        print(f"{name}: OK len={len(body)} {body[:420]}")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__} {str(e)[:120]}")
    print()
