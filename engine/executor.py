"""Execucao com um toque (fase 2, decisao do Rui em 2026-10-13).

Corre SO no servidor europeu (workflow executar.yml). Nunca compra sozinho:
cada compra nasce de um toque do Rui no botao "Executar" de um alerta real.

Chave propria (segredos BYBIT_TRADE_KEY / BYBIT_TRADE_SECRET), separada da
chave de leitura. Antes de qualquer ordem confirma na Bybit que a chave:
  - pode negociar spot e NADA mais (sem levantamentos, transferencias ou
    derivados);
  - esta presa a uma lista de IPs (nunca aberta a qualquer IP).
Se nao estiver assim, recusa-se a usa-la.

Pedidos (state["exec_req"], vindos do Telegram ou do acompanhamento):
  comprar    compra o valor do plano em partes, cada parte com o seu objetivo
             e o stop do plano (ordens TP/SL da propria Bybit)
  breakeven  depois do TP1: stop das partes restantes para a entrada
  fechar     saida por tempo / sem reacao: cancela as ordens e vende o resto
  parar      fecha tudo o que o programa abriu
  teste      prova de 5 USDC em BTC: compra, TP/SL, ajuste, cancela, vende

Resultado em exec.json (ramo "execucoes"); o scanner le-o para marcar o
registo. Mensagens de confirmacao vao direto para o Telegram.
"""
import hashlib
import hmac
import json
import math
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bybit.eu"
RECV = "10000"
TIMEOUT = 15
MAX_AGE_BUY = 6 * 3600          # um toque num alerta com mais de 6h e recusado
ZONE_SLIP = 0.005               # aceita ate 0,5% acima da zona de entrada
TEST_USDC = 5.0
LINK = "cs-"                    # prefixo das ordens do programa


def _tag(op):
    """Identificador curto e unico por operacao: ativo + instante do sinal.
    (19/10: com op[-20:] a ENA e a XPL do mesmo sinal ficavam com o mesmo
    orderLinkId e a Bybit recusou o anexo da XPL: "Duplicate clientOrderId".)"""
    return f"{op.split('-')[0][:10]}{op[-11:]}"


class ExecError(Exception):
    pass


# ---------- rede (IPv4: a chave esta presa ao IPv4 do servidor) ----------

_orig_gai = socket.getaddrinfo


def _ipv4_only(host, *a, **k):
    return [r for r in _orig_gai(host, *a, **k) if r[0] == socket.AF_INET] or \
        _orig_gai(host, *a, **k)


def configured():
    return bool(os.environ.get("BYBIT_TRADE_KEY", "").strip()
                and os.environ.get("BYBIT_TRADE_SECRET", "").strip())


def _call(method, path, params=None):
    key = os.environ["BYBIT_TRADE_KEY"].strip()
    secret = os.environ["BYBIT_TRADE_SECRET"].strip()
    ts = str(int(time.time() * 1000))
    if method == "GET":
        payload = urllib.parse.urlencode(sorted((params or {}).items()))
        url, body = f"{BASE}{path}" + (f"?{payload}" if payload else ""), None
    else:
        payload = json.dumps(params or {}, separators=(",", ":"))
        url, body = f"{BASE}{path}", payload.encode()
    sig = hmac.new(secret.encode(), f"{ts}{key}{RECV}{payload}".encode(),
                   hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=body, method=method, headers={
        "X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": RECV,
        "X-BAPI-SIGN": sig, "Content-Type": "application/json",
        "User-Agent": "cryptoscan-exec"})
    socket.getaddrinfo = _ipv4_only
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ExecError(f"{path}: HTTP {e.code}") from None
    except Exception as e:
        raise ExecError(f"{path}: {type(e).__name__}") from None
    finally:
        socket.getaddrinfo = _orig_gai
    if d.get("retCode") != 0:
        raise ExecError(f"{path}: {d.get('retCode')} {str(d.get('retMsg'))[:100]}")
    return d.get("result") or {}


def get(path, params=None):
    return _call("GET", path, params)


def post(path, params):
    return _call("POST", path, params)


# ---------- regras puras (testadas) ----------

def key_ok(info):
    """(ok, motivo). So spot, sem carteira/levantamentos, IPs restritos."""
    try:
        if int(info.get("readOnly")) == 1:
            return False, "a chave é só de leitura: não pode comprar"
    except (TypeError, ValueError):
        return False, "não consegui ler as permissões da chave"
    perms = info.get("permissions") or {}
    # Na Bybit UE a caixa "Trading" da conta unificada da sempre SpotTrade e
    # DerivativesTrade juntas (nao se separam). Aceita-se so esse par: o
    # programa so envia ordens spot e a chave continua sem carteira,
    # levantamentos ou transferencias, presa ao IP do servidor.
    allowed = {"Spot": {"SpotTrade"}, "Derivatives": {"DerivativesTrade"}}
    bad = [k for k, v in perms.items() if v and not set(v) <= allowed.get(k, set())]
    if bad:
        return False, f"a chave tem permissões a mais ({', '.join(sorted(bad))}): só pode ter Spot"
    if not perms.get("Spot"):
        return False, "a chave não tem permissão de negociar spot"
    ips = [x for x in info.get("ips") or [] if x and x != "*"]
    if not ips:
        return False, "a chave não está presa ao IP do servidor"
    return True, "ok"


def dec(step):
    s = f"{float(step):.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def floor_to(x, step):
    st = float(step)
    return math.floor(x / st + 1e-9) * st


def fmt(x, step):
    return f"{floor_to(x, step):.{dec(step)}f}"


def parts_for(size, tps, partials, min_amt):
    """[(valor_usdc, tp)] por parte. Partes abaixo do minimo da Bybit
    juntam-se a anterior (fica com o objetivo mais perto, conservador)."""
    raw = [(size * p / 100, tp) for p, tp in zip(partials, tps) if p and p > 0]
    if not raw:
        raw = [(size, tps[0])]
    tot = sum(q for q, _ in raw)
    raw = [(q * size / tot, tp) for q, tp in raw]        # soma exata = size
    out = []
    for q, tp in raw:
        if out and (q < min_amt * 1.1 or out[-1][0] < min_amt * 1.1):
            out[-1] = (out[-1][0] + q, out[-1][1])
        else:
            out.append((q, tp))
    return out if out and all(q >= min_amt for q, _ in out) else []


def buy_check(state, op, price, now):
    """(plano, motivo_de_recusa). Valida o pedido contra o sinal ao vivo."""
    sig = (state.get("signals") or {}).get(op) or {}
    rec = next((r for r in state.get("ledger") or [] if r.get("id") == op), None)
    plan = sig.get("plan")
    if not sig or not rec or not plan:
        return None, "operação não encontrada"
    if sig.get("mode") == "PAPER":
        return None, "é um sinal em papel, não real"
    if sig.get("status") not in ("ACTIVE", "TRIGGERED"):
        return None, f"o sinal já não está ativo ({str(sig.get('status')).lower()})"
    if rec.get("executed") is True and not rec.get("auto_exec"):
        return None, "já marcaste esta operação como executada à mão"
    if now - (rec.get("issued_at") or now) > MAX_AGE_BUY:
        return None, "o alerta tem mais de 6 horas"
    lo, hi = plan["entry_zone"]
    if price > hi * (1 + ZONE_SLIP):
        return None, f"o preço ({price:g}) já saiu da zona de entrada (até {hi:g})"
    if price <= plan["stop"] * 1.002:
        return None, f"o preço ({price:g}) está colado ao stop ({plan['stop']:g})"
    if price >= plan["tp"][0] * 0.995:
        return None, f"o preço ({price:g}) já está no primeiro objetivo"
    return plan, None


# ---------- Bybit ----------

def instrument(symbol):
    r = get("/v5/market/instruments-info", {"category": "spot", "symbol": symbol})
    it = (r.get("list") or [None])[0]
    if not it:
        raise ExecError(f"{symbol} não existe na Bybit UE")
    ls, pf = it.get("lotSizeFilter") or {}, it.get("priceFilter") or {}
    return {"base_step": ls.get("basePrecision") or "0.000001",
            "quote_step": ls.get("quotePrecision") or "0.01",
            "min_amt": float(ls.get("minOrderAmt") or 5),
            "tick": pf.get("tickSize") or "0.0001"}


def last_price(symbol):
    r = get("/v5/market/tickers", {"category": "spot", "symbol": symbol})
    return float(r["list"][0]["lastPrice"])


def wallet():
    try:
        return get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    except ExecError:
        return get("/v5/account/wallet-balance", {"accountType": "SPOT"})


def held(w, coin):
    from . import account
    return account.coins(w).get(coin.upper(), 0.0)


def usdc_free(w):
    from . import account
    return account.usdc_free(w) or 0.0


def fills(order_id, symbol, base, side="Buy"):
    """(preco medio, quantidade): numa compra, a liquida recebida (sem a
    comissao paga na propria moeda); numa venda, a quantidade vendida."""
    for _ in range(5):
        r = get("/v5/execution/list", {"category": "spot", "symbol": symbol,
                                       "orderId": order_id})
        ex = r.get("list") or []
        if ex:
            q = sum(float(e["execQty"]) for e in ex)
            v = sum(float(e["execQty"]) * float(e["execPrice"]) for e in ex)
            fee = sum(float(e.get("execFee") or 0) for e in ex
                      if (e.get("feeCurrency") or base).upper() == base.upper())
            return v / q, (q - fee) if side == "Buy" else q
        time.sleep(1)
    raise ExecError("a ordem não mostrou execução")


