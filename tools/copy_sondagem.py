"""(17/11, ordem do Rui: CopyTrading multicorretora) Sondagem SO DE LEITURA do que as APIs permitem de facto.

Uso: python3 tools/copy_sondagem.py publico   (runner do GitHub: OKX publico, Hyperliquid)
     python3 tools/copy_sondagem.py eu        (runner europeu: OKX EEA publico + conta OKX copy, Bybit EU)
Nunca envia ordens nem altera nada. Saida sem valores monetarios nem credenciais (o log e publico)."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _http(url, corpo=None, timeout=20):
    try:
        req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"User-Agent": "cryptoscan/1.0", "Content-Type": "application/json"},
                                     method="POST" if corpo is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, type(e).__name__


def _campos(x):
    return sorted(x.keys()) if isinstance(x, dict) else None


def okx_publico(base):
    out = {"base": base}
    s, d = _http(f"{base}/api/v5/copytrading/public-lead-traders?instType=SWAP&sortType=overview&limit=20")
    out["lead_traders"] = {"http": s, "code": (d or {}).get("code") if isinstance(d, dict) else d}
    ranks = []
    if isinstance(d, dict) and d.get("code") == "0" and d.get("data"):
        ranks = d["data"][0].get("ranks") or []
        out["lead_traders"].update(n=len(ranks), total_paginas=d["data"][0].get("totalPage"), campos=_campos(ranks[0]) if ranks else None)
    if ranks:
        uc = ranks[0].get("uniqueCode")
        for nome, path in (("posicoes_atuais", f"public-current-subpositions?instType=SWAP&uniqueCode={uc}"),
                           ("historico", f"public-subpositions-history?instType=SWAP&uniqueCode={uc}&limit=50"),
                           ("estatisticas", f"public-stats?instType=SWAP&uniqueCode={uc}&lastDays=2"),
                           ("pnl_diario", f"public-pnl?instType=SWAP&uniqueCode={uc}&lastDays=2")):
            s, r = _http(f"{base}/api/v5/copytrading/{path}")
            dd = (r or {}).get("data") if isinstance(r, dict) else None
            out[nome] = {"http": s, "code": (r or {}).get("code") if isinstance(r, dict) else r,
                         "n": len(dd) if isinstance(dd, list) else None,
                         "campos": _campos(dd[0]) if isinstance(dd, list) and dd and isinstance(dd[0], dict) else None}
    return out


def hyperliquid():
    out = {}
    s, d = _http("https://api.hyperliquid.xyz/info", {"type": "meta"})
    out["meta"] = {"http": s, "n_ativos": len((d or {}).get("universe") or []) if isinstance(d, dict) else d}
    s, d = _http("https://stats-data.hyperliquid.xyz/Mainnet/leaderboard", timeout=40)
    rows = (d or {}).get("leaderboardRows") if isinstance(d, dict) else None
    out["leaderboard"] = {"http": s, "n": len(rows) if rows else None, "campos": _campos(rows[0]) if rows else None}
    if rows:
        addr = rows[0].get("ethAddress")
        s, c = _http("https://api.hyperliquid.xyz/info", {"type": "clearinghouseState", "user": addr})
        out["posicoes_carteira"] = {"http": s, "campos": _campos(c), "n_posicoes": len((c or {}).get("assetPositions") or [])
                                    if isinstance(c, dict) else None}
        s, f = _http("https://api.hyperliquid.xyz/info", {"type": "userFills", "user": addr})
        out["execucoes_carteira"] = {"http": s, "n": len(f) if isinstance(f, list) else None,
                                     "campos": _campos(f[0]) if isinstance(f, list) and f else None}
    return out


def okx_conta():
    import okx_exec as E
    if not all(E._chaves()):
        return {"chaves": False}
    out = {"chaves": True}
    for nome, path in (("copy_config", "/api/v5/copytrading/config"),
                       ("copy_posicoes_seguidas", "/api/v5/copytrading/current-subpositions?instType=SWAP")):
        r = E.privado("GET", path)
        out[nome] = {"code": r.get("code"), "msg": str(r.get("msg") or "")[:120]}
    return out


def bybit_eu():
    from engine import account as AC
    out = {"base": AC.BASE}
    for cat in ("spot", "linear", "inverse", "option"):
        s, d = _http(f"{AC.BASE}/v5/market/instruments-info?category={cat}&limit=1000")
        lst = (((d or {}).get("result") or {}).get("list")) if isinstance(d, dict) else None
        out[f"instrumentos_{cat}"] = {"http": s, "retCode": (d or {}).get("retCode") if isinstance(d, dict) else d,
                                      "n": len(lst) if isinstance(lst, list) else None}
    if not AC.configured():
        out["conta"] = "sem chave de leitura"
        return out
    for nome, path, params in (("chave", "/v5/user/query-api", None), ("conta", "/v5/account/info", None),
                               ("saldo_unificado", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}),
                               ("posicoes_linear", "/v5/position/list", {"category": "linear", "settleCoin": "USDT"})):
        try:
            res, info = AC.get(path, params), {"ok": True}
        except Exception as e:
            res, info = {}, {"ok": False, "erro": str(e)[:140]}
        if nome == "chave" and isinstance(res, dict) and res:
            info.update(readOnly=res.get("readOnly"), permissoes=res.get("permissions"), ips_restritos=bool(res.get("ips")))
        if nome == "conta" and isinstance(res, dict) and res:
            info.update(modo_margem=res.get("marginMode"), unificada=res.get("unifiedMarginStatus"))
        if nome == "saldo_unificado" and isinstance(res, dict) and res:
            lst = res.get("list") or [{}]
            info["tem_saldo"] = bool(float((lst[0] or {}).get("totalEquity") or 0) > 0)
        out[nome] = info
    return out


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "publico"
    if modo == "lideres":
        out = {}
        for base in ("https://www.okx.com",):
            for st in ("overview", "pnl", "aum", "win_ratio", "pnl_ratio", "current_copy_trader_pnl"):
                vistos, paginas = set(), None
                for pg in range(1, 40):
                    s_, d = _http(f"{base}/api/v5/copytrading/public-lead-traders?instType=SWAP&sortType={st}&page={pg}&limit=20")
                    if not isinstance(d, dict) or d.get("code") != "0" or not d.get("data"):
                        out[st] = {"erro_pagina": pg, "code": (d or {}).get("code") if isinstance(d, dict) else s_, "msg": str((d or {}).get("msg"))[:80] if isinstance(d, dict) else None}
                        break
                    paginas = d["data"][0].get("totalPage")
                    for r_ in d["data"][0].get("ranks") or []:
                        vistos.add(r_.get("uniqueCode"))
                    if paginas and pg >= int(paginas):
                        break
                out[st] = {**out.get(st, {}), "total_paginas": paginas, "traders": len(vistos)}
        print(json.dumps(out, indent=1))
        sys.exit(0)
    if modo == "publico":
        r = {"okx_www": okx_publico("https://www.okx.com"), "okx_eea": okx_publico("https://eea.okx.com"), "hyperliquid": hyperliquid()}
    else:
        r = {"okx_eea": okx_publico("https://eea.okx.com"), "okx_conta": okx_conta(), "bybit_eu": bybit_eu()}
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
