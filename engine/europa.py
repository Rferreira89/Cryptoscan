"""Dados do servidor europeu (runner "eu" na Hetzner).

Os servidores do GitHub nos EUA nao chegam a Binance Futures nem a conta
Bybit UE. O servidor europeu recolhe esses dados de 15 em 15 minutos
(tools/eu/dados.py) e publica-os em dados.json no ramo "europa". Este
modulo le esse ficheiro e aplica-o:

  - derivados: funding, open interest e long/short da Binance (a maior
    bolsa de perpetuos) passam a substituir os da OKX quando existem e sao
    recentes; as liquidacoes continuam a vir da OKX;
  - conta: saldo total e livre lidos com a chave SO DE LEITURA.

Se o servidor europeu falhar ou os dados forem velhos, tudo volta ao que
havia antes (OKX e capital enviado pelo Telegram). Nunca para o scanner.
"""
import json
import os
import time

from . import derivatives

MAX_AGE_LIVE = 45 * 60          # derivados e conta no scan ao vivo
MAX_AGE_RING = 3 * 3600         # combate da arena (de hora a hora)
H4 = 4 * 3600


def load(max_age=MAX_AGE_LIVE, now=None, path=None):
    """dados.json recente ou None. path: ficheiro local (testes, arena)."""
    now = now or time.time()
    d = None
    try:
        if path:
            with open(path) as f:
                d = json.load(f)
        else:
            repo = os.environ.get("GITHUB_REPOSITORY")
            if not repo:
                return None
            import urllib.request
            url = f"https://raw.githubusercontent.com/{repo}/europa/dados.json"
            with urllib.request.urlopen(url, timeout=15) as r:
                d = json.loads(r.read().decode())
    except Exception:
        return None
    if not isinstance(d, dict) or now - (d.get("t") or 0) > max_age:
        return None
    return d


def base_of(symbol):
    """BTCUSDT -> BTC; 1000PEPEUSDT -> PEPE; 1000000MOGUSDT -> MOG."""
    b = symbol[:-4] if symbol.endswith("USDT") else symbol
    for p in ("1000000", "10000", "1000"):
        if b.startswith(p) and b[len(p):].isalpha():
            return b[len(p):]
    return b


def coin(eu, base):
    return ((eu or {}).get("moedas") or {}).get(base)


def overlay(d, c, now):
    """Aplica os dados da Binance (c) a um resultado de derivados da OKX
    (d, pode ser None). Devolve o novo dicionario ou d se c for vazio."""
    if not c:
        return d
    d = dict(d) if d else {"venue": "okx", "missing": ["liquidations"],
                           "liquidations": None, "oi_usd": None,
                           "basis_pct": None}
    used = False
    fr = c.get("funding") or []                     # [(t_s, taxa)]
    if fr and c.get("funding_now") is not None:
        rate = c["funding_now"]
        hours = c.get("funding_h") or 8.0
        d.update(funding_rate=rate, funding_interval_h=hours,
                 funding_apr=round(rate * 24 / hours * 365 * 100, 1),
                 funding_pctile=derivatives.pctile(
                     rate, [x[1] for x in fr[-100:]]))
        used = True
    oi = c.get("oi") or []                          # [(t_s, oi em moeda)]
    if len(oi) >= 7 and oi[-7][1] and now - oi[-1][0] <= 2 * H4:
        d["oi_chg_24h_pct"] = round((oi[-1][1] / oi[-7][1] - 1) * 100, 2)
        if c.get("oi_usd"):
            d["oi_usd"] = round(c["oi_usd"])
        if c.get("chg_24h_pct") is not None:
            d["price_chg_24h_pct"] = c["chg_24h_pct"]
        d["positioning"] = derivatives.quadrant(d.get("price_chg_24h_pct"),
                                                d["oi_chg_24h_pct"])
        used = True
    ls = c.get("ls") or []                          # [(t_s, racio)]
    if len(ls) >= 20:
        d["ls_ratio"] = round(ls[-1][1], 2)
        d["ls_pctile"] = derivatives.pctile(ls[-1][1], [x[1] for x in ls])
        used = True
    if not used:
        return d
    d["missing"] = [m for m in d.get("missing") or []
                    if m not in ("funding", "open_interest_history",
                                 "long_short_ratio")]
    d["venue"] = "binance"
    d["liq_venue"] = "okx"
    d["flags"] = derivatives.flags(d)
    return d


def account(eu):
    """Resumo da conta (so leitura) se o servidor europeu a leu bem."""
    c = (eu or {}).get("conta") or {}
    return c if c.get("ok") else None


def capital_from(acc):
    """Valor total da conta em USD, dentro dos mesmos limites do /capital."""
    v = (acc or {}).get("equity")
    try:
        v = round(float(v), 2)
    except (TypeError, ValueError):
        return None
    # (27/10) o Rui levantou tudo a 25/10 e o capital ficou parado nos 120,55 porque so
    # aceitava 5 ou mais: agora segue sempre a conta (abaixo de 5 USDC nao ha ordens possiveis)
    return v if 0 < v <= 1_000_000 else None