def order_state(order_id, symbol):
    """(estado, quantidade executada, preco medio) de uma ordem pelo historico da Bybit, ou None."""
    for path in ("/v5/order/realtime", "/v5/order/history"):
        try:
            lst = get(path, {"category": "spot", "symbol": symbol, "orderId": order_id}).get("list") or []
        except ExecError:
            continue
        if lst:
            o = lst[0]
            q = float(o.get("cumExecQty") or 0)
            return o.get("orderStatus"), q, float(o.get("avgPrice") or 0) or None
    return None


def fills_or_state(order_id, symbol, base, side):
    """(23/10, SEI) como fills(), mas sem execucao vista pergunta o estado da ordem: uma IOC
    cancelada sem nada executado devolve (None, 0.0) em vez de rebentar o pedido."""
    try:
        return fills(order_id, symbol, base, side=side)
    except ExecError:
        st = order_state(order_id, symbol)
        if st and st[1] > 0 and st[2]:
            return st[2], st[1]
        if st and st[0] in ("Cancelled", "Rejected", "Deactivated", "PartiallyFilledCanceled") and st[1] == 0:
            return None, 0.0
        raise


def best_bid(symbol):
    try:
        b = get("/v5/market/orderbook", {"category": "spot", "symbol": symbol, "limit": 5}).get("b") or []
        return float(b[0][0]) if b else None
    except (ExecError, KeyError, IndexError, ValueError, TypeError):
        return None


SHORT_MAX_SLIP = 0.006          # (23/10) venda a descoberto: no maximo 0,6% abaixo do ultimo preco


def tpsl_orders(symbol):
    """Ordens de protecao abertas no par. A Bybit UE guarda o TP/SL anexado
    a uma compra limite como UMA ordem de venda 'BidirectionalTpslOrder'
    (filtro Order, campos takeProfit/stopLoss), que prende as moedas."""
    seen = {}
    for flt in (None, "Order", "tpslOrder", "StopOrder"):
        prm = {"category": "spot", "symbol": symbol, "limit": 50}
        if flt:
            prm["orderFilter"] = flt
        try:
            r = get("/v5/order/realtime", prm)
        except ExecError:
            continue
        for o in r.get("list") or []:
            prot = o.get("stopOrderType") or float(o.get("triggerPrice") or 0) > 0 or \
                float(o.get("stopLoss") or 0) > 0
            # compras protegem-se com ordens de venda; vendas a descoberto com
            # ordens de compra (15/10: o teste do short deixou uma por cancelar)
            if prot:
                seen[o["orderId"]] = dict(o, _flt=o.get("orderFilter") or flt or "Order")
    return list(seen.values())


def _match_children(symbol, parts, t0, step):
    """Liga cada parte a sua ordem de protecao (quantidade igual, criada
    depois da compra)."""
    free = [o for o in tpsl_orders(symbol) if float(o.get("createdTime") or 0) >= t0 * 1000 - 5000]
    for p in parts:
        q = floor_to(p["qty"], step)
        # numa venda a descoberto a protecao (compra) vem em USDC: aceita os dois
        alvos = [(q, max(float(step) * 2, q * 0.03))] + \
            ([(p["usdc"], p["usdc"] * 0.05)] if p.get("usdc") else [])

        def dist(o):
            v = float(o.get("qty") or 0)
            return min(abs(v - a) / max(tol, 1e-12) for a, tol in alvos)
        best = min(free, key=dist, default=None)
        if best is not None and dist(best) <= 1.0:
            p["filho"] = best["orderId"]
            free.remove(best)


def usdc_debt(w):
    """Divida em USDC (emprestimo da margem) na conta unificada."""
    return coin_debt(w, "USDC")


def coin_debt(w, coin):
    """Divida numa moeda (emprestimo da margem) na conta unificada."""
    for acc in w.get("list") or []:
        for c in acc.get("coin") or []:
            if c.get("coin") == coin.upper():
                for k in ("spotBorrow", "borrowAmount"):
                    try:
                        v = float(c.get(k) or 0)
                    except (TypeError, ValueError):
                        v = 0.0
                    if v:
                        return v
                return 0.0
    return 0.0


def usdc_fields(w):
    for acc in w.get("list") or []:
        for c in acc.get("coin") or []:
            if c.get("coin") == "USDC":
                return {k: c.get(k) for k in ("walletBalance", "equity", "borrowAmount", "spotBorrow",
                                               "accruedInterest", "availableToBorrow", "locked")}
    return {}


def repay_usdc(amount):
    """Paga 'amount' USDC de divida (so a criada pelo programa)."""
    amt = math.ceil(amount * 100) / 100
    return post("/v5/account/repay", {"coin": "USDC", "amount": f"{amt:.2f}"})


def place_part(symbol, quote, tp, stop, inst, tag, px=None, margin=False):
    """Compra 'quote' USDC com TP e stop da Bybit anexados.

    A Bybit UE so aceita TP/SL anexados em ordens LIMITE (provado no
    diagnostico de 2026-10-13), por isso a compra e uma ordem limite IOC
    ligeiramente acima do preco: executa ja ao preco de mercado ou nao
    executa nada. Se o anexo for recusado, compra sem ele e o chamador poe
    um stop condicional."""
    px = px or last_price(symbol)
    lim = float(fmt(px * (1 + LIMIT_SLIP), inst["tick"])) or px
    qty = floor_to(quote / lim, inst["base_step"])
    base = {"category": "spot", "symbol": symbol, "side": "Buy", "orderType": "Limit",
            "timeInForce": "IOC", "price": fmt(lim, inst["tick"]),
            "qty": fmt(qty, inst["base_step"]), "orderLinkId": f"{LINK}{tag}"[:36]}
    if margin:
        base["isLeverage"] = 1
    try:
        r = post("/v5/order/create", dict(base, takeProfit=fmt(tp, inst["tick"]),
                                          stopLoss=fmt(stop, inst["tick"]),
                                          tpOrderType="Market", slOrderType="Market"))
        return r["orderId"], True
    except ExecError as e:
        global LAST_ATTACH_ERR
        LAST_ATTACH_ERR = str(e)[:160]
        if "insufficient" in str(e).lower() or "balance" in str(e).lower():
            raise
        if "duplicate" in str(e).lower():       # este pedido ja foi enviado: nunca duas vezes
            raise
        r = post("/v5/order/create", dict(base, orderLinkId=f"{LINK}{tag}b"[:36]))
        return r["orderId"], False


LIMIT_SLIP = 0.003              # limite IOC 0,3% acima: executa como mercado
LAST_ATTACH_ERR = None


def stop_order(symbol, qty, stop, inst, tag):
    r = post("/v5/order/create", {"category": "spot", "symbol": symbol, "side": "Sell",
                                  "orderType": "Market", "qty": fmt(qty, inst["base_step"]),
                                  "triggerPrice": fmt(stop, inst["tick"]),
                                  "orderFilter": "tpslOrder",
                                  "orderLinkId": f"{LINK}{tag}"[:36]})
    return r["orderId"]


def sell_all(symbol, qty, inst, tag):
    q = floor_to(qty, inst["base_step"])
    if q <= 0:
        return None
    r = post("/v5/order/create", {"category": "spot", "symbol": symbol, "side": "Sell",
                                  "orderType": "Market", "qty": fmt(q, inst["base_step"]),
                                  "marketUnit": "baseCoin", "orderLinkId": f"{LINK}{tag}"[:36]})
    return r["orderId"]


def cancel(symbol, o):
    post("/v5/order/cancel", {"category": "spot", "symbol": symbol,
                              "orderId": o["orderId"], "orderFilter": o.get("_flt", "tpslOrder")})


def ours(orders, op):
    """Ordens de protecao desta operacao: as guardadas na compra; se
    faltarem, as de venda criadas depois da compra com a quantidade de uma
    parte (nunca ordens anteriores do Rui)."""
    ids = {p.get("filho") for p in op.get("partes") or []} | \
        {p.get("stopId") for p in op.get("partes") or []}
    ids.discard(None)
    out = [o for o in orders if o["orderId"] in ids]
    if out:
        return out
    t0 = (op.get("criado") or 0) * 1000 - 5000
    qs = [p.get("qty") or 0 for p in op.get("partes") or []] + \
        [p.get("usdc") or 0 for p in op.get("partes") or [] if op.get("lado") == "SHORT"]
    return [o for o in orders if float(o.get("createdTime") or 0) >= t0 and
            any(abs(float(o.get("qty") or 0) - x) <= max(1e-9, x * 0.03) for x in qs if x)]


# ---------- acoes ----------

