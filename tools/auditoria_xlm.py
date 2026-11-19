"""(19/11, ordem do Rui) Auditoria SO DE LEITURA das duas posicoes SHORT de XLM (Bybit UE e OKX, executor antigo).
Nenhuma ordem e enviada, alterada ou cancelada. No log (publico): precos, percentagens, R, taxas e horas.
Quantidades e valores em moeda: so por Telegram. Uso: python3 tools/auditoria_xlm.py"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import okx_exec as E  # noqa: E402

PRIV = []
OUT = {"t": int(time.time())}


def pub(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cryptoscan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"erro": type(e).__name__}


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def velas(url_fmt, bars):
    out = {}
    for b in bars:
        d = pub(url_fmt.format(bar=b))
        out[b] = [[int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])]
                  + ([float(x[7])] if len(x) > 7 else []) for x in (d.get("data") or [])]
    return out


def okx(inst, entrada_reg, stop_reg, alvo_reg):
    r = {"inst": inst}
    pos = E.privado("GET", f"/api/v5/account/positions?instId={inst}")
    ps = [p for p in pos.get("data") or [] if f(p.get("pos"))]
    r["leitura"] = pos.get("code")
    ins = E.privado("GET", f"/api/v5/account/instruments?instType=FUTURES&instId={inst}")
    spec = (ins.get("data") or [{}])[0]
    ctval = f(spec.get("ctVal")) or 1.0
    r["contrato"] = {k: spec.get(k) for k in ("ctVal", "ctValCcy", "settleCcy", "expTime", "lotSz", "minSz")}
    tk = E.A.get(f"/api/v5/market/ticker?instId={inst}")
    tk = (tk or [{}])[0] if isinstance(tk, list) else {}
    r["ticker"] = {k: tk.get(k) for k in ("last", "bidPx", "askPx", "bidSz", "askSz", "vol24h", "high24h", "low24h", "open24h")}
    try:
        livro = E.A.get(f"/api/v5/market/books?instId={inst}&sz=20")
        r["livro_asks"] = [[float(a[0]), float(a[1])] for a in (livro[0]["asks"] if livro else [])]
    except Exception as e:
        r["livro_erro"] = type(e).__name__
    for nome, path in (("funding", f"/api/v5/public/funding-rate?instId={inst}"),
                       ("funding_hist", f"/api/v5/public/funding-rate-history?instId={inst}&limit=60"),
                       ("oi", f"/api/v5/public/open-interest?instType=FUTURES&instId={inst}"),
                       ("mark", f"/api/v5/public/mark-price?instType=FUTURES&instId={inst}")):
        try:
            r[nome] = E.A.get(path)
        except Exception as e:
            r[nome] = {"erro": type(e).__name__}
    if not ps:
        r["posicao"] = None
        return r
    p = ps[0]
    q = f(p["pos"])
    avg = f(p.get("avgPx"))
    ask = f(tk.get("askPx"))
    risco_unit = abs(stop_reg - avg) if stop_reg else None
    base_qty = abs(q) * ctval
    risco = risco_unit * base_qty if risco_unit else None
    upl = f(p.get("upl"))
    fee = f(p.get("fee")) or 0.0
    fund = f(p.get("fundingFee")) or 0.0
    r["posicao"] = {"lado": "SHORT" if q < 0 else "LONG", "preco_medio": avg, "entrada_no_registo": entrada_reg,
                    "alav": p.get("lever"), "margem_modo": p.get("mgnMode"), "mark": p.get("markPx"), "liq": p.get("liqPx"),
                    "aberta_em": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(p.get("cTime") or 0) / 1000)),
                    "upl_pct_do_preco": round(100 * (avg - (f(p.get("markPx")) or avg)) / avg, 3) if q < 0 else None,
                    "upl_R": round(upl / risco, 3) if risco and upl is not None else None,
                    "fees_pagas_R": round(fee / risco, 4) if risco else None,
                    "funding_acumulado_R": round(fund / risco, 4) if risco else None,
                    "margem_pct_do_nocional": round(100 / f(p.get("lever")), 2) if f(p.get("lever")) else None,
                    "uplRatio_sobre_margem_pct": round(100 * (f(p.get("uplRatio")) or 0), 2)}
    if ask and risco:
        r["posicao"]["fecho_ao_ask"] = {"preco": ask, "R_bruto": round((avg - ask) * base_qty / risco, 3) if q < 0 else None}
    PRIV.append(f"OKX {inst}: {q:+g} contratos (ctVal {ctval}), upl {upl}, fee paga {fee}, funding {fund}, "
                f"margem {p.get('imr') or p.get('margin')}, risco ate ao stop {risco:.4f}" if risco else f"OKX {inst}: {q:+g}")
    OUT.setdefault("_okx_qty_base", base_qty)
    return r


def bybit():
    from engine import account as AC
    r = {}
    if not AC.configured():
        return {"erro": "sem chave"}
    wall = AC.get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    w = (wall.get("list") or [{}])[0]
    c = next((x for x in w.get("coin") or [] if x.get("coin") == "XLM"), {}) or {}
    divida = f(c.get("borrowAmount")) or 0.0
    r["em_divida"] = divida > 0
    for par in ("XLMUSDC", "XLMUSDT"):
        tk = pub(f"{AC.BASE}/v5/market/tickers?category=spot&symbol={par}")
        it = ((tk.get("result") or {}).get("list") or [{}])[0]
        r[f"ticker_{par}"] = {k: it.get(k) for k in ("lastPrice", "bid1Price", "ask1Price", "bid1Size", "ask1Size",
                                                     "volume24h", "highPrice24h", "lowPrice24h", "prevPrice24h")}
        lv = pub(f"{AC.BASE}/v5/market/orderbook?category=spot&symbol={par}&limit=50")
        r[f"livro_asks_{par}"] = [[float(a[0]), float(a[1])] for a in ((lv.get("result") or {}).get("a") or [])]
    try:
        ci = AC.get("/v5/account/collateral-info", {"currency": "XLM"})
        x = (ci.get("list") or [{}])[0]
        r["juro_hora"] = x.get("hourlyBorrowRate")
        r["juro_dia_pct"] = round(24 * 100 * (f(x.get("hourlyBorrowRate")) or 0), 5)
    except Exception as e:
        r["juro_erro"] = str(e)[:80]
    t0 = 1794673986 - 3600
    try:
        juros = AC.juros_margem("XLM", t0, time.time())
    except Exception as e:
        juros = None
        r["juros_acum_erro"] = type(e).__name__
    try:
        ex = AC.executions_range("XLMUSDC", t0, time.time())
        r["execucoes"] = [{"lado": x.get("side"), "preco": x.get("execPrice"), "t": time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(x.get("execTime")) / 1000)),
                           "fee_moeda": x.get("feeCurrency") or x.get("feeTokenId"), "maker": x.get("isMaker")} for x in ex]
        fees = sum(f(x.get("execFee")) or 0 for x in ex)
        qty = sum(f(x.get("execQty")) or 0 for x in ex if x.get("side") == "Sell")
        vwap = (sum((f(x.get("execPrice")) or 0) * (f(x.get("execQty")) or 0) for x in ex if x.get("side") == "Sell") / qty) if qty else None
    except Exception as e:
        r["exec_erro"] = f"{type(e).__name__}: {str(e)[:80]}"
        fees, qty, vwap = None, None, None
    r["entrada_vwap"] = vwap
    PRIV.append(f"Bybit UE XLM: divida {divida}, vendido {qty}, fees entrada {fees} (moeda das execucoes), "
                f"juros acumulados {juros} XLM, saldo {c.get('walletBalance')}")
    OUT["_bybit"] = {"divida": divida, "juros": juros, "fees": fees}
    stop = 0.15363886803156823
    ent = vwap or 0.1371
    risco = divida * (stop - ent) if divida else None
    px = f(r["ticker_XLMUSDC"].get("ask1Price"))
    if risco:
        r["upl_R_ao_ask"] = round(divida * (ent - px) / risco, 3) if px else None
        r["fees_entrada_R"] = round((fees or 0) / risco, 4) if fees is not None else None
        r["juros_acum_R"] = round((juros or 0) * (px or ent) / risco, 4) if juros is not None else None
        r["juros_acum_pct_da_divida"] = round(100 * (juros or 0) / divida, 4) if juros is not None else None
        r["fees_moeda_ok"] = "verificar fee_moeda nas execucoes"
    try:
        ords = AC.open_orders()
        r["ordens"] = [{"lado": o.get("side"), "tipo": o.get("orderType"), "trigger": o.get("triggerPrice"), "preco": o.get("price"),
                        "filtro": o.get("orderFilter"), "estado": o.get("orderStatus"), "sym": o.get("symbol")}
                       for o in ords if "XLM" in str(o.get("symbol"))]
    except Exception as e:
        r["ordens_erro"] = type(e).__name__
    return r


def mercado():
    m = {}
    okxp = "https://www.okx.com"
    m["velas_XLM"] = velas(okxp + "/api/v5/market/history-candles?instId=XLM-USDT&bar={bar}&limit=300", ["1H", "4H", "1Dutc"])
    m["velas_BTC"] = velas(okxp + "/api/v5/market/history-candles?instId=BTC-USDT&bar={bar}&limit=300", ["4H", "1Dutc"])
    m["swap_funding"] = pub(okxp + "/api/v5/public/funding-rate?instId=XLM-USDT-SWAP")
    m["swap_funding_hist"] = pub(okxp + "/api/v5/public/funding-rate-history?instId=XLM-USDT-SWAP&limit=60")
    m["swap_oi"] = pub(okxp + "/api/v5/public/open-interest?instType=SWAP&instId=XLM-USDT-SWAP")
    m["oi_hist"] = pub(okxp + "/api/v5/rubik/stat/contracts/open-interest-volume?ccy=XLM&period=1D")
    m["oi_hist_4h"] = pub(okxp + "/api/v5/rubik/stat/contracts/open-interest-volume?ccy=XLM&period=4H")
    m["ls_ratio"] = pub(okxp + "/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=XLM&period=4H")
    m["taker"] = pub(okxp + "/api/v5/rubik/stat/taker-volume?ccy=XLM&instType=CONTRACTS&period=4H")
    m["bybit_linear_funding"] = pub("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=XLMUSDT&limit=30")
    m["bybit_ls"] = pub("https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=XLMUSDT&period=4h&limit=50")
    m["bybit_oi"] = pub("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=XLMUSDT&intervalTime=4h&limit=200")
    return m


if __name__ == "__main__":
    OUT["okx"] = okx("XLM-USD_UM_XPERP-310704", 0.13745, 0.15363, 0.11802)
    try:
        OUT["bybit"] = bybit()
    except Exception as e:
        OUT["bybit"] = {"erro": f"{type(e).__name__}: {str(e)[:120]}"}
    OUT["mercado"] = mercado()
    OUT.pop("_okx_qty_base", None)
    priv_b = OUT.pop("_bybit", None)
    print("AUDITORIA_XLM_JSON_INICIO")
    print(json.dumps(OUT, ensure_ascii=False, separators=(",", ":")))
    print("AUDITORIA_XLM_JSON_FIM")
    if PRIV:
        try:
            from engine import alerts
            alerts.send("🔎 Auditoria XLM (só leitura, 19/11):\n" + "\n".join(PRIV))
        except Exception as e:
            print("telegram falhou:", type(e).__name__)
