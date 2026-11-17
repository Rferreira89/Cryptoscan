"""(17/11) COPY_INTELLIGENCE - fontes de traders, confirmadas pela sondagem (tools/copy_sondagem.py, run 44109006310):
  OKX (www.okx.com, publico, sem chaves): lideres, posicoes atuais, historico de posicoes fechadas. No dominio EEA e
      na conta EEA o copy trading nao existe (404): na OKX a copia e feita com ordens PROPRIAS no piloto.
  Hyperliquid (api.hyperliquid.xyz, publico, on-chain): ranking de carteiras, posicoes e execucoes de cada carteira.
  Bybit EU: so spot (129 pares, 0 derivados) e sem API de copy trading -> nao e fonte de traders.
  Binance: sem API oficial de lideres de copy trading (so paginas web internas): nao usada (nao contornar restricoes).
Mercado para execucao: OKX EEA (X-Perps), dados publicos de velas e instrumentos."""
import json
import time
import urllib.parse
import urllib.request

OKX_GLOBAL = "https://www.okx.com"
OKX_EEA = "https://eea.okx.com"
HL = "https://api.hyperliquid.xyz/info"
HL_RANKING = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
UA = {"User-Agent": "cryptoscan-copy/1.0", "Content-Type": "application/json"}


class Falhas(list):
    def add(self, onde, erro):
        self.append({"onde": str(onde)[:80], "erro": str(erro)[:140], "t": int(time.time())})


FALHAS = Falhas()


def _http(url, corpo=None, timeout=25, tent=3):
    erro = None
    for k in range(tent):
        try:
            req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None, headers=UA,
                                         method="POST" if corpo is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"
            time.sleep(1.0 + k)
    FALHAS.add(url.split("?")[0], erro)
    return None


def okx(base, path, params=None):
    d = _http(base + path + ("?" + urllib.parse.urlencode(params) if params else ""))
    if isinstance(d, dict) and d.get("code") == "0":
        return d.get("data") or []
    if isinstance(d, dict) and d.get("code") in ("50011", "50061"):      # limite: espera e tenta uma vez
        time.sleep(2.5)
        d = _http(base + path + ("?" + urllib.parse.urlencode(params) if params else ""))
        if isinstance(d, dict) and d.get("code") == "0":
            return d.get("data") or []
    if d is not None:
        FALHAS.add(path, (d or {}).get("code") if isinstance(d, dict) else d)
    return None


# ------------------------------------------------------------------ OKX -------------------------------------------
def okx_lideres(paginas=5):
    out = []
    for pg in range(1, paginas + 1):
        d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-lead-traders", {"instType": "SWAP", "sortType": "overview",
                                                                        "page": pg, "limit": 20})
        if not d:
            break
        out += d[0].get("ranks") or []
        time.sleep(0.4)
    return [{"fonte": "okx", "id": r["uniqueCode"], "nome": r.get("nickName"), "dias": int(r.get("leadDays") or 0),
             "win_ratio": float(r.get("winRatio") or 0), "copiadores": int(r.get("copyTraderNum") or 0)} for r in out
            if r.get("uniqueCode")]


def okx_historico(uc):
    d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-subpositions-history", {"instType": "SWAP", "uniqueCode": uc, "limit": 100})
    return [{"inst": x["instId"], "base": x["instId"].split("-")[0], "lado": "LONG" if x.get("posSide") == "long" else "SHORT",
             "t_abre": int(x["openTime"]) // 1000, "t_fecha": int(x["closeTime"]) // 1000, "px_abre": float(x["openAvgPx"]),
             "px_fecha": float(x["closeAvgPx"]), "alav": float(x.get("lever") or 1), "margem": float(x.get("margin") or 0),
             "pnl_ratio": float(x.get("pnlRatio") or 0), "id": x.get("subPosId")} for x in d or [] if x.get("closeTime")] \
        if d is not None else None


def okx_posicoes(uc):
    d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-current-subpositions", {"instType": "SWAP", "uniqueCode": uc, "limit": 100})
    if d is None:
        return None
    return [{"inst": x["instId"], "base": x["instId"].split("-")[0], "lado": "LONG" if x.get("posSide") == "long" else "SHORT",
             "t_abre": int(x["openTime"]) // 1000, "px_abre": float(x["openAvgPx"]), "alav": float(x.get("lever") or 1),
             "tamanho": float(x.get("subPos") or 0), "margem": float(x.get("margin") or 0), "id": x["subPosId"]} for x in d]


# ------------------------------------------------------------------ Hyperliquid -----------------------------------
def hl_ranking(n=60, conta_min=20000, conta_max=20_000_000):
    """Carteiras com resultado positivo no mes e na semana, conta dentro de limites (nem micro nem baleias impossiveis de
    seguir); ordenadas pelo ROI do mes. O resto da avaliacao e feita nas execucoes (ranking.py)."""
    d = _http(HL_RANKING, timeout=60)
    rows = (d or {}).get("leaderboardRows") if isinstance(d, dict) else None
    if not rows:
        return None
    out = []
    for r in rows:
        w = {k: v for k, v in r.get("windowPerformances") or []}
        try:
            conta = float(r.get("accountValue") or 0)
            mes, sem = w.get("month") or {}, w.get("week") or {}
            if conta_min <= conta <= conta_max and float(mes.get("pnl") or 0) > 0 and float(sem.get("pnl") or 0) > 0:
                out.append({"fonte": "hyperliquid", "id": r["ethAddress"], "nome": r.get("displayName") or r["ethAddress"][:10],
                            "roi_mes": float(mes.get("roi") or 0), "volume_mes": float(mes.get("vlm") or 0)})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: -x["roi_mes"])
    return out[:n]