def do_buy(state, req, ex, now, send):
    from . import account
    op = req["op"]
    rec = next((r for r in state.get("ledger") or [] if r.get("id") == op), {})
    if (ex["ops"].get(op) or {}).get("status") == "aberta":
        return "já executada antes"
    symbol = account.symbol_of(rec) if rec else None
    if not symbol:
        return "operação não encontrada"
    px = last_price(symbol)
    plan, why = buy_check(state, op, px, now)
    if why:
        send(f"⚠️ Não executei {rec.get('asset')}: {why}. Nada foi comprado.")
        ex["ops"][op] = {"asset": rec.get("asset"), "status": "recusada", "motivo": why, "t": now}
        return why
    inst = instrument(symbol)
    w = wallet()
    size = float(plan.get("position_usdc") or rec.get("position_usdc") or 0)
    free = usdc_free(w)
    if size <= 0:
        return "plano sem valor"
    # alavancagem do plano (margem spot da Bybit), limitada a da conta
    lev_plan = float((plan.get("leverage") or {}).get("use") or 1)
    try:
        lev_acct = float(get("/v5/spot-margin-trade/state").get("spotLeverage") or 1)
    except ExecError:
        lev_acct = 1.0
    need = min(10, math.ceil(lev_plan - 1e-9))
    if lev_plan > 1 and need > lev_acct:
        # a conta tem um teto de alavancagem (2x a 10x) definido na Bybit:
        # sobe-o ao necessario para este plano (nunca o baixa)
        try:
            post("/v5/spot-margin-trade/set-leverage", {"leverage": str(need)})
            lev_acct = float(need)
        except ExecError as e:
            print("teto de alavancagem nao alterado:", e)
    lev = max(1.0, min(lev_plan, lev_acct))
    reduced = False
    cap = math.floor(free * 0.98 * lev * 100) / 100       # o maximo que a margem permite
    if cap < size:
        size, reduced = cap, True
    margin = size > free * 0.98
    debt0 = usdc_debt(w)
    parts = parts_for(size, plan["tp"], plan.get("partials") or [100], inst["min_amt"])
    if not parts:
        why = (f"USDC livre insuficiente ({free:.2f}; mínimo da Bybit "
               f"{inst['min_amt']:g} por ordem)")
        send(f"⚠️ Não executei {rec['asset']}: {why}. Nada foi comprado.")
        ex["ops"][op] = {"asset": rec["asset"], "status": "recusada", "motivo": why, "t": now}
        return why
    o = {"asset": rec["asset"], "symbol": symbol, "status": "aberta", "criado": now,
         "stop": plan["stop"], "partes": [], "t": now}
    for i, (q, tp) in enumerate(parts):
        try:
            oid, attached = place_part(symbol, q, tp, plan["stop"], inst, f"{_tag(op)}-{i}",
                                       margin=margin)
        except ExecError as e:
            o["erro"] = str(e)[:120]
            break
        try:
            avg, qty = fills(oid, symbol, rec["asset"])
        except ExecError as e:               # ordem sem execucao vista: para aqui, guarda o resto
            o["erro"] = f"parte {i + 1} sem execução confirmada ({str(e)[:80]}); verifica na app"
            break
        part = {"orderId": oid, "usdc": round(q, 2), "tp": tp, "preco": avg,
                "qty": qty, "anexo": attached}
        if not attached:
            part["anexo_erro"] = LAST_ATTACH_ERR          # porque a Bybit recusou (diagnostico)
        if not attached:                     # sem anexo: pelo menos o stop
            try:
                part["stopId"] = stop_order(symbol, qty, plan["stop"], inst, f"{_tag(op)}-s{i}")
            except ExecError as e:
                part["stop_erro"] = str(e)[:100]
        o["partes"].append(part)
    if not o["partes"]:
        o["status"] = "recusada"
        if "sem execução confirmada" in str(o.get("erro")):
            o["status"] = "verificar"
            send(f"🚨 A compra de {rec['asset']} foi enviada mas não confirmei a execução. Verifica na app "
                 f"da Bybit: se houver moedas, põe o stop em {plan['stop']:g}.")
        else:
            send(f"⚠️ A compra de {rec['asset']} falhou na Bybit: {o.get('erro')}. Nada foi comprado.")
        ex["ops"][op] = o
        return o.get("erro")
    for _ in range(6):                       # a protecao aparece segundos depois
        time.sleep(2)
        try:
            _match_children(symbol, [p for p in o["partes"] if not p.get("filho")], now, inst["base_step"])
        except ExecError:
            pass
        if all(p.get("filho") or not p.get("anexo") for p in o["partes"]):
            break
    try:
        o["emprestado"] = round(max(0.0, usdc_debt(wallet()) - debt0), 4)
    except ExecError:
        o["emprestado"] = None
    q_tot = sum(p["qty"] for p in o["partes"])
    o["entrada"] = sum(p["preco"] * p["qty"] for p in o["partes"]) / q_tot
    o["qty"] = q_tot
    o["usdc"] = round(sum(p["usdc"] for p in o["partes"]), 2)
    ex["ops"][op] = o
    miss = [p for p in o["partes"] if not p["anexo"]]
    L = [f"⚡ <b>Executado: {rec['asset']}</b>",
         f"Compra de {o['usdc']:.2f} USDC a {o['entrada']:.6g} ({q_tot:.6g} {rec['asset']}), "
         f"em {len(o['partes'])} parte{'s' if len(o['partes']) > 1 else ''}.",
         (f"Stop em {plan['stop']:g} em todas as partes (fica na Bybit até ao fim)."
          if not any(p.get("stop_erro") for p in o["partes"]) else
          f"🚨 O STOP NÃO FICOU na Bybit em {sum(1 for p in o['partes'] if p.get('stop_erro'))} parte(s): "
          f"põe o stop em {plan['stop']:g} na app agora.")]
    L += [f"• Parte {i + 1}: {p['usdc']:.2f} USDC → objetivo {p['tp']:g}"
          for i, p in enumerate(o["partes"])]
    if o.get("emprestado"):
        L.append(f"Alavancagem {o['usdc'] / max(o['usdc'] - o['emprestado'], 0.01):.2f}x: "
                 f"{o['emprestado']:.2f} USDC emprestados pela Bybit (pagos na venda).")
    if reduced:
        L.append(f"Valor reduzido ao que o teu USDC livre ({free:.2f}) e a alavancagem "
                 f"da conta ({lev_acct:g}x) permitem.")
    if o.get("erro"):
        L.append(f"⚠️ Uma parte falhou: {o['erro']}")
    miss = [p for p in miss if not p.get("stop_erro")]
    if miss:
        L.append("⚠️ A Bybit não aceitou o objetivo anexado em "
                 f"{len(miss)} parte(s). O stop ficou na Bybit como ordem condicional (na app: "
                 "Ordens → separador TP/SL). O objetivo fica a cargo do programa: quando o preço "
                 "lá chegar, vende (1 a 2 minutos).")
    L.append("Depois do TP1, se o preço voltar à entrada, o programa vende o resto "
             "(1 a 2 minutos). Confirma na app da Bybit as ordens abertas.")
    send("\n".join(L), html=True)
    return "ok"


# ---------- vendas a descoberto (decisao do Rui, 2026-10-15) ----------
# Margem spot da Bybit UE: vender com isLeverage=1 uma moeda que nao se tem
# pede-a emprestada; recomprar devolve-a. Stop = ordem condicional de COMPRA
# acima da entrada. So depois de um teste real pequeno (teste_short) passar.

def short_check(state, op, price, now):
    """(plano, motivo) para uma venda a descoberto: o espelho de buy_check."""
    sig = (state.get("signals") or {}).get(op) or {}
    rec = next((r for r in state.get("ledger") or [] if r.get("id") == op), None)
    plan = sig.get("plan")
    if not sig or not rec or not plan:
        return None, "operação não encontrada"
    if sig.get("mode") == "PAPER":
        return None, "é um sinal em papel, não real"
    if sig.get("status") not in ("ACTIVE", "TRIGGERED"):
        return None, f"o sinal já não está ativo ({str(sig.get('status')).lower()})"
    if rec.get("executed") is True and not rec.get("auto_exec"):
        return None, "já marcaste esta operação como executada à mão"
    if now - (rec.get("issued_at") or now) > MAX_AGE_BUY:
        return None, "o alerta tem mais de 6 horas"
    lo, hi = plan["entry_zone"]
    if price < lo * (1 - ZONE_SLIP):
        return None, f"o preço ({price:g}) já saiu da zona de venda (desde {lo:g})"
    if price >= plan["stop"] * 0.998:
        return None, f"o preço ({price:g}) está colado ao stop ({plan['stop']:g})"
    if price <= plan["tp"][0] * 1.005:
        return None, f"o preço ({price:g}) já está no primeiro objetivo"
    return plan, None


def place_short_part(symbol, quote, tp, stop, inst, tag, px=None):
    """Vende a descoberto ~'quote' USDC (moeda emprestada) com TP/SL anexados;
    limite IOC ligeiramente abaixo do preco (executa ja ou nao executa)."""
    px = px or last_price(symbol)
    # (23/10) a SEI de 23/10 nao executou: a IOC a 0,3% abaixo do ultimo preco ficou acima dos
    # compradores (livro fino). Agora o limite segue o melhor comprador, ate 0,6% abaixo do ultimo
    # preco; se os compradores estiverem mais longe, nao vende (o custo comeria a vantagem).
    bid = best_bid(symbol)
    if bid is not None and bid < px * (1 - SHORT_MAX_SLIP):
        raise ExecError(f"livro fino: o melhor comprador está {100 * (1 - bid / px):.2f}% abaixo do último preço")
    alvo = min(px * (1 - LIMIT_SLIP), bid * 0.998) if bid else px * (1 - LIMIT_SLIP)
    lim = float(fmt(max(alvo, px * (1 - SHORT_MAX_SLIP)), inst["tick"])) or px
    qty = floor_to(quote / lim, inst["base_step"])
    base = {"category": "spot", "symbol": symbol, "side": "Sell", "orderType": "Limit",
            "timeInForce": "IOC", "price": fmt(lim, inst["tick"]), "isLeverage": 1,
            "qty": fmt(qty, inst["base_step"]), "orderLinkId": f"{LINK}{tag}"[:36]}
    try:
        r = post("/v5/order/create", dict(base, takeProfit=fmt(tp, inst["tick"]),
                                          stopLoss=fmt(stop, inst["tick"]),
                                          tpOrderType="Market", slOrderType="Market"))
        return r["orderId"], True
    except ExecError as e:
        global LAST_ATTACH_ERR
        LAST_ATTACH_ERR = str(e)[:160]
        if "insufficient" in str(e).lower() or "balance" in str(e).lower():
            raise
        if "duplicate" in str(e).lower():       # este pedido ja foi enviado: nunca duas vezes
            raise
        r = post("/v5/order/create", dict(base, orderLinkId=f"{LINK}{tag}b"[:36]))
        return r["orderId"], False


