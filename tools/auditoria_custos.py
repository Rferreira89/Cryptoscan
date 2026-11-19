"""(19/11, ordem do Rui, ponto 13) Custos REAIS de execucao, so leitura: taxa de comissao efetiva (comissao / valor
executado), separada por corretora, executor, lado, maker/taker. Saida publica so com taxas (%), contagens e bps;
nada de quantidades nem dinheiro."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

out = {}


def agrega(linhas):
    g = {}
    for k, fee, val in linhas:
        a = g.setdefault(k, [0, 0.0, 0.0, []])
        a[0] += 1
        a[1] += fee
        a[2] += val
        if val:
            a[3].append(100 * fee / val)
    return {k: {"n": a[0], "taxa_efetiva_pct": round(100 * a[1] / a[2], 4) if a[2] else None,
                "min_pct": round(min(a[3]), 4) if a[3] else None, "max_pct": round(max(a[3]), 4) if a[3] else None}
            for k, a in sorted(g.items())}


try:
    from engine import account as AC
    st = json.load(open(os.environ["ESTADO_BYBIT"])) if os.environ.get("ESTADO_BYBIT") else {}
    pares = sorted({f"{r['asset']}USDC" for r in st.get("ledger") or [] if r.get("mode") == "REAL" and r.get("executed")})
    t1 = time.time()
    linhas = []
    for par in pares:
        for x in AC.executions_range(par, t1 - 60 * 86400, t1):
            val = float(x.get("execQty") or 0) * float(x.get("execPrice") or 0)
            fee = abs(float(x.get("execFee") or 0))
            moeda = x.get("feeCurrency") or ""
            if moeda and moeda != "USDC":                  # comissao paga na moeda: converte ao preco da execucao
                fee *= float(x.get("execPrice") or 0)
            linhas.append((f"{x.get('side')}|{'maker' if x.get('isMaker') else 'taker'}|{x.get('orderType')}", fee, val))
    out["bybit_ue_spot_60d"] = agrega(linhas)
    try:
        fr = AC.get("/v5/account/fee-rate", {"category": "spot", "symbol": "XLMUSDC"})
        it = (fr.get("list") or [{}])[0]
        out["bybit_ue_taxa_da_conta"] = {"maker_pct": round(100 * float(it.get("makerFeeRate")), 4),
                                         "taker_pct": round(100 * float(it.get("takerFeeRate")), 4)}
    except Exception as e:
        out["bybit_ue_taxa_erro"] = type(e).__name__
    # deslize: preco executado contra a referencia do sinal (so operacoes do programa com os dois precos)
    d = []
    for r in st.get("ledger") or []:
        if r.get("mode") == "REAL" and r.get("exec_price") and r.get("entry"):
            s = -1 if r.get("side") == "SHORT" else 1
            d.append(round(1e4 * s * (r["exec_price"] / r["entry"] - 1), 1))
    out["bybit_deslize_entrada_bps_contra_nos"] = {"n": len(d), "valores": d}
except Exception as e:
    out["bybit_erro"] = f"{type(e).__name__}: {str(e)[:100]}"

try:
    import okx_exec as E
    ins = E.privado("GET", "/api/v5/account/instruments?instType=FUTURES")
    ctv = {x["instId"]: float(x.get("ctVal") or 1) for x in ins.get("data") or []}
    linhas, after = [], ""
    for _ in range(10):
        f = E.privado("GET", f"/api/v5/trade/fills-history?instType=FUTURES&limit=100{after}")
        dd = f.get("data") or []
        if not dd:
            break
        for x in dd:
            val = float(x.get("fillSz") or 0) * ctv.get(x.get("instId"), 1.0) * float(x.get("fillPx") or 0)
            cl = str(x.get("clOrdId") or "")
            ex = "piloto" if cl.startswith("pil") else "executor antigo" if cl.startswith("cs") else "outro"
            linhas.append((f"{ex}|{x.get('side')}|{'maker' if x.get('execType') == 'M' else 'taker'}",
                           abs(float(x.get("fee") or 0)), val))
        after = f"&after={dd[-1].get('billId')}"
    out["okx_futuros_fills"] = agrega(linhas)
    fr = E.privado("GET", "/api/v5/account/trade-fee?instType=FUTURES")
    it = (fr.get("data") or [{}])[0]
    out["okx_taxa_da_conta"] = {k: it.get(k) for k in ("level", "maker", "taker", "makerU", "takerU")}
except Exception as e:
    out["okx_erro"] = f"{type(e).__name__}: {str(e)[:100]}"
print("AUDITORIA_CUSTOS " + json.dumps(out, ensure_ascii=False))
