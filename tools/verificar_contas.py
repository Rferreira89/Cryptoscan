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


SZ = {}   # tamanhos das condicionais: so para a cobertura (nunca no log publico)


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
                    SZ[x.get("algoId")] = float(x.get("sz") or 0)
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
            # (18/11, correcao) cobertura da MESMA leitura das ordens (antes havia uma 2.a leitura sem verificar erros:
            # uma resposta falhada dava cobertura 0 com a ordem ativa). Leitura com erro: cobertura None (nao verificada)
            cob = 0.0
            leitura_falhou = any("erro" in x for x in algos if x.get("tipo") in ("conditional", "oco"))
            for x in algos:
                if x.get("stop") and x.get("lado") == fecho:
                    if x.get("fecha_posicao"):
                        cob = abs(q)
                    else:
                        cob += SZ.get(x.get("algoId"), 0.0)
            r.update(ordens_condicionais=algos, ordens_normais_pendentes=ords,
                     cobertura_do_stop=None if not ps or leitura_falhou else round(min(cob, abs(q)) / abs(q), 3),
                     leitura_das_condicionais="falhou" if leitura_falhou else "ok",
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
        wall = AC.get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        w = (wall.get("list") or [{}])[0]
        # (18/11) moedas em divida (short em margem) e as que o programa NAO segue, como o motor as ve (so nomes)
        try:
            tk = AC._tickers_ou_none()
            opened = [r for r in json.load(open(os.environ["ESTADO_BYBIT"])).get("ledger", [])
                      if r.get("kind") == "4H" and r.get("status") == "OPEN" and r.get("executed") is not False] \
                if os.environ.get("ESTADO_BYBIT") and os.path.exists(os.environ["ESTADO_BYBIT"]) else None
            out["moedas_em_divida"] = sorted(AC.debts(wall))
            # (18/11) a protecao como o motor novo a ve (engine/protecao.estado_protecao_bybit): so o estado
            import time as _t
            from engine import protecao as PROT
            ords, lidas, t_l = AC.open_orders_lidas()
            out["protecao_como_o_motor_ve"] = {b: PROT.estado_protecao_bybit(f"{b}USDC", "SHORT", ords, lidas, t_l, _t.time())["estado"]
                                               for b in bases if b in AC.debts(wall)}
            seg = {str(r.get("asset") or "").upper() for r in opened or [] if r.get("side") == "SHORT"}
            out["posicoes_sem_registo"] = ([c for c, q in sorted(AC.debts(wall).items()) if c not in seg
                                            and not (((tk or {}).get(c) or [None])[0] is not None and q * (tk or {})[c][0] < 1.0)]
                                           if opened is not None else "sem estado")
        except Exception as e:
            out["moedas_em_divida_erro"] = type(e).__name__
        for b in bases:
            c = next((x for x in w.get("coin") or [] if x.get("coin") == b), None)
            out[b] = {"tem_saldo_ou_divida": bool(c), "em_divida_short_margem": bool(c and float(c.get("borrowAmount") or 0) > 0)}
            if c:
                PRIV.append(f"Bybit EU {b}: saldo {c.get('walletBalance')}, divida {c.get('borrowAmount')}")
            for par in (f"{b}USDC", f"{b}USDT"):              # como o executor (engine/executor.tpsl_orders): por par
                for filtro in (None, "Order", "tpslOrder", "StopOrder"):
                    prm = {"category": "spot", "symbol": par, "limit": 50}
                    if filtro:
                        prm["orderFilter"] = filtro
                    try:
                        lst = AC.get("/v5/order/realtime", prm).get("list") or []
                    except Exception as e:
                        out[b][f"{par}_{filtro}"] = f"erro: {str(e)[:80]}"
                        continue
                    out[b][f"{par}_{filtro}"] = [{"orderId": x.get("orderId"), "lado": x.get("side"), "tipo": x.get("orderType"),
                                                  "filtro": x.get("orderFilter"), "trigger": x.get("triggerPrice"),
                                                  "stopLoss": x.get("stopLoss"), "takeProfit": x.get("takeProfit"),
                                                  "stopOrderType": x.get("stopOrderType"), "estado": x.get("orderStatus"),
                                                  "orderLinkId": x.get("orderLinkId")} for x in lst]
                    for x in lst:
                        PRIV.append(f"Bybit EU ordem {par} {x.get('orderId')} ({filtro}, {x.get('side')}): qty {x.get('qty')}")
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