def stop_order_buy(symbol, qty, stop, inst, tag):
    """Stop de uma venda a descoberto: compra condicional acima do preco."""
    r = post("/v5/order/create", {"category": "spot", "symbol": symbol, "side": "Buy",
                                  "orderType": "Market", "marketUnit": "baseCoin", "isLeverage": 1,
                                  "qty": fmt(qty, inst["base_step"]),
                                  "triggerPrice": fmt(stop, inst["tick"]),
                                  "orderFilter": "tpslOrder",
                                  "orderLinkId": f"{LINK}{tag}"[:36]})
    return r["orderId"]


def buy_back(symbol, qty, inst, tag):
    """Recompra 'qty' moedas (devolve o emprestimo de uma venda a descoberto)."""
    q = math.ceil(qty / float(inst["base_step"])) * float(inst["base_step"])
    if q <= 0:
        return None
    r = post("/v5/order/create", {"category": "spot", "symbol": symbol, "side": "Buy",
                                  "orderType": "Market", "marketUnit": "baseCoin", "isLeverage": 1,
                                  "qty": fmt(q, inst["base_step"]), "orderLinkId": f"{LINK}{tag}"[:36]})
    return r["orderId"]


def repay_coin(coin, amount, step):
    amt = math.ceil(amount / float(step)) * float(step)
    return post("/v5/account/repay", {"coin": coin.upper(), "amount": fmt(amt, step)})


def do_short(state, req, ex, now, send):
    """Vende a descoberto pelo botao Executar (espelho de do_buy, uma parte
    por objetivo, stop condicional de compra acima)."""
    from . import account
    op = req["op"]
    rec = next((r for r in state.get("ledger") or [] if r.get("id") == op), {})
    if (ex["ops"].get(op) or {}).get("status") == "aberta":
        return "já executada antes"
    symbol = account.symbol_of(rec) if rec else None
    if not symbol:
        return "operação não encontrada"
    px = last_price(symbol)
    plan, why = short_check(state, op, px, now)
    if why:
        send(f"⚠️ Não executei a venda de {rec.get('asset')}: {why}. Nada foi vendido.")
        ex["ops"][op] = {"asset": rec.get("asset"), "status": "recusada", "motivo": why, "t": now}
        return why
    inst = instrument(symbol)
    w = wallet()
    free = usdc_free(w)
    size = float(plan.get("position_usdc") or rec.get("position_usdc") or 0)
    try:
        lev_acct = float(get("/v5/spot-margin-trade/state").get("spotLeverage") or 2)
    except ExecError:
        lev_acct = 2.0
    cap = math.floor(free * 0.95 * max(1.0, lev_acct) * 100) / 100
    reduced = cap < size
    size = min(size, cap)
    d0 = coin_debt(w, rec["asset"])
    parts = parts_for(size, plan["tp"], plan.get("partials") or [100], inst["min_amt"])
    if not parts:
        why = f"margem insuficiente (USDC livre {free:.2f}; mínimo da Bybit {inst['min_amt']:g})"
        send(f"⚠️ Não executei a venda de {rec['asset']}: {why}. Nada foi vendido.")
        ex["ops"][op] = {"asset": rec["asset"], "status": "recusada", "motivo": why, "t": now}
        return why
    o = {"asset": rec["asset"], "symbol": symbol, "status": "aberta", "criado": now, "lado": "SHORT",
         "stop": plan["stop"], "partes": [], "t": now}
    for i, (q, tp) in enumerate(parts):
        try:
            oid, attached = place_short_part(symbol, q, tp, plan["stop"], inst, f"{_tag(op)}-v{i}", px=px)
        except ExecError as e:
            o["erro"] = str(e)[:120]
            break
        avg, qty = fills_or_state(oid, symbol, rec["asset"], "Sell")
        if not qty:                          # IOC sem execucao: nada vendido, nada emprestado
            o["erro"] = "sem execução: não havia compradores ao preço limite (livro fino)"
            break
        part = {"orderId": oid, "usdc": round(q, 2), "tp": tp, "preco": avg, "qty": qty, "anexo": attached}
        if not attached:
            part["anexo_erro"] = LAST_ATTACH_ERR
            try:
                part["stopId"] = stop_order_buy(symbol, qty * 1.002, plan["stop"], inst, f"{_tag(op)}-s{i}")
            except ExecError as e:
                part["stop_erro"] = str(e)[:100]
        o["partes"].append(part)
    if not o["partes"]:
        o["status"] = "recusada"
        send(f"⚠️ A venda a descoberto de {rec['asset']} falhou na Bybit: {o.get('erro')}. Nada foi vendido.")
        ex["ops"][op] = o
        return o.get("erro")
    for _ in range(6):
        time.sleep(2)
        try:
            _match_children(symbol, [p for p in o["partes"] if not p.get("filho")], now, inst["base_step"])
        except ExecError:
            pass
        if all(p.get("filho") or not p.get("anexo") for p in o["partes"]):
            break
    q_tot = sum(p["qty"] for p in o["partes"])
    o.update(entrada=sum(p["preco"] * p["qty"] for p in o["partes"]) / q_tot, qty=q_tot,
             usdc=round(sum(p["usdc"] for p in o["partes"]), 2))
    try:
        o["emprestado_moeda"] = round(max(0.0, coin_debt(wallet(), rec["asset"]) - d0), 10)
    except ExecError:
        o["emprestado_moeda"] = None
    ex["ops"][op] = o
    L = [f"⚡ <b>Executado: venda a descoberto de {rec['asset']}</b>",
         f"Vendi {q_tot:.6g} {rec['asset']} emprestados a {o['entrada']:.6g} ({o['usdc']:.2f} USDC).",
         f"Stop (compra) em {plan['stop']:g}, acima da entrada; fica na Bybit até ao fim."]
    L += [f"• Parte {i + 1}: {p['usdc']:.2f} USDC → objetivo {p['tp']:g}" for i, p in enumerate(o["partes"])]
    if reduced:
        L.append(f"Valor reduzido ao que a margem permite (USDC livre {free:.2f}).")
    if any(not p["anexo"] for p in o["partes"]):
        L.append("⚠️ A Bybit não aceitou o objetivo anexado: o stop ficou como ordem condicional "
                 "(Ordens → TP/SL) e o objetivo é recomprado pelo programa.")
    L.append("No TP1 o programa desce o stop para a entrada na Bybit. Pagas juros pela moeda "
             "emprestada enquanto a venda estiver aberta.")
    send("\n".join(L), html=True)
    return "ok"


def close_short(state, req, ex, now, send, why):
    op = ex["ops"][req["op"]]
    inst = instrument(op["symbol"])
    for o in ours(tpsl_orders(op["symbol"]), op):
        try:
            cancel(op["symbol"], o)
        except ExecError as e:
            op.setdefault("avisos", []).append(f"cancelar: {str(e)[:80]}")
    time.sleep(1)
    debt = coin_debt(wallet(), op["asset"])
    owe = min(debt, (op.get("emprestado_moeda") or op["qty"]) * 1.01) if debt else 0.0
    oid = buy_back(op["symbol"], owe * 1.002, inst, f"{_tag(req['op'])}-r") if owe > 0 else None
    time.sleep(2)
    try:                                       # devolve o que ainda faltar com as moedas compradas
        left = coin_debt(wallet(), op["asset"])
        if left > 0 and held(wallet(), op["asset"]) > 0:
            repay_coin(op["asset"], min(left, held(wallet(), op["asset"])), inst["base_step"])
            op["pago_moeda"] = left
    except ExecError as e:
        op.setdefault("avisos", []).append(f"devolver: {str(e)[:80]}")
    op.update(status="fechada", fechado=now, motivo=why)
    if oid:
        avg, q = fills(oid, op["symbol"], op["asset"])
        op["saida"] = avg
        send(f"🏁 {op['asset']} (venda a descoberto): {why}. Recomprei {q:.6g} a {avg:.6g}, "
             "devolvi o empréstimo e cancelei as ordens abertas.")
    else:
        send(f"🏁 {op['asset']} (venda a descoberto): {why}. Já não havia empréstimo por devolver; "
             "cancelei as ordens abertas.")
    return "ok"


