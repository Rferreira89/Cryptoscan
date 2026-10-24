"""Leitura da conta real na Bybit UE (chave SO DE LEITURA).

Usa BYBIT_API_KEY e BYBIT_API_SECRET (segredos do GitHub, nunca no codigo).
So faz pedidos GET: saldo, ordens abertas e execucoes. Antes de usar a
chave confirma na propria Bybit que ela e so de leitura; se tiver
permissoes de negociacao ou de levantamentos, o programa recusa-se a usa-la.

Nada daqui altera o tamanho das posicoes nem o risco: so informa
(stop colocado ou nao, entrada detetada, saldo em USDC).

O resultado publicado (scan.json) e minimo de proposito, porque o
repositorio e publico: so o saldo livre em USDC, o valor total (que passa a ser o capital) e,
por operacao aberta,
se ha moedas, se ha stop e a que preco. Nunca a carteira inteira.

Uso de teste: python -m engine.account <ficheiro_saida.json> [state.json]
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bybit.eu"
RECV = "10000"
TIMEOUT = 15


class AccountError(Exception):
    pass


def configured():
    return bool(os.environ.get("BYBIT_API_KEY", "").strip()
                and os.environ.get("BYBIT_API_SECRET", "").strip())


def sign(secret, ts, key, recv, query):
    msg = f"{ts}{key}{recv}{query}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def get(path, params=None):
    key = os.environ["BYBIT_API_KEY"].strip()
    secret = os.environ["BYBIT_API_SECRET"].strip()
    query = urllib.parse.urlencode(sorted((params or {}).items()))
    ts = str(int(time.time() * 1000))
    req = urllib.request.Request(
        f"{BASE}{path}" + (f"?{query}" if query else ""),
        headers={"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts,
                 "X-BAPI-RECV-WINDOW": RECV,
                 "X-BAPI-SIGN": sign(secret, ts, key, RECV, query),
                 "User-Agent": "cryptoscan"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode()[:120]
        except Exception:
            msg = ""
        raise AccountError(f"{path}: HTTP {e.code} {msg}") from None
    except Exception as e:  # rede, JSON
        raise AccountError(f"{path}: {type(e).__name__}") from None
    if body.get("retCode") != 0:
        raise AccountError(f"{path}: {body.get('retCode')} "
                           f"{str(body.get('retMsg'))[:80]}")
    return body.get("result") or {}


# ---------- interpretacao (funcoes puras, testadas) ----------

def read_only(info):
    """True so se a Bybit diz que a chave e so de leitura. Na duvida, False."""
    try:
        return int(info.get("readOnly")) == 1
    except (TypeError, ValueError):
        return False


def coins(wallet):
    """{moeda: quantidade} a partir de wallet-balance."""
    out = {}
    for acc in wallet.get("list") or []:
        for c in acc.get("coin") or []:
            try:
                q = float(c.get("walletBalance") or 0)
            except (TypeError, ValueError):
                continue
            if q:
                out[c.get("coin", "").upper()] = out.get(
                    c.get("coin", "").upper(), 0.0) + q
    return out


def debts(wallet):
    """{moeda: divida} da margem (spotBorrow/borrowAmount). (24/10) Um short em
    margem spot deixa a moeda com saldo negativo ou em divida, nunca positivo."""
    out = {}
    for acc in wallet.get("list") or []:
        for c in acc.get("coin") or []:
            for k in ("spotBorrow", "borrowAmount"):
                try:
                    v = float(c.get(k) or 0)
                except (TypeError, ValueError):
                    v = 0.0
                if v > 0:
                    out[c.get("coin", "").upper()] = v
                    break
    return out


def usdc_free(wallet):
    for acc in wallet.get("list") or []:
        for c in acc.get("coin") or []:
            if c.get("coin") == "USDC":
                for k in ("availableToWithdraw", "free", "walletBalance"):
                    try:
                        v = float(c.get(k) or "")
                        return round(v, 2)
                    except (TypeError, ValueError):
                        continue
    return None


def equity(wallet):
    """Valor total da conta em USD (totalEquity ou soma de usdValue)."""
    tot, seen = 0.0, False
    for acc in wallet.get("list") or []:
        try:
            v = float(acc.get("totalEquity") or "")
            tot, seen = tot + v, True
            continue
        except (TypeError, ValueError):
            pass
        for c in acc.get("coin") or []:
            try:
                tot += float(c.get("usdValue") or "")
                seen = True
            except (TypeError, ValueError):
                continue
    return round(tot, 2) if seen else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def stop_for(orders, symbol, side="LONG"):
    """Preco do stop colocado para uma operacao, ou None.

    Num LONG conta qualquer ordem de VENDA com preco de disparo (stop,
    stop-limit ou TP/SL). O preco devolvido e o disparo mais alto abaixo
    do qual a posicao fica protegida."""
    want = "Sell" if side == "LONG" else "Buy"
    # a Bybit UE guarda o TP/SL anexado a uma compra como uma ordem
    # BidirectionalTpslOrder com triggerPrice 0 e o stop no campo stopLoss
    trig = [_f(o.get("triggerPrice")) or _f(o.get("stopLoss")) for o in orders
            if o.get("symbol") == symbol and o.get("side") == want
            and (_f(o.get("triggerPrice")) > 0 or _f(o.get("stopLoss")) > 0)]
    if not trig:
        return None
    return max(trig) if side == "LONG" else min(trig)


def tp_for(orders, symbol, side, entry):
    """Ordens de objetivo (TP) de uma operacao: TP anexado (takeProfit) ou
    ordens de venda (LONG) / compra (SHORT) pelo menos 1% para o lado do lucro."""
    if not entry:
        return 0
    want = "Sell" if side == "LONG" else "Buy"
    ok = lambda px: px > entry * 1.01 if side == "LONG" else 0 < px < entry * 0.99
    n = 0
    for o in orders:
        if o.get("symbol") != symbol or o.get("side") != want:
            continue
        tp, trig, px = _f(o.get("takeProfit")), _f(o.get("triggerPrice")), _f(o.get("price"))
        if (tp and ok(tp)) or (trig and ok(trig)) or (not trig and px and ok(px)):
            n += 1
    return n


def fill_for(execs, symbol, since, side="LONG"):
    """Preco medio e quantidade das compras (LONG) desde 'since' (s)."""
    want = "Buy" if side == "LONG" else "Sell"
    q = v = 0.0
    for e in execs:
        if e.get("symbol") != symbol or e.get("side") != want:
            continue
        if _f(e.get("execTime")) / 1000 < since:
            continue
        q += _f(e.get("execQty"))
        v += _f(e.get("execQty")) * _f(e.get("execPrice"))
    return (v / q, q) if q > 0 else None


def symbol_of(rec):
    base, _, quote = (rec.get("pair") or f"{rec.get('asset')}/USDC").partition("/")
    return f"{base}{quote or 'USDC'}".upper()


def check_trades(ledger, held, orders, execs, now, debt=None):
    """Para cada operacao 4H aberta: moedas na conta, stop, entrada vista.
    (24/10) Num short a posicao existe quando a moeda esta negativa ou em
    divida (antes 'held' so via saldo positivo e os alarmes de stop saltavam
    todos os shorts)."""
    debt = debt or {}
    out = []
    for r in ledger:
        if r.get("kind") != "4H" or r.get("status") != "OPEN":
            continue
        if r.get("executed") is False:
            continue
        side = "SHORT" if r.get("side") == "SHORT" else "LONG"
        sym = symbol_of(r)
        stop = stop_for(orders, sym, side)
        fill = fill_for(execs, sym, (r.get("issued_at") or now) - 600, side)
        row = {"id": r["id"], "asset": r["asset"], "symbol": sym,
               "held": (held.get(r["asset"].upper(), 0.0) > 0 if side == "LONG" else
                     held.get(r["asset"].upper(), 0.0) < 0 or debt.get(r["asset"].upper(), 0.0) > 0),
               "stop_found": stop is not None,
               "tp_n": tp_for(orders, sym, side, r.get("exec_price") or r.get("entry")),
               "stop_px": stop, "plan_stop": r.get("stop"),
               "fill_px": round(fill[0], 10) if fill else None}
        if stop is not None and r.get("stop"):
            row["stop_gap_pct"] = round((stop / r["stop"] - 1) * 100, 2)
        out.append(row)
    return out


# ---------- leitura completa ----------

def open_orders():
    """Todas as ordens spot abertas. A Bybit UE so devolve as TP/SL
    (BidirectionalTpslOrder) quando o pedido vai SEM orderFilter
    (confirmado a 2026-10-13 com as ordens da SOL e da XRP)."""
    seen = {}
    for flt in (None, "Order", "StopOrder", "tpslOrder"):
        prm = {"category": "spot", "limit": 50}
        if flt:
            prm["orderFilter"] = flt
        try:
            res = get("/v5/order/realtime", prm)
        except AccountError:
            continue
        for o in res.get("list") or []:
            seen[o.get("orderId") or id(o)] = o
    return list(seen.values())


def executions(symbols, since):
    out = []
    for s in sorted(set(symbols)):
        try:
            res = get("/v5/execution/list",
                      {"category": "spot", "symbol": s, "limit": 100,
                       "startTime": int(max(since, time.time() - 6.5 * 86400)
                                        * 1000)})
        except AccountError:
            continue
        out += res.get("list") or []
    return out


def real_results(led, execs, now, janela=6.5 * 86400):
    """Fase 1 da contra-auditoria (Rui, 20/10): o resultado REAL de cada
    operacao do programa, a partir das execucoes da Bybit (precos e comissoes
    efetivos), e nao do preco teorico do sinal. So os ultimos 6,5 dias (o
    limite da Bybit); o scanner guarda o que ja fechou no registo.
    Devolve {id: {compra_usdc, venda_usdc, comissoes_usdc, pnl_usdc, fechada, n}}.
    O juro de um short em margem nao aparece nas execucoes (fica de fora)."""
    rows = sorted((r for r in led or [] if r.get("kind") == "4H" and r.get("executed") is not False
                   and (janela is None or (r.get("issued_at") or 0) >= now - janela)),
                  key=lambda r: r.get("issued_at") or 0)
    out = {}
    for i, r in enumerate(rows):
        sym = symbol_of(r)
        t0 = (r.get("issued_at") or now) - 600
        t1 = (r.get("user_closed_at") or r.get("closed_at") or now) + 6 * 3600
        nxt = [x.get("issued_at") for x in rows[i + 1:] if symbol_of(x) == sym and x.get("issued_at")]
        if nxt:
            t1 = min(t1, nxt[0] - 600)
        short = r.get("side") == "SHORT"
        op_side, back_side = ("Sell", "Buy") if short else ("Buy", "Sell")
        q_in = v_in = q_out = v_out = fee_usdc = fee_base_q = 0.0
        n = 0
        for e in execs:
            if e.get("symbol") != sym:
                continue
            t = (_f(e.get("execTime")) or 0) / 1000
            if not t0 <= t <= t1:
                continue
            q, px, fee = _f(e.get("execQty")) or 0, _f(e.get("execPrice")) or 0, _f(e.get("execFee")) or 0
            base_fee = (e.get("feeCurrency") or "").upper() == (r.get("asset") or "").upper()
            if base_fee:
                fee_base_q += fee
            else:
                fee_usdc += fee
            if e.get("side") == op_side:
                q_in, v_in = q_in + q, v_in + q * px
            elif e.get("side") == back_side:
                q_out, v_out = q_out + q, v_out + q * px
            n += 1
        if not q_in:
            continue
        px_in = v_in / q_in
        net_in = q_in - (fee_base_q if not short else 0)
        fechada = q_out >= 0.98 * net_in
        if short:
            pnl = v_in - v_out - fee_usdc - fee_base_q * px_in
        else:
            pnl = v_out - v_in - fee_usdc     # comissao paga na moeda ja reduziu o que se vendeu
        out[r["id"]] = {"compra_usdc": round(v_in, 4), "venda_usdc": round(v_out, 4),
                        "comissoes_usdc": round(fee_usdc + fee_base_q * px_in, 4),
                        "pnl_usdc": round(pnl, 4) if fechada else None,
                        "fechada": fechada, "n": n, "preco_entrada": round(px_in, 10),
                        "preco_saida": round(v_out / q_out, 10) if q_out else None}
    return out


RECUPERAR_MAX = 5           # operacoes antigas recuperadas por leitura da conta


def executions_range(symbol, t0, t1):
    """Execucoes de um par entre t0 e t1 (s), em janelas de 7 dias (limite da Bybit)."""
    out, a = [], t0
    while a < t1:
        b = min(t1, a + 7 * 86400 - 60)
        try:
            res = get("/v5/execution/list", {"category": "spot", "symbol": symbol, "limit": 100,
                                             "startTime": int(a * 1000), "endTime": int(b * 1000)})
            out += res.get("list") or []
        except AccountError:
            pass
        a = b
    return out


def recuperar(led, now, maximo=RECUPERAR_MAX):
    """D1 da auditoria (Rui, 21/10): o resultado real das operacoes antigas
    (fechadas ha mais de 6,5 dias e ainda sem resultado da Bybit), lendo as
    execucoes da propria altura em janelas de 7 dias. Poucas de cada vez."""
    falta = [r for r in led or [] if r.get("kind") == "4H" and r.get("executed") is True
             and r.get("mode") == "REAL" and r.get("status") == "CLOSED" and r.get("real_r") is None
             and not r.get("real") and (r.get("issued_at") or 0) < now - 6.5 * 86400]
    falta = sorted(falta, key=lambda r: r.get("issued_at") or 0)[:maximo]
    out = {}
    for r in falta:
        t0 = (r.get("issued_at") or now) - 600
        t1 = (r.get("user_closed_at") or r.get("closed_at") or now) + 6 * 3600
        ex = executions_range(symbol_of(r), t0, t1)
        res = real_results([r], ex, now, janela=None)
        out[r["id"]] = res.get(r["id"]) or {"sem_dados": True}
    return out


def funding():
    """Saldos na conta Funding (onde caem os depositos na Bybit). O programa
    so negoceia com a Conta Unificada; o dinheiro aqui tem de ser transferido
    pelo Rui (a chave nao tem permissao de transferencias, de proposito).
    Devolve {moeda: quantidade} ou None se a chave nao puder ler."""
    try:
        res = get("/v5/asset/transfer/query-account-coins-balance", {"accountType": "FUND"})
    except AccountError:
        return None
    out = {}
    for c in res.get("balance") or []:
        try:
            q = float(c.get("walletBalance") or 0)
        except (TypeError, ValueError):
            continue
        if q > 0.01:
            out[c.get("coin")] = round(q, 4)
    return out


def _margem_ou_none():
    try:
        m = margem()
        return m or None
    except Exception as e:
        print("margem:", e)
        return None


def margem():
    """(22/10) Moedas com par em USDC que aceitam margem spot na Bybit UE (para vender a
    descoberto). A ICP de 22/10 foi recusada: 'Symbol is not supported on Margin Trading'."""
    d = get("/v5/market/instruments-info", {"category": "spot"})
    out = set()
    for x in d.get("list") or []:
        if x.get("quoteCoin") == "USDC" and str(x.get("marginTrading") or "none").lower() in ("both", "utaonly") \
                and x.get("status") == "Trading":
            out.add(x.get("baseCoin"))
    return sorted(out)


def snapshot(state, now=None):
    """Le a conta e devolve o resumo minimo para publicar. Nunca levanta:
    em caso de erro devolve {'ok': False, 'error': ...}."""
    now = now or time.time()
    if not configured():
        return {"ok": False, "error": "sem chave", "t": int(now)}
    try:
        info = get("/v5/user/query-api")
        if not read_only(info):
            return {"ok": False, "t": int(now),
                    "error": "a chave NÃO é só de leitura: não foi usada"}
        try:
            wallet = get("/v5/account/wallet-balance",
                         {"accountType": "UNIFIED"})
        except AccountError:
            wallet = get("/v5/account/wallet-balance", {"accountType": "SPOT"})
        held = coins(wallet)
        led = state.get("ledger", [])
        opened = [r for r in led if r.get("kind") == "4H"
                  and r.get("status") == "OPEN" and r.get("executed") is not False]
        orders = open_orders()
        since = min([r.get("issued_at") or now for r in opened] or [now])
        execs = executions([symbol_of(r) for r in opened], since - 600)
        try:                                 # resultado real (fase 1): ultimos 6,5 dias
            recent = [r for r in led if r.get("kind") == "4H" and r.get("executed") is not False
                      and (r.get("issued_at") or 0) >= now - 6.5 * 86400]
            reais = real_results(recent, executions([symbol_of(r) for r in recent],
                                                    now - 6.5 * 86400), now)
        except Exception as e:
            reais = {"erro": str(e)[:100]}
        try:                                 # D1 (21/10): as operacoes antigas, poucas de cada vez
            if isinstance(reais, dict) and "erro" not in reais:
                reais.update(recuperar(led, now))
        except Exception as e:
            print("recuperar:", e)
        return {"ok": True, "t": int(now), "usdc_free": usdc_free(wallet), "reais": reais,
                "equity": equity(wallet),
                "expires": info.get("expiredAt"),
                "fundo": funding(),
                "margem": _margem_ou_none(),
                "trades": check_trades(led, held, orders, execs, now, debts(wallet))}
    except AccountError as e:
        return {"ok": False, "error": str(e)[:120], "t": int(now)}


def main(out_path, state_path=None):
    state = {}
    if state_path and os.path.exists(state_path):
        state = json.load(open(state_path))
    snap = snapshot(state)
    with open(out_path, "w") as f:
        json.dump(snap, f, indent=1)
    print(json.dumps(snap, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
