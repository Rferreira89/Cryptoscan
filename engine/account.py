"""Leitura da conta real na Bybit UE (chave SO DE LEITURA).

Usa BYBIT_API_KEY e BYBIT_API_SECRET (segredos do GitHub, nunca no codigo).
So faz pedidos GET: saldo, ordens abertas e execucoes. Antes de usar a
chave confirma na propria Bybit que ela e so de leitura; se tiver
permissoes de negociacao ou de levantamentos, o programa recusa-se a usa-la.

Nada daqui altera o tamanho das posicoes nem o risco: so informa
(stop colocado ou nao, entrada detetada, saldo em USDC).

O resultado publicado (scan.json) e minimo de proposito, porque o
repositorio e publico: so o saldo livre em USDC e, por operacao aberta,
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
    trig = [_f(o.get("triggerPrice")) for o in orders
            if o.get("symbol") == symbol and o.get("side") == want
            and _f(o.get("triggerPrice")) > 0]
    if not trig:
        return None
    return max(trig) if side == "LONG" else min(trig)


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


def check_trades(ledger, held, orders, execs, now):
    """Para cada operacao 4H aberta: moedas na conta, stop, entrada vista."""
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
               "held": held.get(r["asset"].upper(), 0.0) > 0,
               "stop_found": stop is not None,
               "stop_px": stop, "plan_stop": r.get("stop"),
               "fill_px": round(fill[0], 10) if fill else None}
        if stop is not None and r.get("stop"):
            row["stop_gap_pct"] = round((stop / r["stop"] - 1) * 100, 2)
        out.append(row)
    return out


# ---------- leitura completa ----------

def open_orders():
    out = []
    for flt in ("Order", "StopOrder", "tpslOrder"):
        try:
            res = get("/v5/order/realtime",
                      {"category": "spot", "orderFilter": flt, "limit": 50})
        except AccountError:
            continue
        out += res.get("list") or []
    return out


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
        return {"ok": True, "t": int(now), "usdc_free": usdc_free(wallet),
                "expires": info.get("expiredAt"),
                "trades": check_trades(led, held, orders, execs, now)}
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
