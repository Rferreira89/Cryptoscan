"""Corretora de execucao: Bybit UE (spot, pares em USDC).

A API da Bybit recusa ligacoes a partir do GitHub, por isso a lista de
pares, o preco, o volume e o spread da Bybit UE vem da API publica da
CoinGecko. Nao da passo de preco nem quantidade minima: esses confirmam-se
no ecra de ordem da Bybit.
"""
from . import sources

URL = "https://api.coingecko.com/api/v3/exchanges/bybit-eu/tickers"


def fetch(quote="USDC", max_pages=4):
    out = {}
    for page in range(1, max_pages + 1):
        d = sources._get(URL, {"page": page, "order": "volume_desc"})
        rows = d.get("tickers", [])
        for t in rows:
            if t.get("target") != quote:
                continue
            base = t["base"]
            out[base] = {
                "pair": f"{base}/{quote}",
                "last": sources._f(t.get("last")),
                "volume_usd": sources._f(
                    (t.get("converted_volume") or {}).get("usd")),
                "spread_pct": sources._f(t.get("bid_ask_spread_percentage")),
                "stale": bool(t.get("is_stale") or t.get("is_anomaly")),
                "url": t.get("trade_url")}
        if len(rows) < 100:
            break
    if not out:
        raise sources.SourceError("lista da Bybit UE vazia")
    return out


def check(v, global_price, cfg):
    """Devolve (ok, motivos) para executar neste par."""
    if v is None:
        return False, ["não listado na Bybit UE"]
    why = []
    if v["stale"] or not v["last"]:
        why.append("preço da Bybit UE desatualizado")
    if v["spread_pct"] is None or v["spread_pct"] > cfg["max_venue_spread_pct"]:
        why.append("spread elevado na Bybit UE")
    if (v["volume_usd"] or 0) < cfg["min_venue_volume_usd"]:
        why.append("volume baixo na Bybit UE")
    if v["last"] and global_price and \
            abs(v["last"] / global_price - 1) > 0.01:
        why.append("preço da Bybit UE diverge do mercado")
    return not why, why
