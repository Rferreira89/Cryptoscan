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


def _i(x, padrao=None):
    try:
        return int(x)
    except (TypeError, ValueError):
        return padrao


def _f(x, padrao=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return padrao


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
def okx_lideres(paginas=5, ordens=("overview", "win_ratio", "pnl_ratio")):
    """(17/11) Varias ordenacoes publicas da OKX para descobrir candidatos diferentes (nao so os de maior PnL)."""
    out, vistos = [], set()
    for ordem in ordens:
        for pg in range(1, paginas + 1):
            d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-lead-traders", {"instType": "SWAP", "sortType": ordem,
                                                                            "page": pg, "limit": 20})
            if not d:
                break
            for r in d[0].get("ranks") or []:
                if r.get("uniqueCode") and r["uniqueCode"] not in vistos:
                    vistos.add(r["uniqueCode"])
                    out.append(r)
            time.sleep(0.4)
    return [{"fonte": "okx", "id": r["uniqueCode"], "nome": r.get("nickName"), "dias": int(r.get("leadDays") or 0),
             "win_ratio": float(r.get("winRatio") or 0), "copiadores": int(r.get("copyTraderNum") or 0)} for r in out
            if r.get("uniqueCode")]


def okx_historico(uc):
    d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-subpositions-history", {"instType": "SWAP", "uniqueCode": uc, "limit": 100})
    return [{"inst": x["instId"], "base": x["instId"].split("-")[0], "lado": "LONG" if x.get("posSide") == "long" else "SHORT",
             "t_abre": _i(x.get("openTime"), 0) // 1000, "t_fecha": _i(x.get("closeTime"), 0) // 1000, "px_abre": _f(x.get("openAvgPx")),
             "px_fecha": _f(x.get("closeAvgPx")), "alav": _f(x.get("lever"), 1.0) or 1.0, "margem": _f(x.get("margin")),
             "pnl_ratio": _f(x.get("pnlRatio")), "id": x.get("subPosId")} for x in d or []
            if x.get("instId") and _i(x.get("closeTime")) and _i(x.get("openTime")) and _f(x.get("openAvgPx"))] \
        if d is not None else None


def okx_posicoes(uc):
    d = okx(OKX_GLOBAL, "/api/v5/copytrading/public-current-subpositions", {"instType": "SWAP", "uniqueCode": uc, "limit": 100})
    if d is None:
        return None
    return [{"inst": x["instId"], "base": x["instId"].split("-")[0], "lado": "LONG" if x.get("posSide") == "long" else "SHORT",
             "t_abre": (_i(x.get("openTime")) or 0) // 1000 or None, "px_abre": _f(x.get("openAvgPx")), "alav": _f(x.get("lever"), 1.0) or 1.0,
             "tamanho": _f(x.get("subPos")), "margem": _f(x.get("margin")), "id": x.get("subPosId"),
             "upl_nocional": _f(x.get("uplRatio")) / max(1.0, _f(x.get("lever"), 1.0))} for x in d
            if x.get("instId") and x.get("subPosId") and _f(x.get("openAvgPx"))]


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
            if conta_min <= conta <= conta_max and out and out[-1]["id"] == r["ethAddress"]:
                out[-1]["rotacao_mes"] = float(mes.get("vlm") or 0) / conta     # volume / conta: atividade frequente
        except (TypeError, ValueError):
            continue
    # metade pelo ROI do mes, metade pela atividade (traders frequentes de curto prazo), sem repetir
    por_roi = sorted(out, key=lambda x: -x["roi_mes"])[: n // 2]
    ids = {x["id"] for x in por_roi}
    por_ativ = [x for x in sorted(out, key=lambda x: -x.get("rotacao_mes", 0)) if x["id"] not in ids][: n - len(por_roi)]
    return por_roi + por_ativ


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
                ops.append({"inst": coin, "base": _base_hl(coin)[0], "lado": lado, "t_abre": a["t"], "t_fecha": t,
                            "px_abre": a["custo"] / max(a["max_sz"], 1e-12), "px_fecha": px,
                            "retorno_nocional": (a["pnl"] - a["fee"]) / nocional, "entradas": a["entradas"], "alav": None})
                abertas[k] = {"sz": 0.0, "custo": 0.0, "t": t, "pnl": 0.0, "fee": 0.0, "entradas": 0, "max_sz": 0.0}
    return ops


def _base_hl(coin):
    """Hyperliquid cota alguns ativos em lotes de 1000 (kPEPE, kBONK...): base PEPE e preco por unidade = preco/1000."""
    if len(coin) > 1 and coin[0] == "k" and coin[1:].isupper():
        return coin[1:], 0.001
    return coin, 1.0


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
        pv = float(q.get("positionValue") or 0)
        base, fator = _base_hl(q["coin"])
        out.append({"upl_nocional": float(q.get("unrealizedPnl") or 0) / pv if pv else 0.0, "fator_px": fator, "margem": pv,
                    "inst": q["coin"], "base": base, "lado": "LONG" if szi > 0 else "SHORT", "px_abre": float(q.get("entryPx") or 0),
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


BYBIT_CACHE = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/piloto-okx/bybit_eu_spot.json"
BYBIT_CACHE_MAX_S = 48 * 3600


def bybit_eu_spot(info=None):
    """Bases com par spot na Bybit EU (USDT/USDC). A API publica oficial (api.bybit.eu) recusa os servidores do GitHub
    (403); a lista e lida pelo runner europeu do piloto e guardada com a hora da leitura (bybit_eu_spot.json no ramo
    piloto-okx). Usa a direta se responder; senao a guardada, so se tiver menos de 48 h. None se nenhuma servir."""
    info = info if info is not None else {}
    d = _http("https://api.bybit.eu/v5/market/instruments-info?category=spot&limit=1000", tent=1)
    lst = (((d or {}).get("result") or {}).get("list")) if isinstance(d, dict) else None
    if isinstance(lst, list) and lst:
        info.update(origem="direta", idade_s=0)
        return {x.get("baseCoin") for x in lst if x.get("status") == "Trading" and x.get("quoteCoin") in ("USDT", "USDC")}
    if FALHAS and "api.bybit.eu" in FALHAS[-1]["onde"]:
        FALHAS.pop()                                         # 403 esperado daqui: nao conta como falha
    c = _http(BYBIT_CACHE, tent=2)
    if isinstance(c, dict) and c.get("bases") and time.time() - int(c.get("t") or 0) <= BYBIT_CACHE_MAX_S:
        info.update(origem="guardada (runner europeu)", idade_s=int(time.time() - int(c["t"])))
        return set(c["bases"])
    info.update(origem="indisponivel", idade_s=None)
    return None
