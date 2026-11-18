"""(18/11, ordem de trabalho) Verificacao SO DE LEITURA, diretamente nas corretoras:
  OKX (conta EEA do piloto e do executor antigo, eea.okx.com via okx_exec.privado): posicoes, ordens condicionais
     pendentes de TODOS os tipos e ordens normais pendentes por instrumento, com a origem (pil = piloto, cs = antigo).
  Bybit EU (api.bybit.eu, engine/account.py, chave so de leitura): conta, saldos com divida (short em margem spot),
     ordens abertas e ordens condicionais spot do ativo.
Nenhuma ordem e enviada ou cancelada. No log (publico) so precos, estados, lados e coberturas; quantidades vao so
por Telegram (privado). Uso: python3 tools/verificar_contas.py RENDER SPCX XLM"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import okx_exec as E  # noqa: E402

PRIV = []


def origem(cl):
    cl = str(cl or "")
    return "piloto (pil)" if cl.startswith("pil") else "executor antigo (cs)" if cl.startswith("cs") else ("sem identificador" if not cl else "outro")


def okx(bases):
    out = {"base_api": "https://eea.okx.com (conta EEA)"}
    insts = E.privado("GET", "/api/v5/account/instruments?instType=FUTURES")
    ids = [x["instId"] for x in insts.get("data") or []] if insts.get("code") == "0" else []
    pos = E.privado("GET", "/api/v5/account/positions?instType=FUTURES")
    out["leitura_posicoes"] = pos.get("code") == "0"
    todas = [p for p in pos.get("data") or [] if float(p.get("pos") or 0)]
    out["posicoes_abertas_na_conta"] = [{"inst": p["instId"], "lado": "LONG" if float(p["pos"]) > 0 else "SHORT", "preco_medio": p.get("avgPx"),
                                          "alav": p.get("lever"), "margem": p.get("mgnMode")} for p in todas]
    for p in todas:
        PRIV.append(f"OKX posicao {p['instId']}: {float(p['pos']):+g} contratos, preco medio {p.get('avgPx')}")
    for b in bases:
        for inst in [i for i in ids if i.split("-")[0] == b]:
            r = {"inst": inst}
            ps = [p for p in todas if p["instId"] == inst]
            q = float(ps[0]["pos"]) if ps else 0.0
            r["posicao"] = None if not ps else {"lado": "LONG" if q > 0 else "SHORT", "preco_medio": ps[0].get("avgPx")}
            algos = []
            for t in ("conditional", "oco", "trigger", "move_order_stop", "twap", "iceberg"):
                a = E.privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType={t}")
                if a.get("code") != "0":
                    algos.append({"tipo": t, "erro": a.get("code")})
                    continue
                for x in a.get("data") or []:
                    algos.append({"algoId": x.get("algoId"), "tipo": t, "lado": x.get("side"), "estado": x.get("state"),
                                  "stop": x.get("slTriggerPx") or None, "objetivo": x.get("tpTriggerPx") or None,
                                  "trigger": x.get("triggerPx") or None, "reduce_only": x.get("reduceOnly"),
                                  "fecha_posicao": x.get("closeFraction") == "1", "origem": origem(x.get("algoClOrdId")),
                                  "algoClOrdId": x.get("algoClOrdId") or None})
                    PRIV.append(f"OKX ordem condicional {inst} {x.get('algoId')} ({t}, {x.get('side')}): sz {x.get('sz')}")
            pend = E.privado("GET", f"/api/v5/trade/orders-pending?instId={inst}")
            ords = [{"ordId": x.get("ordId"), "lado": x.get("side"), "tipo": x.get("ordType"), "preco": x.get("px"),
                     "estado": x.get("state"), "reduce_only": x.get("reduceOnly"), "origem": origem(x.get("clOrdId"))}
                    for x in (pend.get("data") or [])] if pend.get("code") == "0" else [{"erro": pend.get("code")}]
            fecho = None if not ps else ("buy" if q < 0 else "sell")
            cob = 0.0
            for x in algos:
                if x.get("stop") and x.get("lado") == fecho:
                    if x.get("fecha_posicao"):
                        cob = abs(q)
            for a in (E.privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional").get("data") or []) + \
                     (E.privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco").get("data") or []):
                if a.get("slTriggerPx") and a.get("side") == fecho and a.get("closeFraction") != "1":
                    cob += float(a.get("sz") or 0)
            r.update(ordens_condicionais=algos, ordens_normais_pendentes=ords,
                     cobertura_do_stop=None if not ps else round(min(cob, abs(q)) / abs(q), 3),
                     condicionais_sem_posicao=[x["algoId"] for x in algos if not ps and x.get("algoId")])
            out[inst] = r
    return out


def bybit(bases):
    from engine import account as AC
    out = {"base_api": AC.BASE, "e_bybit_eu": AC.BASE.rstrip("/") == "https://api.bybit.eu"}
    if not AC.configured():
        out["erro"] = "sem chave de leitura"
        return out
    try:
        k = AC.get("/v5/user/query-api")
        out["chave"] = {"so_leitura": k.get("readOnly") == 1, "uid_presente": bool(k.get("userID"))}
        info = AC.get("/v5/account/info")
        out["conta"] = {"modo_margem": info.get("marginMode"), "unificada": info.get("unifiedMarginStatus")}
        w = (AC.get("/v5/account/wallet-balance", {"accountType": "UNIFIED"}).get("list") or [{}])[0]
        for b in bases:
            c = next((x for x in w.get("coin") or [] if x.get("coin") == b), None)
            out[b] = {"tem_saldo_ou_divida": bool(c), "em_divida_short_margem": bool(c and float(c.get("borrowAmount") or 0) > 0)}
            if c:
                PRIV.append(f"Bybit EU {b}: saldo {c.get('walletBalance')}, divida {c.get('borrowAmount')}")
            for filtro in ("Order", "StopOrder", "tpslOrder"):
                try:
                    o = AC.get("/v5/order/realtime", {"category": "spot", "symbol": f"{b}USDT", "orderFilter": filtro})
                    lst = o.get("list") or []
                    out[b][f"ordens_{filtro}"] = [{"orderId": x.get("orderId"), "lado": x.get("side"), "tipo": x.get("orderType"),
                                                  "trigger": x.get("triggerPrice"), "preco": x.get("price"), "estado": x.get("orderStatus"),
                                                  "orderLinkId": x.get("orderLinkId")} for x in lst]
                    for x in lst:
                        PRIV.append(f"Bybit EU ordem {b} {x.get('orderId')} ({filtro}, {x.get('side')}): qty {x.get('qty')}")
                except Exception as e:
                    out[b][f"ordens_{filtro}"] = f"erro: {str(e)[:80]}"
    except Exception as e:
        out["erro"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out


if __name__ == "__main__":
    bases = sys.argv[1:] or ["RENDER", "SPCX", "XLM"]
    r = {"okx": okx(bases), "bybit_eu": bybit(["XLM"])}
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if PRIV:
        try:
            from engine import alerts
            alerts.send("🔎 Verificação só de leitura (18/11):\n" + "\n".join(PRIV))
        except Exception as e:
            print("telegram falhou:", type(e).__name__)
