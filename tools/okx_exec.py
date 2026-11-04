"""(04/11) Execucao REAL da compra no panico na OKX Europa. Pedido do Rui: "quero que comecem ja a operar sempre que
houver oportunidade. Ja la esta depositado o dinheiro." (decisao do Rui, acima da autorizacao previa das 30 operacoes).

Regra (a mesma do papel, H23 L10 com custos de futuros H38): para cada sinal do agente, ordem LIMITE de compra 1% abaixo
do fecho, valida 2 velas de 4H, com STOP (2 ATR) e OBJETIVO (2R) anexados na propria ordem; saida por tempo 72 h depois
da execucao (fecho a mercado). Todos os sinais, cada um com risco de 1% da conta (arquitetura do relatorio Missao 20 USD).
Contratos: os X-Perps da OKX Europa (USD_UM_XPERP), os unicos negociaveis por esta conta; margem isolada.
Travoes: so com okx_config.json "real": true; nao abre novas se a conta cair 25% do maximo; teto de posicoes;
nunca levanta nem transfere (a chave nem tem essa permissao).
Repositorio publico: o log nunca mostra saldos; os valores vao so para o Telegram.
"""
import base64, datetime, hashlib, hmac, json, math, os, time, urllib.error, urllib.request

import okx_agente as A

H4 = 14400
CFG_PADRAO = {"real": False, "risco_pct": 1.0, "alavancagem": 10, "max_posicoes": 40, "travao_queda_pct": 25}


def cfg():
    c = dict(CFG_PADRAO)
    p = os.path.join(os.path.dirname(__file__), "..", "okx_config.json")
    if os.path.exists(p):
        c.update(json.load(open(p)))
    return c


