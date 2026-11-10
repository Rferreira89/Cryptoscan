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
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import guarda as G  # noqa: E402  (10/11: verificacoes puras antes da ordem)

H4 = 14400
CFG_PADRAO = {"real": False, "so_mercado": True, "risco_pct": 1.0, "risco_max_pct": 2.0, "alavancagem": 10, "max_posicoes": 40, "travao_queda_pct": 25,
              "recuo_real": False, "recuo_risco_pct": 1.0,
              # (05/11, OK do Rui) interruptor proprio da H40 (panico): so abre ordens reais com true explicito;
              # ausente = so papel (seguro)
              "panico_real": False,
              # (08/11, OK do Rui) H40 de volta a real com risco limitado: 1% por operacao (sem tolerancia acima),
              # no maximo 3 posicoes H40 e teto de risco aberto de 3% da conta somando TODAS as estrategias
              "panico_risco_pct": 1.0, "panico_risco_max_pct": 1.0, "panico_max_posicoes": 3, "risco_total_max_pct": 3.0}


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
        # (04/11) com 20 USD a ordem minima as vezes obriga a arriscar mais: aceita ate risco_max_pct (2%; no H38 o
        # risco de 2% em todos os sinais ainda fez crescer a conta nas duas metades: x1,43 e x1,11)
        sz = info["minSz"] or 0
        if sz <= 0 or sz * por_contrato > eq * c.get("risco_max_pct", 2.0) / 100:
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
        msgs.append(f"⏭️ OKX real — {base}: a ordem mínima do contrato obrigava a arriscar mais de {c.get('risco_max_pct', 2.0)}% da conta; não entrei.")
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
                f"({100 * p['risco_usd'] / eq:.1f}% da conta). Válida 8 h.")
    # repositorio publico: o estado guarda so precos e ids, nunca tamanhos nem valores da conta
    return {"inst": info["inst"], "ordId": d.get("ordId"), "clOrdId": cl, "estado": "pendente", "t_sig": sig["t_sig"],
            "valido_ate": sig["t_sig"] + 3 * H4, "criado": int(now), **{k: p[k] for k in ("lim", "stop", "alvo", "alav")}}


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
                      )
            sz_exec = d.get("accFillSz") or "?"
            op["sair_em"] = op["t_fill"] + 18 * H4
            msgs.append(f"✅ OKX real — {base}: compra executada a {op['entrada']:.6g} ({sz_exec} contratos). "
                        f"Stop e objetivo na OKX; saída por tempo dentro de 72 h.")
        elif st in ("canceled", "mmp_canceled"):
            msgs.append(f"⌛ OKX real — {base}: a ordem foi cancelada sem executar.")
            op.update(estado="cancelada", motivo="cancelada sem executar", fechado=int(now))
            return True
        elif st == "live" and now >= op["valido_ate"]:
            privado("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
            msgs.append(f"⌛ OKX real — {base}: a ordem limite caducou (8 h) sem executar; cancelei-a. Nada comprado.")
            op.update(estado="cancelada", motivo="caducou (8 h) sem executar", fechado=int(now))
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
            saida = float(px) if px else None
            op.update(estado="fechada", motivo=motivo, saida=saida, fechado=int(now),
                      ret_pct=round(100 * (saida / op["entrada"] - 1), 2) if saida and op.get("entrada") else None)
            return True
    return False


def migrar_publico(R, now):
    """(05/11, OK do Rui) o okx.json e PUBLICO: (1) o maximo da conta em USD ("pico") passa a ficar so cifrado
    (pico_cifrado, com DATA_KEY); sem chave fica como esta e o travao FECHA as entradas novas (estado_pico);
    (2) ordens canceladas que ficaram no historico como "pendente" passam a "cancelada"."""
    if "pico" in R and _chave_ativa():
        v = R.pop("pico")
        if v and not R.get("pico_cifrado"):
            guardar_pico(R, float(v))
    for h in R.get("hist") or []:
        if h.get("estado") == "pendente":                # no historico so ha operacoes acabadas
            h.update(estado="cancelada", motivo=h.get("motivo") or "cancelada sem executar (registo corrigido)")


def _chave_ativa():
    try:
        from engine import cifra
        return cifra.ativa()
    except Exception:
        return False


def ler_pico(R):
    env = R.get("pico_cifrado")
    if not env:
        return None
    try:
        from engine import cifra
        return float(cifra.decifrar_bytes(env).decode())
    except Exception:
        return None


def estado_pico(R, c, eq):
    """(05/11, OK do Rui: fail-closed) ("ok", pico) para operar, ou ("fechado", motivo) para NAO abrir ordens novas.
    - maximo cifrado legivel -> ok;
    - sem chave, chave errada ou envelope estragado -> fechado (nunca recomeca sozinho do saldo atual);
    - sem maximo nenhum -> fechado, SEMPRE: um estado vazio pode ser uma conta nova ou um estado perdido, e o programa
      nao consegue provar qual e (05/11, Rui). O primeiro maximo exige inicializacao explicita e autorizada;
    - inicializacao/recomeco manual: okx_config "travao_reiniciar_pico": "<data>" (com o OK do Rui) poe o maximo no saldo
      atual UMA vez por cada valor novo (fica registado em pico_reiniciado)."""
    pedido = c.get("travao_reiniciar_pico")
    if pedido and R.get("pico_reiniciado") != pedido and _chave_ativa():
        guardar_pico(R, eq)
        if R.get("pico_cifrado"):
            R["pico_reiniciado"] = pedido
            return "ok", eq
    if not _chave_ativa():
        return "fechado", "sem a chave DATA_KEY o máximo da conta não pode ser lido"
    if "pico" in R:
        return "fechado", "o máximo antigo ainda não foi cifrado"
    if R.get("pico_cifrado"):
        v = ler_pico(R)
        return ("ok", v) if v else ("fechado", "o máximo cifrado não abre (chave diferente ou ficheiro alterado)")
    if R.get("hist") or R.get("ops"):
        return "fechado", "o máximo da conta desapareceu do estado"
    return "fechado", "máximo da conta por inicializar (precisa de inicialização autorizada: travao_reiniciar_pico)"


def guardar_pico(R, v):
    try:
        from engine import cifra
        R["pico_cifrado"] = cifra.cifrar_bytes(f"{float(v):.8f}".encode())
    except Exception:
        R.pop("pico_cifrado", None)                      # sem DATA_KEY: nunca grava o valor em claro


def correr(st, novos, now, msgs):
    """novos: [(base, sinal)] do agente nesta passagem. st: okx.json (chave 'real' so com ids e precos publicos)."""
    c = cfg()
    R = st.setdefault("real", {"ops": {}, "hist": []})
    for op in list(R["ops"].values()) + R["hist"]:  # limpeza: tamanhos e valores nunca ficam no estado publico
        for k in ("sz", "nominal", "sz_exec", "pnl", "risco_usd"):
            op.pop(k, None)
    migrar_publico(R, now)
    if not all(_chaves()):
        return
    reconciliar(R, now, msgs)
    for base in list(R["ops"]):
        op = R["ops"][base]
        if c.get("so_mercado", True) and op.get("estado") == "pendente" and op.get("estrategia") != "recuo" \
                and ((st.get("pend") or {}).get(base) or {}).get("tipo") == "isolado":
            # (04/11, H40) ordem posta antes do filtro num panico isolado: cancela SO se ainda nao executou
            cx = privado("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
            if cx.get("code") == "0" and ((cx.get("data") or [{}])[0].get("sCode") in ("0", None)):
                msgs.append(f"🛑 OKX real — {base}: cancelei a ordem limite (pânico isolado; pelo H40 só operamos o pânico do mercado todo).")
                R["hist"].append({"asset": base, **R["ops"].pop(base), "estado": "cancelada", "motivo": "H40 isolado"})
                continue
        if acompanhar(base, R["ops"][base], now, msgs):
            R["hist"].append({"asset": base, **R["ops"].pop(base)})
    del R["hist"][:-500]
    if not c["real"] or not novos:
        return
    eq = equity()
    if not eq:
        msgs.append("⚠️ OKX real: não consegui ler o saldo da conta; nenhuma ordem nova.")
        return
    est, v = estado_pico(R, c, eq)
    if est != "ok":
        msgs.append(f"🔒 OKX real: travão em modo seguro ({v}); nenhuma ordem nova. As posições abertas continuam a ser geridas.")
        return
    pico = max(v, eq)
    guardar_pico(R, pico)
    if eq < pico * (1 - c["travao_queda_pct"] / 100):
        msgs.append(f"🛑 OKX real: a conta está {c['travao_queda_pct']}% abaixo do máximo; travão ligado, sem ordens novas.")
        return
    xp = xperps()
    tent = R.setdefault("colocados", [])          # so os sinais com ordem posta (uma recusa por tamanho volta a tentar)
    for base, sig in novos:
        chave = f"{base}:{sig['t_sig']}"
        if base in R["ops"] or chave in tent or len(R["ops"]) >= c["max_posicoes"] or now >= sig["t_sig"] + 3 * H4 - 300:
            continue
        recuo = sig.get("tipo") == "recuo"
        if recuo and not c.get("recuo_real"):
            continue
        h40 = sig.get("tipo") in ("mercado", "isolado", None)      # sinais do panico do agente (tools/okx_agente.py)
        if not recuo and not h40:
            continue                                              # estrategia desconhecida: nunca abre ordens reais
        if h40 and not c.get("panico_real", False):
            # (05/11, OK do Rui) H40 suspensa do dinheiro real: o sinal fica so em papel (a H46 continua)
            chave_p = f"p:{base}:{sig['t_sig']}"
            if chave_p not in R.setdefault("avisados", []):
                R["avisados"].append(chave_p)
                msgs.append(f"📝 OKX — {base}: sinal de pânico (H40) só em papel; a H40 está suspensa do dinheiro real.")
            continue
        if c.get("so_mercado", True) and sig.get("tipo") not in ("mercado", "recuo"):
            # (04/11, H40) o panico isolado perdeu na metade recente (-0,126R); o do mercado todo deu +0,17R/+0,41R
            chave_i = f"i:{base}:{sig['t_sig']}"
            if chave_i not in R.setdefault("avisados", []):
                R["avisados"].append(chave_i)
                msgs.append(f"⏭️ OKX real — {base}: pânico isolado (o BTC não caiu): fica só em papel (H40).")
            continue
        info = xp.get(base)
        if not info:
            chave_x = f"x:{base}:{sig['t_sig']}"
            if chave_x not in R.setdefault("avisados", []):
                R["avisados"].append(chave_x)
                msgs.append(f"⏭️ OKX real — {base}: não há X-Perp negociável na tua conta; fica só em papel.")
            continue
        avisados = R.setdefault("avisados", [])
        n0 = len(msgs)
        # (04/11, OK do Rui) H46 recuo na subida com dinheiro real antes das 30 em papel, mas com metade do risco (1%)
        cc = {**c, "risco_pct": float(c.get("recuo_risco_pct") or 1.0),
              "risco_max_pct": min(float(c.get("risco_max_pct", 2.0)), 2.0)} if recuo else c
        if h40:
            # (08/11, OK do Rui) H40 com risco limitado: 1% por operacao e no maximo 3 posicoes H40 ao mesmo tempo
            cc = {**c, "risco_pct": float(c.get("panico_risco_pct", 1.0)),
                  "risco_max_pct": float(c.get("panico_risco_max_pct", 1.0))}
            n_h40 = sum(1 for o in R["ops"].values() if o.get("estrategia") != "recuo")
            if n_h40 >= int(c.get("panico_max_posicoes", 3)):
                chave_m = f"m:{base}:{sig['t_sig']}"
                if chave_m not in avisados:
                    avisados.append(chave_m)
                    msgs.append(f"⏭️ OKX real — {base}: já há {n_h40} posições da H40 (máximo {c.get('panico_max_posicoes', 3)}); fica só em papel.")
                continue
        # (08/11) teto de risco aberto somando todas as estrategias (percentagens, nunca valores, no estado publico)
        p = plano(sig, info, eq, cc)
        aberto = sum(float(o.get("risco_pct") or (cc["risco_max_pct"] if o.get("estrategia") != "recuo" else 2.0))
                     for o in R["ops"].values())
        if p and aberto + 100 * p["risco_usd"] / eq > float(c.get("risco_total_max_pct", 3.0)) + 1e-9:
            chave_r = f"r:{base}:{sig['t_sig']}"
            if chave_r not in avisados:
                avisados.append(chave_r)
                msgs.append(f"⏭️ OKX real — {base}: o risco aberto passaria {c.get('risco_total_max_pct', 3.0)}% da conta; fica só em papel.")
            continue
        # (10/11, investigacao) guarda antes da ordem: stop sao e do lado certo, sem duplicado, e os limites opcionais
        # de cfg["guarda"] (desligados por omissao: ligar e decisao do Rui)
        if p:
            fech = [{"resultado": h.get("ret_pct"), "t": h.get("fechado")} for h in R["hist"]
                    if h.get("estado") == "fechada"]
            fech.sort(key=lambda f: f["t"] or 0)
            n24 = sum(1 for o in list(R["ops"].values()) + R["hist"]
                      if (o.get("criado") or 0) >= now - 86400 and o.get("ordId"))
            pode, porque = G.verificar(c, lado="LONG", entrada=p["lim"], stop=p["stop"], ativo=base, t_sinal=sig["t_sig"],
                                       agora=now, entradas_24h=n24, fechadas=fech, abertas=set(R["ops"]))
            if not pode:
                chave_g = f"g:{base}:{sig['t_sig']}"
                if chave_g not in avisados:
                    avisados.append(chave_g)
                    msgs.append(f"⏭️ OKX real — {base}: guarda antes da ordem: {'; '.join(porque)}.")
                continue
        op = abrir(base, sig, info, eq, cc, now, msgs)
        if op and p:
            op["risco_pct"] = round(100 * p["risco_usd"] / eq, 2)
        if op and h40:
            op["estrategia"] = "panico"
        if op and recuo:
            op["estrategia"] = "recuo"
            msgs[-1] = msgs[-1].replace("OKX real — ", "OKX real (recuo na subida, H46) — ", 1)
        if op:
            R["ops"][base] = op
            tent.append(chave)
            del tent[:-500]
        elif chave in avisados:                   # a mesma recusa nao se repete no Telegram de hora a hora
            del msgs[n0:]
        else:
            avisados.append(chave)
            del avisados[:-500]


def reconciliar(R, now, msgs):
    """(04/11) posicoes abertas na OKX que o programa nao esta a seguir (ex.: a HUMA executou antes do cancelamento):
    adota-as para a saida por tempo e confirma que tem stop; se nao tiver, poe o stop do plano original."""
    pos = privado("GET", "/api/v5/account/positions?instType=FUTURES")
    if pos.get("code") != "0":
        return
    seguidas = {o["inst"] for o in R["ops"].values()}
    for x in pos.get("data") or []:
        if not float(x.get("pos") or 0) or x.get("instId") in seguidas:
            continue
        inst, base = x["instId"], x["instId"].split("-")[0]
        ant = next((h for h in reversed(R["hist"]) if h.get("inst") == inst), {})
        t_fill = int(int(x.get("cTime") or now * 1000) / 1000)
        op = {"inst": inst, "ordId": ant.get("ordId"), "estado": "aberta", "entrada": float(x.get("avgPx") or 0), "t_fill": t_fill,
              "sair_em": t_fill + 18 * H4, "stop": ant.get("stop"), "alvo": ant.get("alvo"), "alav": int(float(x.get("lever") or 0) or 0),
              "t_sig": ant.get("t_sig"), "criado": int(now), "adotada": True}
        R["ops"][base] = op
        if ant:
            R["hist"].remove(ant)
        algos = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
        algos2 = privado("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
        tem_stop = any(a.get("slTriggerPx") for a in (algos.get("data") or []) + (algos2.get("data") or []))
        if not tem_stop and op["stop"]:
            r = privado("POST", "/api/v5/trade/order-algo", {"instId": inst, "tdMode": "isolated", "side": "sell", "ordType": "oco",
                                                            "sz": x.get("pos"), "reduceOnly": True,
                                                            "slTriggerPx": str(op["stop"]), "slOrdPx": "-1",
                                                            "tpTriggerPx": str(op["alvo"]), "tpOrdPx": "-1"})
            tem_stop = r.get("code") == "0"
        msgs.append(f"🔁 OKX real — {base}: posição aberta a {op['entrada']:.6g} encontrada e adotada (sai no stop, no objetivo ou ao fim de 72 h). "
                    + ("Stop confirmado ✅" if tem_stop else "⚠️ NÃO consegui confirmar o stop: verifica na app da OKX."))


def cofre(caminho):
    """(04/11, Rui: "na interface deveria dizer o dinheiro e as operacoes que tenho na OKX") dados privados da conta
    OKX para a app. So grava se houver DATA_KEY: o ficheiro e cifrado logo a seguir (engine.cifra); nunca em claro."""
    if not os.environ.get("DATA_KEY") or not all(_chaves()):
        return False
    b = privado("GET", "/api/v5/account/balance")
    if b.get("code") != "0":
        return False
    d0 = (b.get("data") or [{}])[0]
    moedas = [{"ccy": x.get("ccy"), "eq": float(x.get("eq") or 0), "disponivel": float(x.get("availBal") or 0)}
              for x in d0.get("details") or [] if float(x.get("eq") or 0) > 0]
    pos = []
    for x in (privado("GET", "/api/v5/account/positions?instType=FUTURES").get("data") or []):
        if not float(x.get("pos") or 0):
            continue
        pos.append({"asset": x["instId"].split("-")[0], "inst": x["instId"], "contratos": float(x.get("pos") or 0),
                    "entrada": float(x.get("avgPx") or 0), "atual": float(x.get("markPx") or 0) or None,
                    "valor_usd": float(x.get("notionalUsd") or 0), "margem_usd": float(x.get("imr") or x.get("margin") or 0),
                    "pnl_usd": float(x.get("upl") or 0), "pnl_pct": round(100 * float(x.get("uplRatio") or 0), 2),
                    "alav": float(x.get("lever") or 0), "liquidacao": float(x.get("liqPx") or 0) or None})
    ordens = [{"asset": x["instId"].split("-")[0], "preco": float(x.get("px") or 0), "contratos": float(x.get("sz") or 0),
               "lado": x.get("side")} for x in (privado("GET", "/api/v5/trade/orders-pending?instType=FUTURES").get("data") or [])]
    fech = [{"asset": x["instId"].split("-")[0], "entrada": float(x.get("openAvgPx") or 0), "saida": float(x.get("closeAvgPx") or 0),
             "pnl_usd": float(x.get("realizedPnl") or x.get("pnl") or 0), "t": int(int(x.get("uTime") or 0) / 1000)}
            for x in (privado("GET", "/api/v5/account/positions-history?instType=FUTURES&limit=30").get("data") or [])]
    out = {"t": int(time.time()), "equity_usd": float(d0.get("totalEq") or 0), "moedas": moedas, "posicoes": pos,
           "ordens": ordens, "fechadas": fech, "pnl_aberto_usd": round(sum(p["pnl_usd"] for p in pos), 4),
           "pnl_fechado_usd": round(sum(f["pnl_usd"] for f in fech), 4)}
    json.dump(out, open(caminho, "w"))
    return True