def breakeven_short(state, req, ex, now, send):
    op = ex["ops"][req["op"]]
    inst = instrument(op["symbol"])
    # (20/10) igual as compras: so depois de a Bybit recomprar a parte do TP1.
    # Exposicao a descoberto = moeda devida menos moeda ja recomprada na conta.
    w = wallet()
    nucleo_q = float(((ex.get("nucleo") or {}).get(op["asset"]) or {}).get("qty") or 0)
    net = coin_debt(w, op["asset"]) - max(0.0, held(w, op["asset"]) - nucleo_q)
    partes = op.get("partes") or []
    if net <= 0.02 * (op.get("qty") or 0):
        op.update(status="fechada", fechado=now, motivo="fechada na Bybit (stop ou objetivos)", be_pendente=False)
        return "já fechada na Bybit"
    if len(partes) > 1 and net > (op.get("qty") or 0) - 0.5 * (partes[0].get("qty") or 0):
        if not op.get("be_pendente"):
            send(f"⏳ {op['asset']} (venda a descoberto): o sinal viu o TP1, mas na Bybit a parte do TP1 ainda "
                 "não foi recomprada. Mantenho as ordens originais; desço o stop para a entrada quando recomprar.")
        op["be_pendente"] = True
        return "à espera da recompra do TP1 na Bybit"
    op["be_pendente"] = False
    new = float(fmt(op["entrada"] * 0.999, inst["tick"]))
    olds = ours(tpsl_orders(op["symbol"]), op)
    if any(0 < float(o.get("triggerPrice") or 0) <= new * 1.001 for o in olds):
        return "stop já na entrada"
    for o in olds:
        try:
            cancel(op["symbol"], o)
        except ExecError as e:
            op.setdefault("avisos", []).append(f"cancelar: {str(e)[:80]}")
    time.sleep(1)
    owe = coin_debt(wallet(), op["asset"])
    try:
        sid = stop_order_buy(op["symbol"], owe * 1.002, new, inst, f"{_tag(req['op'])}-be")
        for p in op.get("partes") or []:
            p.update(stopId=sid, filho=sid, anexo=False)
    except ExecError as e:
        send(f"⚠️ {op['asset']}: TP1 atingido, mas não consegui descer o stop para a entrada "
             f"({str(e)[:60]}). Põe-no à mão a {new:.6g}.")
        return "erro"
    op["stop"] = new
    send(f"🔒 {op['asset']} (venda a descoberto): TP1 atingido. O stop desceu para a entrada "
         f"({new:.6g}) na Bybit — esta operação já não pode dar perda.")
    return "ok"


def do_test_short(state, req, ex, now, send):
    """Prova real e pequena da venda a descoberto: vende ~6 USDC de BTC
    emprestado (TP/SL anexados), cancela a protecao, recompra e confirma que
    o emprestimo de BTC ficou devolvido. Custa so as comissoes."""
    sym, steps = "BTCUSDC", []
    inst = instrument(sym)
    try:
        w0 = wallet()
        d0 = coin_debt(w0, "BTC")
        steps.append(f"antes: USDC livre {usdc_free(w0):.2f}, dívida BTC {d0:.8f}")
        px = last_price(sym)
        q = max(inst["min_amt"] * 1.2, 6.0)
        oid, attached = place_short_part(sym, q, px * 0.95, px * 1.05, inst, f"ts-{now}", px=px)
        avg, qty = fills(oid, sym, "BTC", side="Sell")
        steps.append(f"venda a descoberto {qty:.8f} BTC a {avg:.2f} (anexo: "
                     f"{'sim' if attached else 'não — ' + str(LAST_ATTACH_ERR)})")
        time.sleep(2)
        d1 = coin_debt(wallet(), "BTC")
        steps.append(f"empréstimo de BTC criado: {d1 - d0:.8f}")
        od = []
        for _ in range(10):
            od = [o for o in tpsl_orders(sym) if o.get("side") == "Buy"
                  and float(o.get("createdTime") or 0) >= (now - 30) * 1000]
            if od:
                break
            time.sleep(2)
        if attached and not od:
            steps.append("ERRO: a proteção anexada não apareceu para cancelar")
        for o in od:
            cancel(sym, o)
            steps.append(f"cancelar proteção ({o.get('stopOrderType')}): ok")
        time.sleep(1)
        rid = buy_back(sym, max(d1 - d0, qty) * 1.002, inst, f"tsr{now % 100000}")
        a2, q2 = fills(rid, sym, "BTC")
        steps.append(f"recompra {q2:.8f} BTC a {a2:.2f}")
        time.sleep(2)
        left = coin_debt(wallet(), "BTC") - d0
        if left > 1e-8:
            repay_coin("BTC", left, inst["base_step"])
            time.sleep(2)
            left = coin_debt(wallet(), "BTC") - d0
        steps.append(f"dívida de BTC no fim: {max(left, 0):.8f}")
        if left > 1e-6:
            steps.append("ERRO: ficou empréstimo de BTC por devolver")
    except ExecError as e:
        steps.append(f"ERRO: {e}")
    ex["teste_short"] = {"t": now, "passos": steps}
    send("🧪 <b>Teste de venda a descoberto</b>\n" + "\n".join(f"• {x}" for x in steps[-7:]), html=True)
    return "ok"


def do_breakeven(state, req, ex, now, send):
    if (ex["ops"].get(req["op"]) or {}).get("lado") == "SHORT" and \
            (ex["ops"][req["op"]]).get("status") == "aberta":
        return breakeven_short(state, req, ex, now, send)
    return _breakeven_long(state, req, ex, now, send)


def _breakeven_long(state, req, ex, now, send):
    """Depois do TP1: o stop das moedas que restam sobe para a entrada, NA
    BYBIT (decisao do Rui, 2026-10-15: "porque e que tenho de o por a mao?").
    A Bybit UE nao deixa alterar a protecao anexada (170312), por isso: tenta
    alterar; se nao der, cancela a ordem antiga e cria um stop novo na
    entrada (o objetivo final passa a ser vendido pelo programa)."""
    op = ex["ops"].get(req["op"]) or {}
    if op.get("status") != "aberta":
        return "sem operação aberta do programa"
    inst = instrument(op["symbol"])
    # (20/10, ENA) o TP1 do sinal vem do preco da Binance; na Bybit a parte do
    # TP1 pode ainda nao ter vendido. So se mexe no stop depois de a Bybit a
    # vender: ate la a ordem do TP1 fica, e volta-se a ver de 15 em 15 minutos.
    partes = op.get("partes") or []
    nucleo_q = float(((ex.get("nucleo") or {}).get(op["asset"]) or {}).get("qty") or 0)
    have = max(0.0, held(wallet(), op["asset"]) - nucleo_q)      # as moedas do nucleo nao contam
    if have <= 0.02 * (op.get("qty") or 0):
        op.update(status="fechada", fechado=now, motivo="fechada na Bybit (stop ou objetivos)", be_pendente=False)
        return "já fechada na Bybit"
    p0 = partes[0] if partes else {}
    if len(partes) > 1 and not p0.get("anexo") and have > (op.get("qty") or 0) - 0.5 * (p0.get("qty") or 0):
        # (21/10, XPL) a Bybit recusou o objetivo anexado: nao ha ordem do TP1 na
        # Bybit e ela nunca vendia. E o programa que vende a parte do TP1 (se o
        # preco estiver no objetivo) e depois sobe o stop do resto para a entrada.
        tp1, px = float(p0.get("tp") or 0), last_price(op["symbol"])
        if tp1 and px >= tp1 * 0.995:
            for o in ours(tpsl_orders(op["symbol"]), op):      # liberta as moedas presas nos stops
                try:
                    cancel(op["symbol"], o)
                except ExecError as e:
                    op.setdefault("avisos", []).append(f"cancelar: {str(e)[:80]}")
            time.sleep(1)
            q1 = min(float(p0.get("qty") or 0), max(0.0, held(wallet(), op["asset"]) - nucleo_q))
            try:
                oid = sell_all(op["symbol"], q1, inst, f"{_tag(req['op'])}-tp1")
                avg, sold = fills(oid, op["symbol"], op["asset"], side="Sell") if oid else (None, 0.0)
            except ExecError as e:
                avg, sold = None, 0.0
                op.setdefault("avisos", []).append(f"venda TP1: {str(e)[:80]}")
            if sold:
                p0["vendida"] = {"preco": avg, "qty": sold, "t": now}
                op["qty"] = max(0.0, (op.get("qty") or 0) - sold)
                send(f"💰 <b>{op['asset']}: TP1 vendido pelo programa</b> — {sold:.6g} {op['asset']} a {avg:.6g} "
                     f"(entrada {op['entrada']:.6g}, {((avg / op['entrada']) - 1) * 100:+.1f}%). "
                     "A Bybit não tinha aceitado o objetivo anexado.", html=True)
            else:
                send(f"⚠️ {op['asset']}: não consegui vender a parte do TP1. Ponho na mesma o stop na entrada.")
        have = -1                                                # segue para o stop na entrada
    if len(partes) > 1 and have > (op.get("qty") or 0) - 0.5 * (partes[0].get("qty") or 0):
        if not op.get("be_pendente"):
            send(f"⏳ {op['asset']}: o sinal viu o TP1, mas na Bybit a parte do TP1 ainda não vendeu. "
                 "Mantenho a ordem do TP1 e o stop original; subo o stop para a entrada assim que vender.")
        op["be_pendente"] = True
        return "à espera da venda do TP1 na Bybit"
    op["be_pendente"] = False
    new = float(fmt(op["entrada"] * 1.001, inst["tick"]))      # entrada + comissao
    olds = ours(tpsl_orders(op["symbol"]), op)
    if any(float(o.get("triggerPrice") or 0) >= new * 0.999 for o in olds):
        return "stop já na entrada"
    moved = 0
    for o in olds:                          # 1) alterar o gatilho (stop separado)
        trig = float(o.get("triggerPrice") or 0)
        if trig and not float(o.get("stopLoss") or 0) and trig < new:
            try:
                post("/v5/order/amend", {"category": "spot", "symbol": op["symbol"],
                                         "orderId": o["orderId"], "triggerPrice": fmt(new, inst["tick"])})
                moved += 1
                continue
            except ExecError as e:
                op.setdefault("avisos", []).append(f"alterar stop: {str(e)[:80]}")
        try:                                # 2) cancelar e criar um stop novo
            cancel(op["symbol"], o)
        except ExecError as e:
            op.setdefault("avisos", []).append(f"cancelar: {str(e)[:80]}")
    if moved < len(olds) or not olds:
        time.sleep(1)
        have = held(wallet(), op["asset"])
        qty = floor_to(min(have, op["qty"]), inst["base_step"])
        if qty > 0:
            try:
                sid = stop_order(op["symbol"], qty, new, inst, f"{_tag(req['op'])}-be")
                for p in op.get("partes") or []:
                    p.update(stopId=sid, filho=sid, anexo=False)
                moved += 1
            except ExecError as e:
                op["stop_erro"] = str(e)[:120]
                send(f"⚠️ {op['asset']}: TP1 atingido, mas não consegui pôr o stop na entrada "
                     f"({str(e)[:60]}). Põe-no à mão a {new:.6g}; o programa vende se o preço voltar à entrada.")
                return "erro"
    op["stop"] = new
    send(f"🔒 {op['asset']}: TP1 atingido. O stop subiu para a entrada ({new:.6g}) na Bybit — "
         "esta operação já não pode dar perda. O objetivo final é vendido pela Bybit ou pelo programa.")
    return "ok"