def _chaves():
    return tuple((os.environ.get(v) or "").strip() for v in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"))


def privado(metodo, path, corpo=None):
    k, s, p = _chaves()
    agora = datetime.datetime.now(datetime.timezone.utc)
    ts = agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z"
    body = json.dumps(corpo, separators=(",", ":")) if corpo is not None else ""
    sig = base64.b64encode(hmac.new(s.encode(), (ts + metodo + path + body).encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(A.BASE + path, data=body.encode() if body else None, method=metodo,
                                 headers={"OK-ACCESS-KEY": k, "OK-ACCESS-SIGN": sig, "OK-ACCESS-TIMESTAMP": ts,
                                          "OK-ACCESS-PASSPHRASE": p, "Content-Type": "application/json",
                                          "User-Agent": "cryptoscan/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"code": str(e.code), "msg": "HTTP"}
    except Exception as e:
        return {"code": "rede", "msg": type(e).__name__}


def _passo(v, passo):
    return math.floor(v / passo + 1e-9) * passo if passo else v


def _fmt(v, passo):
    casas = max(0, -int(math.floor(math.log10(passo)))) if passo and passo < 1 else 0
    return f"{_passo(v, passo):.{casas}f}"


def xperps():
    """{BASE: info} dos X-Perps negociaveis pela conta (USD_UM_XPERP), com o mais longo se houver varios."""
    conta = {x["instId"] for x in (privado("GET", "/api/v5/account/instruments?instType=FUTURES").get("data") or [])}
    out = {}
    for i in A.get("/api/v5/public/instruments?instType=FUTURES"):
        iid = i.get("instId", "")
        if "XPERP" not in iid or iid not in conta or i.get("state") != "live":
            continue
        base = iid.split("-")[0]
        out[base] = {"inst": iid, "ctVal": float(i.get("ctVal") or 0), "minSz": float(i.get("minSz") or 0),
                     "lotSz": float(i.get("lotSz") or 0), "tick": float(i.get("tickSz") or 0), "ctType": i.get("ctType"),
                     "lever": int(float(i.get("lever") or 1))}
    return out


def equity():
    d = privado("GET", "/api/v5/account/balance")
    if d.get("code") != "0":
        return None
    try:
        return float((d.get("data") or [{}])[0].get("totalEq") or 0)
    except (TypeError, ValueError):
        return None


def plano(sig, info, eq, c):
    """Ordem para um sinal: limite, stop, objetivo e contratos para arriscar risco_pct da conta; None se nao cabe."""
    tick = info["tick"] or 1e-8
    lim = _passo(sig["lim"], tick)
    stop = lim - 2 * sig["atr"]
    if stop <= 0 or lim <= 0:
        return None
    alvo = lim + 2 * (lim - stop)
    risco = eq * c["risco_pct"] / 100
    por_contrato = info["ctVal"] * (lim - stop) if info.get("ctType") != "inverse" else info["ctVal"] * (1 / stop - 1 / lim) * lim
    if por_contrato <= 0:
        return None
    sz = _passo(risco / por_contrato, info["lotSz"] or info["minSz"] or 1)
    if sz < (info["minSz"] or 0) or sz <= 0:
        return None
    nominal = sz * info["ctVal"] * lim
    # a liquidacao (~1/alav) tem de ficar bem abaixo do stop: alav <= 1 / (1,5 x distancia do stop)
    dist = (lim - stop) / lim
    alav = max(1, min(int(c["alavancagem"]), info.get("lever") or 1, int(1 / (1.5 * dist))))
    return {"lim": lim, "stop": _passo(stop, tick), "alvo": _passo(alvo, tick), "sz": sz, "nominal": round(nominal, 2),
            "risco_usd": round(sz * por_contrato, 3), "alav": alav,
            "px_s": _fmt(lim, tick), "stop_s": _fmt(stop, tick), "alvo_s": _fmt(alvo, tick), "sz_s": _fmt(sz, info["lotSz"] or 1)}


def abrir(base, sig, info, eq, c, now, msgs):
    p = plano(sig, info, eq, c)
    if not p:
        msgs.append(f"⏭️ OKX real — {base}: o risco de {c['risco_pct']}% não chega à ordem mínima do contrato; não entrei.")
        return None
    privado("POST", "/api/v5/account/set-leverage", {"instId": info["inst"], "lever": str(p["alav"]), "mgnMode": "isolated"})
    cl = f"cs{base[:8]}{int(sig['t_sig']) % 100000000}".replace("-", "")[:32]
    corpo = {"instId": info["inst"], "tdMode": "isolated", "side": "buy", "ordType": "limit", "px": p["px_s"], "sz": p["sz_s"],
             "clOrdId": cl, "attachAlgoOrds": [{"tpTriggerPx": p["alvo_s"], "tpOrdPx": "-1",
                                                "slTriggerPx": p["stop_s"], "slOrdPx": "-1"}]}
    r = privado("POST", "/api/v5/trade/order", corpo)
    d = (r.get("data") or [{}])[0]
    if d.get("sCode") == "51016":               # clOrdId repetido: a ordem ja existe (estado perdido) -> adota-a
        q = privado("GET", f"/api/v5/trade/order?instId={info['inst']}&clOrdId={cl}")
        qd = (q.get("data") or [{}])[0]
        if qd.get("ordId"):
            d = {"ordId": qd["ordId"], "sCode": "0"}
            r = {"code": "0"}
    if r.get("code") != "0" or d.get("sCode") not in ("0", None):
        msgs.append(f"⚠️ OKX real — {base}: a OKX recusou a ordem ({d.get('sCode') or r.get('code')}: {(d.get('sMsg') or r.get('msg') or '')[:90]}).")
        return None
    msgs.append(f"📌 OKX real — {base}: ordem limite de compra a {p['px_s']} ({p['sz_s']} contratos, ~{p['nominal']} USD, "
                f"{p['alav']}x isolada). Stop {p['stop_s']} e objetivo {p['alvo_s']} anexados; risco ~{p['risco_usd']} USD "
                f"({c['risco_pct']}% da conta). Válida 8 h.")
    return {"inst": info["inst"], "ordId": d.get("ordId"), "clOrdId": cl, "estado": "pendente", "t_sig": sig["t_sig"],
            "valido_ate": sig["t_sig"] + 3 * H4, "criado": int(now), **{k: p[k] for k in ("lim", "stop", "alvo", "sz", "nominal", "alav")}}


def acompanhar(base, op, now, msgs):
    """Atualiza uma operacao real; devolve True quando acabou (cancelada ou fechada)."""
    if op["estado"] == "pendente":
        r = privado("GET", f"/api/v5/trade/order?instId={op['inst']}&ordId={op['ordId']}")
        d = (r.get("data") or [{}])[0]
        st = d.get("state")
        if st == "filled" or (st == "partially_filled" and now >= op["valido_ate"]):
            if st == "partially_filled":
                privado("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
            op.update(estado="aberta", entrada=float(d.get("avgPx") or op["lim"]), t_fill=int(int(d.get("fillTime") or now * 1000) / 1000),
                      sz_exec=float(d.get("accFillSz") or op["sz"]))
            op["sair_em"] = op["t_fill"] + 18 * H4
            msgs.append(f"✅ OKX real — {base}: compra executada a {op['entrada']:.6g} ({op['sz_exec']:g} contratos). "
                        f"Stop e objetivo na OKX; saída por tempo dentro de 72 h.")
        elif st in ("canceled", "mmp_canceled"):
            msgs.append(f"⌛ OKX real — {base}: a ordem foi cancelada sem executar.")
            return True
        elif st == "live" and now >= op["valido_ate"]:
            privado("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
            msgs.append(f"⌛ OKX real — {base}: a ordem limite caducou (8 h) sem executar; cancelei-a. Nada comprado.")
            return True
        return False
    if op["estado"] == "aberta":
        pos = privado("GET", f"/api/v5/account/positions?instId={op['inst']}")
        aberta = any(float(x.get("pos") or 0) != 0 for x in (pos.get("data") or []))
        motivo = None
        if aberta and now >= op["sair_em"]:
            privado("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated", "autoCxl": True})
            motivo = "tempo (72 h)"
        elif not aberta:
            motivo = "stop ou objetivo"
        if motivo:
            h = privado("GET", f"/api/v5/account/positions-history?instId={op['inst']}&limit=1")
            hd = (h.get("data") or [{}])[0]
            pnl = hd.get("realizedPnl") or hd.get("pnl")
            px = hd.get("closeAvgPx")
            msgs.append(f"🏁 OKX real — {base} fechou ({motivo})" + (f" a {float(px):.6g}" if px else "") +
                        (f": resultado {float(pnl):+.3f} USD." if pnl not in (None, "") else "."))
            op.update(estado="fechada", motivo=motivo, pnl=float(pnl) if pnl not in (None, "") else None, fechado=int(now))
            return True
    return False


def correr(st, novos, now, msgs):
    """novos: [(base, sinal)] do agente nesta passagem. st: okx.json (chave 'real' so com ids e precos publicos)."""
    c = cfg()
    R = st.setdefault("real", {"ops": {}, "hist": [], "pico": None})
    if not all(_chaves()):
        return
    for base in list(R["ops"]):
        if acompanhar(base, R["ops"][base], now, msgs):
            R["hist"].append({"asset": base, **R["ops"].pop(base)})
    del R["hist"][:-500]
    if not c["real"] or not novos:
        return
    eq = equity()
    if not eq:
        msgs.append("⚠️ OKX real: não consegui ler o saldo da conta; nenhuma ordem nova.")
        return
    R["pico"] = max(R.get("pico") or eq, eq)
    if eq < R["pico"] * (1 - c["travao_queda_pct"] / 100):
        msgs.append(f"🛑 OKX real: a conta está {c['travao_queda_pct']}% abaixo do máximo; travão ligado, sem ordens novas.")
        return
    xp = xperps()
    tent = R.setdefault("tentados", [])
    for base, sig in novos:
        chave = f"{base}:{sig['t_sig']}"
        if base in R["ops"] or chave in tent or len(R["ops"]) >= c["max_posicoes"] or now >= sig["t_sig"] + 3 * H4 - 300:
            continue
        tent.append(chave)
        del tent[:-500]
        info = xp.get(base)
        if not info:
            msgs.append(f"⏭️ OKX real — {base}: não há X-Perp negociável na tua conta; fica só em papel.")
            continue
        op = abrir(base, sig, info, eq, c, now, msgs)
        if op:
            R["ops"][base] = op