def hl_historico(addr):
    """Operacoes fechadas reconstruidas das execucoes (Open/Close por moeda e lado)."""
    f = _http(HL, {"type": "userFills", "user": addr})
    if not isinstance(f, list):
        return None
    ops, abertas = [], {}
    for x in sorted(f, key=lambda x: x["time"]):
        coin, dirc = x["coin"], str(x.get("dir") or "")
        if coin.startswith("@") or "Long" not in dirc and "Short" not in dirc:
            continue                                          # spot ou movimentos sem posicao
        lado = "LONG" if "Long" in dirc else "SHORT"
        sz, px, t = float(x["sz"]), float(x["px"]), int(x["time"]) // 1000
        k = (coin, lado)
        a = abertas.setdefault(k, {"sz": 0.0, "custo": 0.0, "t": t, "pnl": 0.0, "fee": 0.0, "entradas": 0, "max_sz": 0.0})
        a["fee"] += float(x.get("fee") or 0)
        if dirc.startswith("Open"):
            if a["sz"] == 0:
                a.update(t=t, custo=0.0, pnl=0.0, entradas=0, max_sz=0.0)
            a["sz"] += sz
            a["custo"] += sz * px
            a["entradas"] += 1
            a["max_sz"] = max(a["max_sz"], a["sz"])
        elif dirc.startswith("Close") and a["sz"] > 0:
            a["pnl"] += float(x.get("closedPnl") or 0)
            a["sz"] = max(0.0, a["sz"] - sz)
            if a["sz"] <= 1e-12:
                nocional = a["custo"] or 1e-9
                ops.append({"inst": coin, "base": coin, "lado": lado, "t_abre": a["t"], "t_fecha": t,
                            "px_abre": a["custo"] / max(a["max_sz"], 1e-12), "px_fecha": px,
                            "retorno_nocional": (a["pnl"] - a["fee"]) / nocional, "entradas": a["entradas"], "alav": None})
                abertas[k] = {"sz": 0.0, "custo": 0.0, "t": t, "pnl": 0.0, "fee": 0.0, "entradas": 0, "max_sz": 0.0}
    return ops


def hl_posicoes(addr):
    c = _http(HL, {"type": "clearinghouseState", "user": addr})
    if not isinstance(c, dict):
        return None
    out = []
    for p in c.get("assetPositions") or []:
        q = p.get("position") or {}
        szi = float(q.get("szi") or 0)
        if not szi:
            continue
        lev = (q.get("leverage") or {}).get("value")
        out.append({"inst": q["coin"], "base": q["coin"], "lado": "LONG" if szi > 0 else "SHORT", "px_abre": float(q.get("entryPx") or 0),
                    "alav": float(lev or 1), "tamanho": abs(szi), "id": f"{q['coin']}|{'L' if szi > 0 else 'S'}", "t_abre": None})
    return out


# ------------------------------------------------------------------ mercado de execucao (OKX EEA) ------------------
def xperps_eea():
    """base -> instId dos X-Perps vivos na OKX EEA (onde o piloto executa)."""
    d = okx(OKX_EEA, "/api/v5/public/instruments", {"instType": "FUTURES"}) or []
    out = {}
    for i in d:
        iid = i.get("instId", "")
        head, _, tail = iid.rpartition("-")
        if head.endswith("_UM_XPERP") and tail.isdigit() and i.get("state") == "live":
            out[iid.split("-")[0]] = iid
    return out


def velas_1h(inst, n=60):
    d = okx(OKX_EEA, "/api/v5/market/candles", {"instId": inst, "bar": "1H", "limit": n})
    if not d:
        return None
    v = [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]), "ok": str(x[8]) == "1"}
         for x in d if len(x) > 8]
    return sorted([b for b in v if b["ok"]], key=lambda b: b["t"])


def preco(inst):
    d = okx(OKX_EEA, "/api/v5/market/ticker", {"instId": inst})
    try:
        return float(d[0]["last"]) if d else None
    except (KeyError, ValueError, TypeError):
        return None


def bybit_eu_spot():
    """Bases com par spot na Bybit EU (USDT/USDC), da API publica oficial da Bybit EU (api.bybit.eu). None se falhar."""
    d = _http("https://api.bybit.eu/v5/market/instruments-info?category=spot&limit=1000")
    lst = (((d or {}).get("result") or {}).get("list")) if isinstance(d, dict) else None
    if not isinstance(lst, list):
        return None
    return {x.get("baseCoin") for x in lst if x.get("status") == "Trading" and x.get("quoteCoin") in ("USDT", "USDC")}