def do_close(state, req, ex, now, send, why="saída do plano"):
    op = ex["ops"].get(req["op"]) or {}
    if op.get("status") != "aberta":
        return "sem operação aberta do programa"
    if op.get("lado") == "SHORT":
        return close_short(state, req, ex, now, send, why)
    inst = instrument(op["symbol"])
    for o in ours(tpsl_orders(op["symbol"]), op):
        try:
            cancel(op["symbol"], o)
        except ExecError as e:
            op.setdefault("avisos", []).append(f"cancelar: {str(e)[:80]}")
    time.sleep(1)
    # moedas ja vendidas desde a compra (objetivos atingidos pela Bybit)
    try:
        r = get("/v5/execution/list", {"category": "spot", "symbol": op["symbol"],
                                       "startTime": int(op["criado"] * 1000), "limit": 100})
        sold_tp = sum(float(e["execQty"]) for e in r.get("list") or [] if e.get("side") == "Sell")
    except ExecError:
        sold_tp = 0.0
    nucleo_q = float(((ex.get("nucleo") or {}).get(op["asset"]) or {}).get("qty") or 0)
    have = max(0.0, held(wallet(), op["asset"]) - nucleo_q)      # nunca vende o nucleo
    qty = max(0.0, min(have, op["qty"] - sold_tp))
    oid = sell_all(op["symbol"], qty, inst, f"{_tag(req['op'])}-f")
    op.update(status="fechada", fechado=now, motivo=why)
    if op.get("emprestado"):                 # a venda abate a divida; confirma
        try:
            time.sleep(2)
            d = usdc_debt(wallet())
            if d > 0:
                repay_usdc(min(d, op["emprestado"]))
                op["pago"] = round(min(d, op["emprestado"]), 4)
        except ExecError as e:
            op.setdefault("avisos", []).append(f"pagamento: {str(e)[:80]}")
    if oid:
        avg, q = fills(oid, op["symbol"], op["asset"], side="Sell")
        op["saida"] = avg
        send(f"🏁 {op['asset']}: {why}. Vendi {q:.6g} a {avg:.6g} e cancelei as ordens abertas.")
    else:
        send(f"🏁 {op['asset']}: {why}. Já não havia moedas do programa para vender; "
             "cancelei as ordens abertas.")
    return "ok"


def do_stop_all(state, req, ex, now, send):
    n = 0
    for k, op in list(ex["ops"].items()):
        if op.get("status") == "aberta":
            do_close(state, {"op": k}, ex, now, send, why="paragem pedida (/parar)")
            n += 1
    if not n:
        send("⛔ /parar: não há operações abertas pelo programa.")
    return "ok"


def do_test(state, req, ex, now, send):
    """Prova real e pequena: compra ate 5 USDC de BTC com TP/SL anexados,
    confirma a ordem de protecao na Bybit, cancela-a e vende tudo (o mesmo
    caminho de uma saida do programa). Regista cada passo."""
    sym, steps = "BTCUSDC", []
    inst = instrument(sym)
    px = last_price(sym)
    free = usdc_free(wallet())
    q = min(TEST_USDC, round(free * 0.9, 2))          # o mais pequeno possivel
    q = max(q, round(inst["min_amt"] * 1.1, 2))
    if free < q:
        steps.append(f"ERRO: USDC livre ({free:.2f}) abaixo do mínimo da Bybit para BTC ({inst['min_amt']:g})")
        ex["teste"] = {"t": now, "passos": steps}
        send("🧪 Teste de execução não feito: " + steps[-1])
        return "sem saldo"
    try:
        oid, attached = place_part(sym, q, px * 1.05, px * 0.95, inst, f"teste-{now}")
        steps.append(f"compra {q:.2f} USDC: ok (TP/SL anexados: {'sim' if attached else 'não — ' + str(LAST_ATTACH_ERR)})")
        avg, qty = fills(oid, sym, "BTC")
        steps.append(f"executada a {avg:.2f}, {qty:.8f} BTC líquidos")
        od = []
        for _ in range(8):                   # a protecao aparece segundos depois
            time.sleep(2)
            od = [o for o in tpsl_orders(sym) if float(o.get("createdTime") or 0) >= (now - 5) * 1000]
            if od:
                break
        steps.append(f"ordens TP/SL encontradas: {len(od)} "
                     + "; ".join(f"{o.get('_flt')} trig={o.get('triggerPrice')} "
                                 f"tp={o.get('takeProfit')} sl={o.get('stopLoss')} qty={o.get('qty')}"
                                 for o in od))
        if not attached:
            sid = stop_order(sym, qty, px * 0.95, inst, f"teste-s{now}")
            steps.append(f"stop separado: {sid}")
            od = [o for o in tpsl_orders(sym) if float(o.get("createdTime") or 0) >= (now - 5) * 1000]
        for o in od:
            try:
                cancel(sym, o)
                steps.append(f"cancelar {o['orderId'][-6:]}: ok")
            except ExecError as e:
                steps.append(f"cancelar: ERRO {e}")
        time.sleep(1)
        sid = sell_all(sym, min(qty, held(wallet(), "BTC")), inst, f"teste-v{now}")
        if sid:
            a2, q2 = fills(sid, sym, "BTC", side="Sell")
            steps.append(f"venda: {q2:.8f} BTC a {a2:.2f} (resultado do teste ≈ {(a2 - avg) * q2 - q * 0.002:+.3f} USDC)")
    except ExecError as e:
        steps.append(f"ERRO: {e}")
    ex["teste"] = {"t": now, "passos": steps}
    send(f"🧪 <b>Teste de execução (BTC, {q:.2f} USDC)</b>\n" + "\n".join(f"• {s}" for s in steps), html=True)
    return "ok"


def do_diag(state, req, ex, now, send):
    """Sem custo: ordens limite de compra muito abaixo do preco (nunca
    executam) com TP/SL anexados, em varias formas; regista o que a Bybit
    aceita e cancela tudo logo a seguir."""
    sym, out = "BTCUSDC", []
    inst = instrument(sym)
    px = last_price(sym)
    lim = px * 0.5
    qty = max(inst["min_amt"] * 1.2 / lim, float(inst["base_step"]))
    common = {"category": "spot", "symbol": sym, "side": "Buy", "orderType": "Limit",
              "qty": fmt(qty * 1.0001, inst["base_step"]), "price": fmt(lim, inst["tick"]),
              "timeInForce": "GTC"}
    variants = {
        "limite_tp_sl_mercado": dict(takeProfit=fmt(px * 0.6, inst["tick"]), stopLoss=fmt(px * 0.45, inst["tick"]),
                                     tpOrderType="Market", slOrderType="Market"),
        "limite_tp_sl_simples": dict(takeProfit=fmt(px * 0.6, inst["tick"]), stopLoss=fmt(px * 0.45, inst["tick"])),
        "limite_so_sl": dict(stopLoss=fmt(px * 0.45, inst["tick"])),
    }
    for k, extra in variants.items():
        try:
            r = post("/v5/order/create", dict(common, orderLinkId=f"{LINK}d{k[:8]}{now % 100000}", **extra))
            out.append(f"{k}: ACEITE")
            try:
                post("/v5/order/cancel", {"category": "spot", "symbol": sym, "orderId": r["orderId"]})
                out.append(f"{k}: cancelada")
            except ExecError as e:
                out.append(f"{k}: cancelar ERRO {e}")
        except ExecError as e:
            out.append(f"{k}: recusada — {e}")
    ex["diag"] = {"t": now, "min_amt": inst["min_amt"], "passos": out}
    return "ok"


