"""(05/11 16:22, autorizacao expressa do Rui) Cancela SO as 5 ordens limite reais da H40 colocadas as 16:07 na OKX.
Nao abre ordens, nao fecha posicoes: se uma ordem ja tiver executado (total ou parcialmente), a parte executada fica
como posicao com o stop e o objetivo anexados, e so a parte por executar e cancelada. Log publico: so estados."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import okx_exec as E

ORDENS = [("TRUMP", "TRUMP-USD_UM_XPERP-310704", "4073258200106012672"),
          ("WLD", "WLD-USD_UM_XPERP-310613", "4073258219534028800"),
          ("KAITO", "KAITO-USD_UM_XPERP-310725", "4073258234365087744"),
          ("AEON", "AEON-USD_UM_XPERP-310801", "4073258249565245440"),
          ("BILL", "BILL-USD_UM_XPERP-310718", "4073258264429858816")]


def estado(inst, oid):
    d = (E.privado("GET", f"/api/v5/trade/order?instId={inst}&ordId={oid}").get("data") or [{}])[0]
    return d.get("state"), d.get("accFillSz")


def main():
    linhas = []
    for base, inst, oid in ORDENS:
        antes, exec_antes = estado(inst, oid)
        res = "sem acao"
        if antes in ("live", "partially_filled"):
            r = E.privado("POST", "/api/v5/trade/cancel-order", {"instId": inst, "ordId": oid})
            d = (r.get("data") or [{}])[0]
            res = f"pedido de cancelamento: code {r.get('code')} sCode {d.get('sCode')}"
            time.sleep(1)
        depois, exec_depois = estado(inst, oid)
        executado = exec_depois not in (None, "", "0")
        linhas.append(f"{base}: antes={antes} -> depois={depois}; {res}; parte executada: {'sim' if executado else 'nao'}")
        print(linhas[-1], flush=True)
    pos = E.privado("GET", "/api/v5/account/positions?instType=FUTURES")
    abertas = [x.get("instId") for x in (pos.get("data") or []) if float(x.get("pos") or 0) != 0]
    pend = E.privado("GET", "/api/v5/trade/orders-pending?instType=FUTURES")
    pendentes = [x.get("instId") for x in (pend.get("data") or [])]
    algo = E.privado("GET", "/api/v5/trade/orders-algo-pending?ordType=oco&instType=FUTURES")
    protecoes = [x.get("instId") for x in (algo.get("data") or [])]
    print("posicoes abertas:", abertas, "| ordens pendentes:", pendentes, "| protecoes OCO:", protecoes, flush=True)
    import okx_agente as A
    A.telegram("🛑 OKX — cancelamento autorizado das 5 ordens H40 de 05/11 16:07:\n" + "\n".join(linhas) +
               f"\nPosições abertas: {abertas or 'nenhuma'} · ordens pendentes: {pendentes or 'nenhuma'} · proteções OCO: {protecoes or 'nenhuma'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
