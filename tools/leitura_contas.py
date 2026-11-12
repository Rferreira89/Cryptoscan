"""(11/11, autorizacao do Rui 11/11 23:40: consultas EXCLUSIVAMENTE de leitura no servidor europeu) Bybit UE e OKX.

So pedidos GET. Nunca abre, altera ou fecha ordens ou posicoes. Repositorio PUBLICO: o log so mostra dados de mercado
e regras da conta (comissoes, minimos, margem, juros, modo da conta), nunca saldos nem quantidades emprestaveis; os
saldos e o que depende deles vao so para o Telegram do Rui.
Uso (no servidor europeu): python3 -m tools.leitura_contas [saida_publica.json]"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CENARIOS = (0.5, 1, 2, 3, 4, 5)          # risco por operacao, % do capital


def _f(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


# ---------------- OKX (so GET) ----------------
def okx(pedido, base="https://eea.okx.com"):
    pub, priv, avisos = {}, {}, []
    cfgc = pedido(base, "/api/v5/account/config")
    c = (cfgc.get("data") or [{}])[0] if cfgc.get("code") == "0" else {}
    pub["conta"] = {k: c.get(k) for k in ("acctLv", "posMode", "autoLoan", "ctIsoMode", "mgnIsoMode", "perm", "level")}
    if cfgc.get("code") != "0":
        avisos.append(f"account/config: {cfgc.get('code')} {str(cfgc.get('msg'))[:60]}")
    fee = pedido(base, "/api/v5/account/trade-fee?instType=FUTURES")
    f0 = (fee.get("data") or [{}])[0] if fee.get("code") == "0" else {}
    pub["comissoes_futures"] = {"maker": _f(f0.get("maker")), "taker": _f(f0.get("taker")), "nivel": f0.get("level"),
                                "erro": None if fee.get("code") == "0" else f"{fee.get('code')} {str(fee.get('msg'))[:60]}"}
    conta = {x["instId"] for x in (pedido(base, "/api/v5/account/instruments?instType=FUTURES").get("data") or [])}
    inst = pedido(base, "/api/v5/public/instruments?instType=FUTURES").get("data") or []
    tk = {x["instId"]: _f(x.get("last")) for x in (pedido(base, "/api/v5/market/tickers?instType=FUTURES").get("data") or [])}
    xp = {}
    for i in inst:
        iid = i.get("instId", "")
        if "XPERP" not in iid or i.get("state") != "live":
            continue
        px = tk.get(iid)
        mn = (_f(i.get("minSz")) or 0) * (_f(i.get("ctVal")) or 0) * (px or 0)
        xp[iid] = {"base": iid.split("-")[0], "negociavel_conta": iid in conta, "ctVal": _f(i.get("ctVal")),
                   "minSz": _f(i.get("minSz")), "lotSz": _f(i.get("lotSz")), "lever_max": _f(i.get("lever")),
                   "preco": px, "nocional_minimo_usd": round(mn, 4) if px else None}
    pub["xperps"] = xp
    bal = pedido(base, "/api/v5/account/balance")
    if bal.get("code") == "0":
        b = (bal.get("data") or [{}])[0]
        priv["okx"] = {"totalEq": _f(b.get("totalEq")), "adjEq": _f(b.get("adjEq")), "imr": _f(b.get("imr")),
                       "mmr": _f(b.get("mmr")), "notionalUsd": _f(b.get("notionalUsd")),
                       "moedas": {d.get("ccy"): {"eq": _f(d.get("eq")), "availBal": _f(d.get("availBal")),
                                                 "availEq": _f(d.get("availEq"))} for d in b.get("details") or []}}
    else:
        avisos.append(f"account/balance: {bal.get('code')} {str(bal.get('msg'))[:60]}")
    pos = pedido(base, "/api/v5/account/positions")
    priv["okx_posicoes"] = len(pos.get("data") or []) if pos.get("code") == "0" else None
    pub["avisos"] = avisos
    return pub, priv


# ---------------- Bybit UE (so GET, chave so de leitura) ----------------
def bybit(acc):
    pub, priv, avisos = {}, {}, []
    info = acc.get("/v5/user/query-api")
    pub["chave_so_leitura"] = acc.read_only(info)
    if not pub["chave_so_leitura"]:
        return {"erro": "a chave da Bybit NAO e so de leitura: nada consultado"}, {}
    try:
        fr = acc.get("/v5/account/fee-rate", {"category": "spot"})
        lst = fr.get("list") or []
        usdc = [x for x in lst if str(x.get("symbol", "")).endswith("USDC")]
        mk = sorted({_f(x.get("makerFeeRate")) for x in usdc if x.get("makerFeeRate") is not None})
        tk_ = sorted({_f(x.get("takerFeeRate")) for x in usdc if x.get("takerFeeRate") is not None})
        pub["comissoes_spot"] = {"maker": mk, "taker": tk_, "pares": len(usdc)}
    except acc.AccountError as e:
        pub["comissoes_spot"] = {"erro": str(e)[:100]}
    try:
        md = acc.margem_detalhe()
        pub["margem"] = {b: {k: v for k, v in x.items() if k not in ("disponivel_para_emprestar", "max_emprestimo")}
                         for b, x in md["moedas"].items() if x.get("margem_spot")}
        pub["minimos_usdc"] = {b: {"min_ordem_valor": x.get("min_ordem_valor"), "min_ordem_qtd": x.get("min_ordem_qtd"),
                                   "estado": x.get("estado")} for b, x in md["moedas"].items()}
        priv["bybit_emprestavel"] = {b: x.get("disponivel_para_emprestar") for b, x in md["moedas"].items() if x.get("margem_spot")}
        avisos += md["limitacoes"]
    except acc.AccountError as e:
        avisos.append(f"margem: {str(e)[:100]}")
    try:
        stt = acc.get("/v5/spot-margin-trade/state")
        pub["margem_estado"] = {k: stt.get(k) for k in ("spotLeverage", "spotMarginMode", "effectiveLeverage")}
    except acc.AccountError as e:
        pub["margem_estado"] = {"erro": str(e)[:100]}
    try:
        w = acc.get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        priv["bybit"] = {"equity": acc.equity(w), "usdc_livre": acc.usdc_free(w), "dividas": acc.debts(w)}
        livre = acc.usdc_free(w) or 0
        pub["verificacoes"] = {"usdc_livre_cobre_ordem_minima_5": livre >= 5.0, "ha_dividas_de_margem": bool(acc.debts(w)),
                               "moedas_com_saldo": sorted(c for c, q in acc.coins(w).items() if q and c not in ("USDC",))}
        try:
            oo = acc.open_orders()
            pub["verificacoes"]["ordens_abertas"] = len(oo) if isinstance(oo, list) else None
        except Exception as e:                              # noqa: BLE001
            pub["verificacoes"]["ordens_abertas"] = f"erro {type(e).__name__}"
    except acc.AccountError as e:
        avisos.append(f"wallet: {str(e)[:100]}")
    pub["avisos"] = avisos
    return pub, priv


def regime_btc(velas_diarias):
    """Regime pela regra da producao (engine/arena.market_regime) com velas diarias [(t, o, h, l, c)] fechadas."""
    from engine import arena
    d = [{"t": int(t), "o": o, "h": h, "l": l, "c": c} for t, o, h, l, c in sorted(velas_diarias)]
    if len(d) < 200:
        return {"regime": None, "velas": len(d)}
    c = [x["c"] for x in d]
    s50, s200 = sum(c[-50:]) / 50, sum(c[-200:]) / 200
    return {"regime": arena.market_regime(btc1d=d), "velas": len(d), "ultimo_dia": d[-1]["t"], "fecho": c[-1],
            "sma50": round(s50, 2), "sma200": round(s200, 2), "ret30_pct": round((c[-1] / c[-31] - 1) * 100, 2)}


def velas_okx(pedido, base="https://eea.okx.com"):
    out = []
    for url in ("/api/v5/market/candles?instId=BTC-USDT&bar=1Dutc&limit=300",
                "/api/v5/market/history-candles?instId=BTC-USDT&bar=1Dutc&limit=100&after={}"):
        if "{}" in url:
            if not out:
                break
            url = url.format(min(x[0] for x in out) * 1000)
        d = pedido(base, url)
        for r in d.get("data") or []:
            if str(r[8] if len(r) > 8 else "1") == "1":                # so velas confirmadas (fechadas)
                out.append((int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return sorted(set(out))


def velas_bybit():
    import json as _j
    import urllib.request
    req = urllib.request.Request("https://api.bybit.eu/v5/market/kline?category=spot&symbol=BTCUSDC&interval=D&limit=400",
                                 headers={"User-Agent": "cryptoscan/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = _j.loads(r.read())
    rows = (d.get("result") or {}).get("list") or []
    import time as _t
    hoje = int(_t.time()) // 86400 * 86400
    return sorted((int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in rows
                  if int(x[0]) // 1000 < hoje)                           # tira o dia por fechar


def resumo_privado(priv, pub):
    """Texto para o Telegram: saldos e o capital minimo por cenario de risco (so para o Rui)."""
    linhas = ["🔎 Leitura das contas (só leitura, nada alterado)"]
    b = priv.get("bybit") or {}
    linhas.append(f"Bybit UE: valor {b.get('equity')} | USDC livre {b.get('usdc_livre')} | dívidas {b.get('dividas') or 'nenhuma'}")
    o = priv.get("okx") or {}
    usdt = (o.get("moedas") or {}).get("USDT") or {}
    linhas.append(f"OKX: valor {o.get('totalEq')} | USDT disponível {usdt.get('availBal')} | margem inicial usada {o.get('imr')} "
                  f"| posições abertas {priv.get('okx_posicoes')}")
    eq = o.get("totalEq")
    xs = [x for x in (pub.get("okx") or {}).get("xperps", {}).values() if x.get("negociavel_conta") and x.get("nocional_minimo_usd")]
    if eq and xs:
        for r in CENARIOS:
            # TF-SHORT: stop ~15% do preco; o contrato minimo cabe se min_nocional x 15% <= eq x r%
            ok = sum(1 for x in xs if x["nocional_minimo_usd"] * 0.15 <= eq * r / 100)
            linhas.append(f"  OKX risco {r}% com stop de 15%: {ok}/{len(xs)} X-Perps cabem no contrato mínimo")
    return "\n".join(linhas)


def main(saida=None):
    from tools import okx_verifica as OV
    from engine import account as ACC
    pub, priv = {}, {}
    try:
        pub["okx"], p = okx(OV.pedido)
        priv.update(p)
    except Exception as e:                                  # noqa: BLE001
        pub["okx"] = {"erro": type(e).__name__}
    if ACC.configured():
        try:
            pub["bybit"], p = bybit(ACC)
            priv.update(p)
        except Exception as e:                              # noqa: BLE001
            pub["bybit"] = {"erro": type(e).__name__}
    else:
        pub["bybit"] = {"erro": "sem chave"}
    reg = {}
    try:
        reg["okx_btc_usdt"] = regime_btc(velas_okx(OV.pedido))
    except Exception as e:                                  # noqa: BLE001
        reg["okx_btc_usdt"] = {"erro": type(e).__name__}
    try:
        reg["bybit_ue_btc_usdc"] = regime_btc(velas_bybit())
    except Exception as e:                                  # noqa: BLE001
        reg["bybit_ue_btc_usdc"] = {"erro": type(e).__name__}
    pub["regime"] = reg
    OV.telegram(resumo_privado(priv, pub))
    txt = json.dumps(pub, ensure_ascii=False, separators=(",", ":"))
    if saida:
        with open(saida, "w", encoding="utf-8") as f:
            f.write(txt)
    print("LEITURA_PUBLICA_INICIO")
    print(txt)
    print("LEITURA_PUBLICA_FIM")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