def do_clean(state, req, ex, now, send):
    """Limpa o teste: mostra TODAS as ordens abertas em BTCUSDC criadas pelo
    teste (desde o inicio do ultimo teste), cancela-as e vende o BTC do teste."""
    sym, out = "BTCUSDC", []
    t0 = ((ex.get("teste") or {}).get("t") or now) - 10
    inst = instrument(sym)
    seen = {}
    for flt in (None, "Order", "tpslOrder", "StopOrder"):
        prm = {"category": "spot", "symbol": sym, "limit": 50}
        if flt:
            prm["orderFilter"] = flt
        try:
            for o in get("/v5/order/realtime", prm).get("list") or []:
                seen[o["orderId"]] = dict(o, _flt=flt or o.get("orderFilter") or "Order")
        except ExecError as e:
            out.append(f"listar {flt}: ERRO {e}")
    mine = [o for o in seen.values() if float(o.get("createdTime") or 0) >= t0 * 1000]
    for o in mine:
        out.append(f"ordem {o['orderId'][-6:]} filtro={o.get('orderFilter') or o['_flt']} tipo={o.get('stopOrderType')} "
                   f"lado={o.get('side')} trig={o.get('triggerPrice')} qty={o.get('qty')} estado={o.get('orderStatus')}")
        try:
            post("/v5/order/cancel", {"category": "spot", "symbol": sym, "orderId": o["orderId"],
                                      "orderFilter": o.get("orderFilter") or o["_flt"]})
            out.append("  cancelada")
        except ExecError as e:
            out.append(f"  cancelar ERRO {e}")
    out.append(f"ordens anteriores do Rui em BTCUSDC (não tocadas): {len(seen) - len(mine)}")
    time.sleep(1)
    q = 0.0000409
    try:
        sid = sell_all(sym, min(q, held(wallet(), "BTC")), inst, f"limpa{now % 100000}")
        if sid:
            a, qq = fills(sid, sym, "BTC", side="Sell")
            out.append(f"venda: {qq:.8f} BTC a {a:.2f}")
    except ExecError as e:
        out.append(f"venda: ERRO {e}")
    ex["limpeza"] = {"t": now, "passos": out}
    return "ok"


def do_clean_short(state, req, ex, now, send):
    """Cancela as ordens de COMPRA em BTCUSDC criadas desde o teste da venda a
    descoberto (as do Rui, anteriores, nao sao tocadas)."""
    sym, out = "BTCUSDC", []
    t0 = ((ex.get("teste_short") or {}).get("t") or now) - 60
    for o in tpsl_orders(sym):
        if o.get("side") != "Buy" or float(o.get("createdTime") or 0) < t0 * 1000:
            continue
        out.append(f"ordem {o['orderId'][-6:]} tipo={o.get('stopOrderType')} tp={o.get('takeProfit')} "
                   f"sl={o.get('stopLoss')} qty={o.get('qty')}")
        try:
            cancel(sym, o)
            out.append("  cancelada")
        except ExecError as e:
            out.append(f"  cancelar ERRO {e}")
    if not out:
        out.append("nenhuma ordem do teste por cancelar")
    ex["limpeza_short"] = {"t": now, "passos": out}
    send("🧹 Limpeza do teste da venda a descoberto:\n" + "\n".join(out))
    return "ok"


def do_test2(state, req, ex, now, send):
    """Prova do 'stop para a entrada': a Bybit UE nao deixa alterar a ordem
    TP/SL anexada. Testa substitui-la por duas ordens condicionais (objetivo
    e stop) sobre as mesmas moedas, depois cancela e vende tudo."""
    sym, steps = "BTCUSDC", []
    inst = instrument(sym)
    px = last_price(sym)
    q = max(min(TEST_USDC, round(usdc_free(wallet()) * 0.9, 2)), round(inst["min_amt"] * 1.1, 2))
    try:
        oid, attached = place_part(sym, q, px * 1.05, px * 0.95, inst, f"t2-{now}")
        avg, qty = fills(oid, sym, "BTC")
        steps.append(f"compra {q:.2f} USDC a {avg:.2f} (anexo: {'sim' if attached else 'não'})")
        od = []
        for _ in range(8):
            time.sleep(2)
            od = [o for o in tpsl_orders(sym) if float(o.get("createdTime") or 0) >= (now - 5) * 1000]
            if od:
                break
        for o in od:
            cancel(sym, o)
            steps.append(f"cancelar a proteção anexada ({o.get('stopOrderType')}): ok")
        time.sleep(1)
        ids = []
        for nome, trig in (("objetivo", px * 1.05), ("stop na entrada", avg)):
            try:
                ids.append(stop_order(sym, qty, trig, inst, f"t2{nome[:3]}{now % 100000}"))
                steps.append(f"{nome} condicional: ACEITE")
            except ExecError as e:
                steps.append(f"{nome} condicional: recusada — {e}")
        time.sleep(1)
        for o in tpsl_orders(sym):
            if o["orderId"] in ids:
                cancel(sym, o)
                steps.append(f"cancelar {o['orderId'][-6:]}: ok")
        time.sleep(1)
        sid = sell_all(sym, min(qty, held(wallet(), "BTC")), inst, f"t2v{now % 100000}")
        if sid:
            a2, q2 = fills(sid, sym, "BTC", side="Sell")
            steps.append(f"venda: {q2:.8f} BTC a {a2:.2f}")
    except ExecError as e:
        steps.append(f"ERRO: {e}")
    ex["teste2"] = {"t": now, "passos": steps}
    return "ok"


def do_test_margin(state, req, ex, now, send):
    """Prova minima da margem: compra BTC com ~2 USDC emprestados (TP/SL
    anexados), cancela a protecao, vende e confirma que a divida criada
    pelo teste fica paga a 100%."""
    sym, steps = "BTCUSDC", []
    inst = instrument(sym)
    try:
        st = get("/v5/spot-margin-trade/state")
        steps.append(f"margem spot: modo={st.get('spotMarginMode')} alavancagem={st.get('spotLeverage')}")
    except ExecError as e:
        steps.append(f"estado da margem: ERRO {e}")
    w0 = wallet()
    d0, free = usdc_debt(w0), usdc_free(w0)
    steps.append(f"antes: USDC livre {free:.2f}, dívida {d0:.4f} — {usdc_fields(w0)}")
    q = round(max(free, 0) + 2.0, 2)
    try:
        oid, attached = place_part(sym, q, last_price(sym) * 1.05, last_price(sym) * 0.95, inst,
                                   f"tm-{now}", margin=True)
        avg, qty = fills(oid, sym, "BTC")
        steps.append(f"compra com margem {q:.2f} USDC a {avg:.2f}, {qty:.8f} BTC (anexo: "
                     f"{'sim' if attached else 'não — ' + str(LAST_ATTACH_ERR)})")
        w1 = wallet()
        steps.append(f"depois da compra: dívida {usdc_debt(w1):.4f} — {usdc_fields(w1)}")
        od = []
        for _ in range(8):
            time.sleep(2)
            od = [o for o in tpsl_orders(sym) if float(o.get("createdTime") or 0) >= (now - 5) * 1000]
            if od:
                break
        for o in od:
            cancel(sym, o)
            steps.append(f"cancelar proteção ({o.get('stopOrderType')}): ok")
        time.sleep(1)
        sid = sell_all(sym, min(qty, held(wallet(), "BTC")), inst, f"tmv{now % 100000}")
        if sid:
            a2, q2 = fills(sid, sym, "BTC", side="Sell")
            steps.append(f"venda: {q2:.8f} BTC a {a2:.2f}")
        time.sleep(2)
        w2 = wallet()
        d2 = usdc_debt(w2)
        steps.append(f"depois da venda: dívida {d2:.4f} — {usdc_fields(w2)}")
        if d2 > d0 + 1e-6:
            try:
                repay_usdc(d2 - d0)
                steps.append(f"pagamento de {d2 - d0:.4f} USDC: ok")
            except ExecError as e:
                steps.append(f"pagamento: ERRO {e}")
            time.sleep(2)
            d3 = usdc_debt(wallet())
            steps.append(f"dívida final {d3:.4f} (antes do teste {d0:.4f})")
            if d3 > d0 + 0.01:
                steps.append("ERRO: ficou dívida do teste por pagar")
        else:
            steps.append("a Bybit abateu a dívida sozinha com o USDC da venda")
    except ExecError as e:
        steps.append(f"ERRO: {e}")
    ex["teste_margem"] = {"t": now, "passos": steps}
    send("🧪 <b>Teste de margem</b>\n" + "\n".join(f"• {x}" for x in steps[-6:]), html=True)
    return "ok"


def do_test_lev(state, req, ex, now, send):
    """Sem custo: le o teto de alavancagem da conta e volta a grava-lo com o
    mesmo valor, para provar que a chave o pode alterar."""
    try:
        cur = get("/v5/spot-margin-trade/state").get("spotLeverage") or "2"
        post("/v5/spot-margin-trade/set-leverage", {"leverage": str(int(float(cur)))})
        out = f"teto atual {cur}x; a chave pode alterá-lo: sim"
    except ExecError as e:
        out = f"ERRO: {e}"
    ex["teste_alav"] = {"t": now, "res": out}
    return "ok"


