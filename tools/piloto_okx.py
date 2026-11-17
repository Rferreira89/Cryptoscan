"""(17/11, ordem do Rui) PILOTO REAL OKX - executor isolado, so a estrategia "Rompimento com reteste 4H LONG -
cripto, v2" (regra e495d11739f6 do Hunter), com limites proprios e bloqueios persistentes.

Limites (piloto_okx_config.json; nunca alterados pelo programa): capital 10 USDC, perda acumulada 5 USDC
(suspensao de entradas aos 3), perda diaria 1 USDC, risco planeado por operacao 0,25 USDC COM custos, nocional
10 USDC, alavancagem 1x-5x (a menor que chega), 1 posicao, margem isolada, so LONG.

Antes de QUALQUER ordem, todas as portas tem de estar abertas (cada falha fica escrita com a causa):
  config_ativa, teste_fora_da_amostra, conta_usdc (settlement), sem_levantamentos (permissoes da API),
  saldo_usdc, isolamento (o executor OKX existente adota qualquer posicao da conta que nao segue - ver
  okx_exec.reconciliar - e geriria/fecharia a do piloto; so passa quando okx_exec declarar PILOTO_ISOLADO),
  bloqueio (perdas/estado persistente), dados (velas fiaveis).
Uma ordem enviada nao e uma ordem executada; uma posicao so esta protegida com o stop confirmado na OKX.
Nunca: ordens para recuperar perdas, aumentar o tamanho para caber no minimo, mexer noutras posicoes/ordens da conta
(so instrumentos e clOrdId do piloto, prefixo "pil"), mudar configuracoes globais da conta, converter fundos.
Um stop nao garante a perda maxima: gaps, deslizamento e falhas podem dar perdas maiores (reserva de custos).

Uso: python3 tools/piloto_okx.py <pasta_estado> [--simular]
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import protecao as PROT  # noqa: E402
from engine import quick_opportunities_derivatives as DERIV  # noqa: E402

H4 = 14400
REGRA = {"id": "e495d11739f6", "familia": "rompimento_reteste", "parametros": {"n": 24}, "tf": "4H", "lado": "LONG",
         "filtro": "cripto", "stop_ref": "4H", "saida": {"tipo": "fixa", "k": 3.0, "tp": 1.5, "hold": 6}}
CFG_FICHEIRO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "piloto_okx_config.json")
PREFIXO = "pil"
COMISSAO = 0.0005           # por lado (taker, conservador)
SPREAD_MAX_PCT = 0.30
PRAZO_ENTRADA_S = 3600


def cfg():
    with open(CFG_FICHEIRO, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ sinal (identico ao Hunter) --------------------
def atr14(v):
    tr = [0.0] + [max(v[i]["h"] - v[i]["l"], abs(v[i]["h"] - v[i - 1]["c"]), abs(v[i]["l"] - v[i - 1]["c"]))
                  for i in range(1, len(v))]
    out = [None] * len(v)
    for i in range(14, len(v)):
        out[i] = sum(tr[i - 13:i + 1]) / 14
    return out


def sinal_v2(v, n=24):
    """Ultima vela fechada de 4H: rompeu o maximo das n velas anteriores nas ultimas 3, voltou ao nivel
    (minimo a +-0,3 ATR) e fecha acima. Mesma regra de tools/hunter/familias.rompimento_reteste (prev_max e
    deslocamentos de 3 velas). Devolve {nivel, atr, fecho, t} ou None."""
    i = len(v) - 1
    if i < n + 4:
        return None
    nivel = max(b["h"] for b in v[i - 3 - n:i - 3])            # prev_max(h, n) na vela i-3
    rompeu = max(v[i - k]["c"] for k in (1, 2, 3)) > nivel
    a = atr14(v)[i]
    if not a or not rompeu:
        return None
    if abs(v[i]["l"] - nivel) <= 0.3 * a and v[i]["c"] > nivel:
        return {"nivel": nivel, "atr": a, "fecho": v[i]["c"], "t": v[i]["t"]}
    return None


def plano(sig, k=3.0, tp=1.5):
    e = sig["fecho"]
    risco = k * sig["atr"]
    return {"entrada": e, "stop": e - risco, "alvo": e + tp * risco}


# ------------------------------------------------------------------ dimensionamento -------------------------------
def _passo(x, passo):
    return math.floor(x / passo + 1e-9) * passo if passo else x


def dimensionar(pl, inst, c, spread_pct, funding_8h=0.0, saldo=None):
    """Contratos para arriscar <= risco_max_op USDC INCLUINDO custos (comissao ida e volta, metade do spread e
    deslizamento de reserva, funding estimado de 24 h); nocional <= nocional_max; alavancagem 1-5 (a menor que
    chega para a margem caber no capital livre). Rejeita (devolve motivo) em vez de aumentar para o minimo."""
    e, st = pl["entrada"], pl["stop"]
    if not (0 < st < e):
        return None, "stop invalido"
    ctv = float(inst["ctVal"]) * float(inst.get("ctMult") or 1)
    conv = e if (inst.get("ctValCcy") or "").upper() != "USD" else 1.0
    nocional_1 = ctv * conv                                    # USDC por contrato
    reserva = c["reserva_deslize_pct"] / 100
    # custos em fracao do nocional: comissao ida e volta + spread (meio spread em cada lado) + reserva de deslizamento
    # adverso + funding de 24 h (3 eventos de 8 h) se for contra o LONG
    custo_pct = 2 * COMISSAO + spread_pct / 100 + reserva + max(0.0, funding_8h) * 3
    risco_1 = nocional_1 * (e - st) / e + nocional_1 * custo_pct
    lote, minimo = float(inst["lotSz"]), float(inst["minSz"])
    n = _passo(min(c["risco_max_op"] / risco_1, c["nocional_max"] / nocional_1), lote)
    if n < minimo:
        return None, (f"tamanho minimo ({minimo:g} contratos) arriscaria {minimo * risco_1:.3f} USDC ou nocional "
                      f"{minimo * nocional_1:.2f} USDC: acima dos limites")
    nocional = n * nocional_1
    livre = min(c["capital_max"], saldo if saldo is not None else c["capital_max"])
    alav = max(1, math.ceil(nocional / max(1e-9, livre * 0.9)))
    if alav > c["alav_max"]:
        return None, f"precisaria de {alav}x de alavancagem (maximo {c['alav_max']}x)"
    return {"contratos": n, "nocional": round(nocional, 4), "risco_total": round(n * risco_1, 4), "alav": alav,
            "margem": round(nocional / alav, 4), "custos_estimados": round(n * nocional_1 * custo_pct, 4)}, None


# ------------------------------------------------------------------ estado e bloqueios -----------------------------
def estado_inicial():
    return {"ops": [], "aberta": None, "bloqueio": None, "suspenso": None, "perda_realizada": 0.0, "dias": {},
            "vistos": [], "portas": {}, "eventos": []}


def evento(st, now, txt, **kw):
    st["eventos"].append({"t": int(now), "txt": txt, **kw})
    st["eventos"] = st["eventos"][-500:]


def perdas(st, upl, now):
    """Perda acumulada = realizada + nao realizada da posicao aberta (sem duplicar: a realizada so conta fechos)."""
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    nao = min(0.0, upl or 0.0)
    return {"acumulada": round(max(0.0, -(st["perda_realizada"] + nao)), 4),
            "dia": round(max(0.0, -(st["dias"].get(dia, 0.0) + nao)), 4)}


def aplicar_limites(st, c, upl, now):
    """Bloqueios persistentes (nunca apagados por uma nova execucao: so editando o estado a mao, decisao do Rui)."""
    p = perdas(st, upl, now)
    acoes = []
    if p["acumulada"] >= c["perda_max"] and not st["bloqueio"]:
        st["bloqueio"] = {"t": int(now), "motivo": f"perda acumulada {p['acumulada']:.2f} >= {c['perda_max']} USDC: piloto encerrado"}
        acoes += ["cancelar_entradas", "fechar_posicao"]
    elif p["acumulada"] >= c["suspender_em"] and not st["suspenso"]:
        st["suspenso"] = {"t": int(now), "motivo": f"perda acumulada {p['acumulada']:.2f} >= {c['suspender_em']} USDC: revisao"}
        acoes += ["cancelar_entradas"]
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    if p["dia"] >= c["perda_diaria_max"]:
        st.setdefault("bloqueio_dia", {})[dia] = f"perda do dia {p['dia']:.2f} >= {c['perda_diaria_max']} USDC"
        acoes += ["cancelar_entradas"]
    return p, acoes


# ------------------------------------------------------------------ portas -----------------------------------------
def portas(api, st, c, now, teste_oos, isolado):
    out = {}
    out["config_ativa"] = (bool(c.get("ativo")), "ativo no piloto_okx_config.json")
    t = teste_oos or {}
    ok_oos = bool(t.get("n", 0) >= 30 and (t.get("r_medio") or 0) > 0)
    out["teste_fora_da_amostra"] = (ok_oos, f"teste final da regra: {json.dumps({k: t.get(k) for k in ('n', 'r_medio', 'ic95_r', 'p_r_positivo')})}")
    conf = api.priv("GET", "/api/v5/account/config")
    ok, porque = DERIV.validate_okx_account_config(conf)
    out["conta_usdc"] = (ok, porque)
    row = ((conf or {}).get("data") or [{}])[0]
    perm = str(row.get("perm") or "")
    out["sem_levantamentos"] = (bool(perm) and "withdraw" not in perm, f"permissoes da API: {perm or 'desconhecidas'}")
    out["modo_conta"] = (str(row.get("posMode")) == "net_mode" and str(row.get("acctLv")) in ("2", "3"),
                         f"posMode={row.get('posMode')} acctLv={row.get('acctLv')} (precisa net_mode e margem)")
    bal = api.priv("GET", "/api/v5/account/balance?ccy=USDC")
    try:
        disp = float(((bal.get("data") or [{}])[0].get("details") or [{}])[0].get("availBal") or 0)
    except (TypeError, ValueError, IndexError, AttributeError):
        disp = 0.0
    st["_saldo_usdc"] = disp
    out["saldo_usdc"] = (disp >= c["capital_max"], "saldo USDC disponivel suficiente para o capital do piloto"
                         if disp >= c["capital_max"] else "saldo USDC disponivel abaixo do capital do piloto")
    out["isolamento"] = (bool(isolado), "o executor OKX existente ignora as posicoes do piloto" if isolado else
                         "o executor OKX existente (okx_exec.reconciliar) adota qualquer posicao que nao segue e "
                         "geri-la-ia/fecha-la-ia: falta a autorizacao para o isolar (ou uma subconta dedicada)")
    out["bloqueio"] = (not st["bloqueio"] and not st["suspenso"],
                       (st["bloqueio"] or st["suspenso"] or {}).get("motivo", "sem bloqueio"))
    return {k: {"ok": bool(v[0]), "detalhe": v[1]} for k, v in out.items()}


# ------------------------------------------------------------------ ciclo -----------------------------------------
def instrumentos(api):
    """X-Perps de cripto vivos E negociaveis pela conta (lista da conta), com a especificacao atual."""
    conta = {x["instId"] for x in (api.priv("GET", "/api/v5/account/instruments?instType=FUTURES").get("data") or [])}
    out = {}
    for i in api.pub("/api/v5/public/instruments", {"instType": "FUTURES"}) or []:
        iid = i.get("instId", "")
        if (DERIV.is_um_xperp(iid) and iid in conta and i.get("state") == "live" and i.get("ctType") == "linear"
                and str(i.get("instCategory")) == "1" and str(i.get("ruleType")).lower() != "pre_market"):
            out[iid.split("-")[0]] = {"inst": iid, "ctVal": i["ctVal"], "ctMult": i.get("ctMult") or 1,
                                      "ctValCcy": i.get("ctValCcy"), "lotSz": i["lotSz"], "minSz": i["minSz"],
                                      "tickSz": i["tickSz"], "lever": i.get("lever")}
    return out


def velas4h(api, inst, now):
    d = api.pub("/api/v5/market/history-candles", {"instId": inst, "bar": "4H", "limit": 100}) or []
    v = sorted(({"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
                for x in d if len(x) > 8 and str(x[8]) == "1"), key=lambda b: b["t"])
    return [b for b in v if b["t"] + H4 <= now]


def ciclo(api, pasta, now=None, simular=False, teste_oos=None, isolado=None, enviar=lambda m: None):
    now = int(now or time.time())
    c = cfg()
    p = os.path.join(pasta, "piloto_estado.json")
    st = estado_inicial()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            st.update(json.load(f))
    if isolado is None:
        isolado = _okx_exec_isolado()
    msgs = []
    # 1. reconciliar com a OKX: posicoes e ordens do piloto (so as dele)
    rec = reconciliar(api, st, now, msgs)
    upl = rec.get("upl", 0.0)
    pp, acoes = aplicar_limites(st, c, upl, now)
    if acoes:
        executar_acoes(api, st, acoes, now, msgs, simular)
    # 2. gerir a posicao (saida por tempo; stop confirmado)
    gerir(api, st, c, now, msgs, simular)
    # 3. portas e sinal novo (so no fecho de 4H e sem posicao)
    st["portas"] = portas(api, st, c, now, teste_oos, isolado)
    fechadas = [k for k, v in st["portas"].items() if not v["ok"]]
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    if st["aberta"] is None and now % H4 < 3600:
        cand = procurar(api, st, c, now)
        st["ultimo_sinal"] = cand
        if cand and cand.get("plano"):
            if fechadas or (st.get("bloqueio_dia") or {}).get(dia):
                evento(st, now, "sinal valido NAO executado: portas fechadas", portas=fechadas, sinal=cand["id"])
                msgs.append(f"🔒 Piloto OKX: sinal {cand['base']} (v2) não executado — portas fechadas: {', '.join(fechadas)}.")
            else:
                entrar(api, st, c, cand, now, msgs, simular)
    st["perdas"] = pp
    st["t"] = now
    st["simulacao"] = bool(simular)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    for m in msgs:
        enviar(m)
    return st, msgs


def _okx_exec_isolado():
    try:
        import okx_exec
        return bool(getattr(okx_exec, "PILOTO_ISOLADO", False))
    except Exception:
        return False


def procurar(api, st, c, now):
    """Primeiro sinal v2 valido na ultima vela de 4H fechada entre os X-Perps de cripto negociaveis (ordenados
    pelo volume); uma operacao de cada vez, nunca o mesmo sinal duas vezes."""
    xp = instrumentos(api)
    tick = {t["instId"]: t for t in api.pub("/api/v5/market/tickers", {"instType": "FUTURES"}) or []}
    ordem = sorted(xp, key=lambda b: -float((tick.get(xp[b]["inst"]) or {}).get("volCcy24h") or 0))
    rej = {}
    for b in ordem:
        v = velas4h(api, xp[b]["inst"], now)
        if len(v) < 40 or now - (v[-1]["t"] + H4) > H4:
            rej[b] = "dados insuficientes ou atrasados"
            continue
        s = sinal_v2(v)
        if not s:
            continue
        sid = f"{REGRA['id']}|{b}|{s['t']}"
        if sid in st["vistos"]:
            continue
        t = tick.get(xp[b]["inst"]) or {}
        bid, ask = float(t.get("bidPx") or 0), float(t.get("askPx") or 0)
        spread = 100 * (ask - bid) / ((ask + bid) / 2) if bid > 0 and ask > 0 else None
        if spread is None or spread > SPREAD_MAX_PCT:
            rej[b] = f"spread {spread}% acima de {SPREAD_MAX_PCT}%"
            st["vistos"].append(sid)
            continue
        pl = plano(s, REGRA["saida"]["k"], REGRA["saida"]["tp"])
        if ask >= pl["alvo"] or ask <= pl["stop"]:
            rej[b] = "preco atual ja fora do plano"
            st["vistos"].append(sid)
            continue
        pl["entrada"] = ask                                    # limite no melhor preco de venda (entra ja)
        dim, porque = dimensionar(pl, xp[b], c, spread, saldo=st.get("_saldo_usdc"))
        st["vistos"].append(sid)
        if not dim:
            rej[b] = porque
            continue
        return {"id": sid, "base": b, "inst": xp[b]["inst"], "sinal": s, "plano": pl, "dim": dim, "spread_pct": round(spread, 4),
                "tick": xp[b]["tickSz"], "rejeitados": rej}
    return {"rejeitados": rej} if rej else None


def entrar(api, st, c, cand, now, msgs, simular):
    d, pl = cand["dim"], cand["plano"]
    cl = f"{PREFIXO}{int(now)}"
    tk = float(cand["tick"])
    px = lambda x: f"{_passo(x, tk):.10f}".rstrip("0").rstrip(".")
    op = {"id": cand["id"], "clOrdId": cl, "inst": cand["inst"], "base": cand["base"], "versao": REGRA["id"],
          "t_sinal": cand["sinal"]["t"], "t_ordem": int(now), "preco_previsto": pl["entrada"], "stop": float(px(pl["stop"])),
          "alvo": float(px(pl["alvo"])), "contratos": d["contratos"], "alav": d["alav"], "risco_planeado": d["risco_total"],
          "nocional": d["nocional"], "custos_estimados": d["custos_estimados"], "spread_pct": cand["spread_pct"],
          "estado": "pendente", "prazo": int(now) + PRAZO_ENTRADA_S, "sair_em": None}
    if simular:
        op["estado"] = "simulada (sem ordem)"
        st["ops"].append(op)
        evento(st, now, "SIMULACAO: ordem nao enviada", op=op["id"])
        msgs.append(f"🧪 Piloto OKX (simulação): entraria em {cand['base']} LONG, {d['contratos']:g} contratos, {d['alav']}x.")
        return
    lv = api.priv("POST", "/api/v5/account/set-leverage", {"instId": cand["inst"], "lever": str(d["alav"]), "mgnMode": "isolated"})
    if (lv or {}).get("code") != "0":
        evento(st, now, "alavancagem recusada: sem ordem", resposta=str(lv)[:200])
        msgs.append(f"⚠️ Piloto OKX: a OKX recusou {d['alav']}x em {cand['base']}; nenhuma ordem enviada.")
        return
    r = api.priv("POST", "/api/v5/trade/order", {
        "instId": cand["inst"], "tdMode": "isolated", "side": "buy", "ordType": "limit", "px": px(pl["entrada"]),
        "sz": f"{d['contratos']:g}", "clOrdId": cl,
        "attachAlgoOrds": [{"slTriggerPx": px(pl["stop"]), "slOrdPx": "-1", "tpTriggerPx": px(pl["alvo"]), "tpOrdPx": "-1"}]})
    dd = ((r or {}).get("data") or [{}])[0]
    if (r or {}).get("code") != "0" or dd.get("sCode") not in (None, "0"):
        evento(st, now, "ordem recusada pela OKX", resposta=str(r)[:300])
        msgs.append(f"⚠️ Piloto OKX: ordem em {cand['base']} recusada pela OKX ({dd.get('sMsg') or (r or {}).get('msg')}).")
        return
    op["ordId"] = dd.get("ordId")
    st["aberta"] = op
    st["ops"].append(op)
    evento(st, now, "ordem ENVIADA (ainda nao executada)", op=op["id"], ordId=op["ordId"])
    msgs.append(f"📌 Piloto OKX: ordem limite LONG {cand['base']} enviada ({d['contratos']:g} contratos, {d['alav']}x isolada, "
                f"stop e objetivo anexados). Enviada não é executada: confirmo na volta seguinte.")


def reconciliar(api, st, now, msgs):
    """Estado da OKX para o instrumento do piloto: ordem (executada, parcial, cancelada), posicao, stop."""
    op = st.get("aberta")
    if not op or "simulada" in op.get("estado", ""):
        return {}
    o = api.priv("GET", f"/api/v5/trade/order?instId={op['inst']}&ordId={op.get('ordId')}")
    od = ((o or {}).get("data") or [{}])[0]
    pos = api.priv("GET", f"/api/v5/account/positions?instId={op['inst']}")
    pd = next((x for x in ((pos or {}).get("data") or []) if float(x.get("pos") or 0) != 0), None)
    upl = float(pd.get("upl") or 0) if pd else 0.0
    acc = float(od.get("accFillSz") or 0)
    if op["estado"] == "pendente":
        if acc > 0:
            op.update(estado="aberta", contratos_exec=acc, preco_efetivo=float(od.get("avgPx") or 0),
                      t_execucao=int(int(od.get("fillTime") or now * 1000) / 1000))
            op["slippage_pct"] = round(100 * (op["preco_efetivo"] / op["preco_previsto"] - 1), 4)
            op["sair_em"] = op["t_execucao"] + REGRA["saida"]["hold"] * H4
            parcial = od.get("state") == "partially_filled" or acc < op["contratos"]
            evento(st, now, "EXECUTADA" + (" parcialmente" if parcial else ""), op=op["id"], contratos=acc)
            msgs.append(f"✅ Piloto OKX: compra executada em {op['base']} a {op['preco_efetivo']:.6g} "
                        f"({acc:g}/{op['contratos']:g} contratos).")
            if parcial and od.get("state") == "partially_filled":
                api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
                evento(st, now, "resto da ordem parcial cancelado; risco recalculado para a quantidade efetiva")
                op["risco_planeado"] = round(op["risco_planeado"] * acc / op["contratos"], 4)
        elif now >= op["prazo"] or od.get("state") in ("canceled", "mmp_canceled"):
            if od.get("state") not in ("canceled", "mmp_canceled"):
                api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
            op["estado"] = "nao executada (cancelada)"
            st["aberta"] = None
            evento(st, now, "entrada nao executada no prazo: cancelada", op=op["id"])
            msgs.append(f"⏹️ Piloto OKX: entrada em {op['base']} não executada no prazo; cancelada.")
            return {"upl": 0.0}
    if op["estado"] == "aberta":
        if pd is None:                                       # fechou (stop, objetivo ou manual)
            fechar_contas(api, st, op, now, msgs)
            return {"upl": 0.0}
        a1 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={op['inst']}&ordType=conditional")
        a2 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={op['inst']}&ordType=oco")
        ok, mot = PROT.stop_cobre(((a1 or {}).get("data") or []) + ((a2 or {}).get("data") or []), abs(float(pd["pos"])), "LONG",
                                  op.get("preco_efetivo"))
        op["stop_confirmado"] = bool(ok)
        if not ok:
            evento(st, now, "POSICAO SEM STOP CONFIRMADO", motivos=mot)
            r = api.priv("POST", "/api/v5/trade/order-algo", {"instId": op["inst"], "tdMode": "isolated", "side": "sell",
                                                             "ordType": "conditional", "sz": str(abs(float(pd["pos"]))),
                                                             "reduceOnly": True, "slTriggerPx": str(op["stop"]), "slOrdPx": "-1"})
            if (r or {}).get("code") == "0":
                msgs.append(f"⚠️ Piloto OKX: {op['base']} estava sem stop confirmado; stop reposto (confirmo na volta seguinte).")
            else:
                api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
                st["bloqueio"] = {"t": int(now), "motivo": "stop nao colocado: posicao fechada por seguranca"}
                evento(st, now, "stop falhou: fecho de seguranca e piloto bloqueado")
                msgs.append(f"🛑 Piloto OKX: não consegui proteger {op['base']}; fechei a posição e bloqueei o piloto.")
    # posicoes orfas do piloto (instrumento do piloto aberto sem op seguida) - so reporta
    return {"upl": upl}


def fechar_contas(api, st, op, now, msgs):
    f = api.priv("GET", f"/api/v5/trade/fills-history?instType=FUTURES&instId={op['inst']}&limit=50")
    fills = [x for x in ((f or {}).get("data") or []) if int(x.get("ts") or 0) // 1000 >= op.get("t_execucao", 0)]
    vend = [x for x in fills if x.get("side") == "sell"]
    pnl = sum(float(x.get("fillPnl") or 0) for x in vend)
    fee = sum(float(x.get("fee") or 0) for x in fills)
    px_saida = (sum(float(x["fillPx"]) * float(x["fillSz"]) for x in vend) / sum(float(x["fillSz"]) for x in vend)) if vend else None
    liquido = pnl + fee
    op.update(estado="fechada", t_fecho=int(now), preco_saida=px_saida, pnl_bruto=round(pnl, 6), comissoes=round(fee, 6),
              pnl_liquido=round(liquido, 6), r=round(liquido / op["risco_planeado"], 3) if op["risco_planeado"] else None,
              duracao_h=round((now - op.get("t_execucao", now)) / 3600, 1),
              motivo_saida=("objetivo" if px_saida and px_saida >= op["alvo"] * 0.999 else
                            "stop" if px_saida and px_saida <= op["stop"] * 1.001 else "tempo/outro"))
    st["perda_realizada"] = round(st["perda_realizada"] + liquido, 6)
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    st["dias"][dia] = round(st["dias"].get(dia, 0.0) + liquido, 6)
    st["aberta"] = None
    evento(st, now, "FECHADA", op=op["id"], r=op["r"])
    msgs.append(f"🏁 Piloto OKX: {op['base']} fechada ({op['motivo_saida']}), {op['r']:+.2f}R.")


def gerir(api, st, c, now, msgs, simular):
    op = st.get("aberta")
    if not op or op.get("estado") != "aberta" or simular:
        return
    if op.get("sair_em") and now >= op["sair_em"]:
        api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
        evento(st, now, "saida por tempo (24 h) pedida; confirmo na volta seguinte", op=op["id"])
        msgs.append(f"⏱️ Piloto OKX: {op['base']} chegou às 24 h; pedi o fecho (reduce-only da posição isolada).")


def executar_acoes(api, st, acoes, now, msgs, simular):
    op = st.get("aberta")
    motivo = (st["bloqueio"] or st["suspenso"] or {}).get("motivo") or "perda do dia"
    if op and op.get("estado") == "pendente" and "cancelar_entradas" in acoes and not simular:
        api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op.get("ordId")})
        op["estado"] = "cancelada por limite"
        st["aberta"] = None
    if op and op.get("estado") == "aberta" and "fechar_posicao" in acoes and not simular:
        api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
    evento(st, now, "LIMITE ATINGIDO", acoes=acoes, motivo=motivo)
    msgs.append(f"🛑 Piloto OKX: {motivo}. Ações: {', '.join(acoes)}.")


# ------------------------------------------------------------------ main -------------------------------------------
class ApiReal:
    def __init__(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import okx_exec as E
        import okx_agente as A
        self._priv, self._pub = E.privado, A.get

    def priv(self, metodo, path, corpo=None):
        return self._priv(metodo, path, corpo)

    def pub(self, path, params=None):
        import urllib.parse
        return self._pub(path + ("?" + urllib.parse.urlencode(params) if params else ""))


if __name__ == "__main__":
    pasta = sys.argv[1]
    simular = "--simular" in sys.argv
    teste = None
    tp = os.path.join(pasta, "teste_oos.json")
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            teste = json.load(f).get("teste")
    try:
        from engine import alerts
        enviar = alerts.send
    except Exception:
        enviar = lambda m: None
    st, msgs = ciclo(ApiReal(), pasta, simular=simular, teste_oos=teste, enviar=enviar)
    print(json.dumps({"portas": st["portas"], "aberta": bool(st["aberta"]), "bloqueio": st["bloqueio"],
                      "suspenso": st["suspenso"], "ops": len(st["ops"]), "simulacao": st["simulacao"]}, ensure_ascii=False))