def do_orders(state, req, ex, now, send):
    """Diagnostico sem custo: como a Bybit devolve as ordens abertas das
    operacoes em curso (para a leitura da conta encontrar os stops)."""
    out = []
    for sym in ("SOLUSDC", "XRPUSDC", None):
        for flt in (None, "Order", "tpslOrder", "StopOrder"):
            prm = {"category": "spot", "limit": 50}
            if sym:
                prm["symbol"] = sym
            if flt:
                prm["orderFilter"] = flt
            try:
                L = get("/v5/order/realtime", prm).get("list") or []
                out.append(f"{sym or 'todos'}/{flt or '-'}: {len(L)} " + "; ".join(
                    f"{o.get('symbol')} {o.get('side')} f={o.get('orderFilter')} t={o.get('stopOrderType')} "
                    f"trig={o.get('triggerPrice')} tp={o.get('takeProfit')} sl={o.get('stopLoss')} qty={o.get('qty')} "
                    f"lev={o.get('isLeverage')}" for o in L[:4]))
            except ExecError as e:
                out.append(f"{sym or 'todos'}/{flt or '-'}: ERRO {e}")
    ex["ordens"] = {"t": now, "res": out}
    return "ok"


# ---------- nucleo da carteira (Rui, 2026-10-20; engine/nucleo.py) ----------
# Spot, sem alavancagem e sem emprestimo: compra e vende a propria moeda.

def do_nucleo_reforcar(state, req, ex, now, send):
    """Reforco do nucleo depois de um deposito: compra a diferenca para a sua
    parte do capital e junta a posicao (preco medio)."""
    a = req["op"].split("-", 1)[1]
    pos = (ex.get("nucleo") or {}).get(a)
    if not pos or pos.get("verificar"):
        return "sem posição no núcleo"
    return do_nucleo_comprar(state, req, ex, now, send, junta=pos)


def do_nucleo_comprar(state, req, ex, now, send, junta=None):
    a = req["op"].split("-", 1)[1]
    nuc = ex.setdefault("nucleo", {})
    if nuc.get(a) and junta is None:
        return "já está no núcleo"
    plano = (((state.get("nucleo") or {}).get("plano") or {}).get(a)) or {}
    usdc = float(plano.get("comprar_usdc") or 0)
    if not plano.get("acima") or usdc <= 0:
        return "sem plano de compra"
    sym = f"{a}USDC"
    inst = instrument(sym)
    free = usdc_free(wallet())
    usdc = min(usdc, free * 0.98)
    if usdc < max(inst["min_amt"], 5.0):
        send(f"⚠️ Núcleo: não comprei {a}, USDC livre insuficiente ({free:.2f}).")
        return "USDC insuficiente"
    px = last_price(sym)
    lim = float(fmt(px * (1 + LIMIT_SLIP), inst["tick"]))
    qty = floor_to(usdc / lim, inst["base_step"])
    r = post("/v5/order/create", {"category": "spot", "symbol": sym, "side": "Buy", "orderType": "Limit",
                                  "timeInForce": "IOC", "price": fmt(lim, inst["tick"]),
                                  "qty": fmt(qty, inst["base_step"]),
                                  "orderLinkId": f"{LINK}nb{a}{now % 1000000}"[:36]})
    try:
        avg, q = fills(r["orderId"], sym, a)
    except ExecError as e:
        send(f"🚨 Núcleo: a compra de {a} foi enviada mas não confirmei a execução ({str(e)[:60]}). Verifica na app.")
        nuc[a] = {"qty": 0.0, "entrada": px, "t": now, "verificar": True}
        return "sem execução confirmada"
    ex.setdefault("nucleo_log", []).append({"moeda": a, "acao": "reforço" if junta else "compra", "usdc": round(avg * q, 2),
                                            "preco": avg, "t": now})
    ex["nucleo_log"] = ex["nucleo_log"][-60:]
    if junta:
        q0, e0 = float(junta.get("qty") or 0), float(junta.get("entrada") or avg)
        tq = q0 + q
        nuc[a] = {"qty": tq, "entrada": round((q0 * e0 + q * avg) / tq, 8), "usdc": round((q0 * e0 + q * avg), 2), "t": junta.get("t") or now}
        send(f"🧱 <b>Núcleo: reforcei {a}</b> — mais {avg * q:.2f} USDC a {avg:.6g}, para voltar à sua parte do capital "
             f"(agora {tq:.6g} {a}). Spot, sem alavancagem.", html=True)
        return "ok"
    nuc[a] = {"qty": q, "entrada": avg, "usdc": round(avg * q, 2), "t": now}
    send(f"🧱 <b>Núcleo: comprei {a}</b> — {avg * q:.2f} USDC a {avg:.6g} ({q:.6g} {a}). Spot, sem alavancagem. "
         f"Fica enquanto o fecho diário estiver acima da média de 200 dias ({plano.get('media'):.6g}).", html=True)
    return "ok"


def do_nucleo_vender(state, req, ex, now, send):
    a = req["op"].split("-", 1)[1]
    nuc = ex.setdefault("nucleo", {})
    pos = nuc.get(a)
    if not pos:
        return "sem posição no núcleo"
    sym = f"{a}USDC"
    inst = instrument(sym)
    q = min(held(wallet(), a), pos.get("qty") or 0)
    oid = sell_all(sym, q, inst, f"ns{a}{now % 1000000}")
    avg, sold = (fills(oid, sym, a, side="Sell") if oid else (None, 0.0))
    pnl = round(sold * (avg - pos["entrada"]), 2) if avg else None
    ex.setdefault("nucleo_hist", []).append({"moeda": a, "entrada": pos["entrada"], "saida": avg, "qty": sold,
                                             "t_entrada": pos.get("t"), "t_saida": now, "pnl_usdc": pnl})
    ex["nucleo_hist"] = ex["nucleo_hist"][-100:]
    nuc.pop(a, None)
    send(f"🧱 Núcleo: vendi {a} para USDC — o fecho diário ficou abaixo da média de 200 dias. "
         + (f"Venda a {avg:.6g}, resultado {pnl:+.2f} USDC." if avg else "Já não havia moedas para vender."))
    return "ok"


ACTIONS = {"vender": do_short, "teste_short": do_test_short, "limpar_short": do_clean_short, "ordens": do_orders, "teste_alav": do_test_lev, "teste_margem": do_test_margin, "teste2": do_test2, "limpar": do_clean, "diag": do_diag, "comprar": do_buy, "breakeven": do_breakeven, "fechar": do_close,
           "parar": do_stop_all, "teste": do_test,
           "nucleo_comprar": do_nucleo_comprar, "nucleo_vender": do_nucleo_vender,
           "nucleo_reforcar": do_nucleo_reforcar}


def main(state_path, ex_in, out):
    from . import alerts
    now = int(time.time())
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    try:
        ex = json.load(open(ex_in))
    except Exception:
        ex = {}
    ex.setdefault("ops", {})
    ex.setdefault("feitos", [])

    def send(text, html=False):
        try:
            alerts.send(text, html=html)
        except Exception as e:
            print("TELEGRAM FALHOU", e)

    ex["t"] = now
    if not configured():
        ex.update(pronto=False, chave="sem chave de negociação (BYBIT_TRADE_KEY)")
    else:
        try:
            info = get("/v5/user/query-api")
            ok, why = key_ok(info)
            # so nomes de permissoes e se ha IP (nada secreto)
            ex["permissoes"] = info.get("permissions")
            ex["ips_definidos"] = len([x for x in info.get("ips") or [] if x and x != "*"])
            ex["expira"] = info.get("expiredAt")             # validade da chave (aviso 14 dias antes)
        except ExecError as e:
            ok, why = False, str(e)[:120]
        ex.update(pronto=ok, chave=why)
    reqs = [r for r in state.get("exec_req") or [] if r.get("id") not in ex["feitos"]]
    forced = os.environ.get("EXEC_ACAO", "").strip()
    if forced:                                   # pedido manual (teste)
        acao, _, op = forced.partition(":")      # (23/10) "vender:<id>" = o botao Executar pedido pelo Rui
        acao = acao.strip()
        if acao in ("comprar", "vender") and op.strip():
            reqs.append({"id": f"{acao}-{op.strip()}-manual-{now}", "acao": acao, "op": op.strip(), "t": now})
        else:
            reqs.append({"id": f"manual-{forced}-{now}", "acao": forced, "op": "", "t": now})
    for r in reqs:
        res = "ignorado"
        if not ex["pronto"]:
            if r.get("acao") in ("comprar", "vender", "teste", "parar"):
                send(f"⚠️ Execução desligada: {ex['chave']}. Nada foi feito.")
            res = "chave não pronta"
        elif r.get("acao") in ("comprar", "vender") and now - (r.get("t") or now) > 3600:
            res = "pedido demasiado antigo"
        elif r.get("acao") in ACTIONS:
            try:
                res = ACTIONS[r["acao"]](state, r, ex, now, send)
            except ExecError as e:
                res = f"erro: {e}"
                send(f"⚠️ Erro na Bybit ao {r['acao']} {r.get('op', '')[:30]}: {str(e)[:120]}")
            except Exception as e:           # erro inesperado: o pedido fica feito, nunca se repete
                res = f"erro inesperado: {type(e).__name__}: {e}"
                send(f"🚨 Erro inesperado ao {r['acao']} {r.get('op', '')[:30]}: {type(e).__name__}. "
                     "O pedido não será repetido; confirma na app da Bybit se houve compra e se tem stop.")
        ex["feitos"] = (ex["feitos"] + [r["id"]])[-300:]
        ex.setdefault("log", []).append({"t": now, "id": r["id"], "acao": r.get("acao"), "res": str(res)[:160]})
        ex["log"] = ex["log"][-100:]
    with open(out, "w") as f:
        json.dump(ex, f, indent=1, ensure_ascii=False)
    print(f"pronto={ex['pronto']} ({ex['chave']}) pedidos={len(reqs)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
