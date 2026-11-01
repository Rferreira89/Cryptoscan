"""Papel ao vivo da "compra no panico com ordem limite" (H23, 29/10; OK do Rui: "so em papel").

Regra exatamente como no estudo (backtest/estudos/h23_ordens_limite.py, variante L10):
  sinal (fecho de vela de 4H): o ultimo financiamento ja pago e negativo e esta no percentil 5 ou abaixo
  dos 270 anteriores (~90 dias), e a moeda caiu 10% ou mais em 3 dias (18 velas).
  ordem limite 1% abaixo do fecho do sinal, valida 2 velas (8 h); sem execucao, nao ha operacao.
  stop 2 ATR (media de 42 velas), objetivo 2R, saida ao fim de 18 velas.
  custos: 0,10% na entrada e no objetivo (ordem limite), 0,25% no stop e na saida por tempo.
No historico de 2024-26 deu +0,08R por operacao nas duas metades (acima do acaso, p=0,000), mas nao
passou o criterio de +0,15R. Por isso: SO PAPEL. Nao envia ordens nem mensagens. Dinheiro real so com
o criterio unico de 28/10 cumprido e autorizacao do Rui.
"""
H4 = 14400
OFFSET, VALIDA, HOLD, ATR_N = 0.01, 2, 18, 42
F_LIM, F_MKT = 0.0010, 0.0025


def _pct5(hist):
    s = sorted(hist)
    k = 0.05 * (len(s) - 1)
    i = int(k)
    return s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (k - i)     # como numpy.percentile (linear)


def sinal(c4, funding):
    """Plano pendente para a ultima vela fechada, ou None. funding: [(t_s, taxa)] por ordem."""
    if not c4 or len(c4) < max(ATR_N, 19) + 1 or not funding:
        return None
    b = c4[-1]
    conhecidos = [f for f in funding if f[0] <= b["t"] + H4]
    if len(conhecidos) < 271:
        return None
    fv = conhecidos[-1][1]
    if fv is None or fv >= 0 or fv > _pct5([f[1] for f in conhecidos[-271:-1]]):
        return None
    if b["c"] / c4[-19]["c"] - 1 > -0.10:
        return None
    trs = [max(c4[i]["h"], c4[i - 1]["c"]) - min(c4[i]["l"], c4[i - 1]["c"]) for i in range(len(c4) - ATR_N, len(c4))]
    return {"t_sig": b["t"], "lim": b["c"] * (1 - OFFSET), "atr": sum(trs) / ATR_N, "funding": fv,
            "queda_3d_pct": round((b["c"] / c4[-19]["c"] - 1) * 100, 1)}


BTC_QUEDA = -0.03          # (01/11) H28: o panico de uma moeda sozinha correu pior do que o do mercado todo


def tipo_panico(c4_btc, t_sig):
    """'mercado' se o BTC caiu 3% ou mais nas 6 velas de 4H ate ao sinal, 'isolado' se nao, None sem dados."""
    if not c4_btc:
        return None
    ts = [b["t"] for b in c4_btc]
    if t_sig not in ts:
        return None
    k = ts.index(t_sig)
    if k < 6:
        return None
    return "mercado" if c4_btc[k]["c"] / c4_btc[k - 6]["c"] - 1 <= BTC_QUEDA else "isolado"


def _r(e, px, risk, fout):
    return round(((px - e) - (F_LIM * e + fout * px)) / risk, 3)


def _seguir(op, barras):
    """Avanca uma operacao aberta pelas velas novas. Devolve (R, motivo) quando fecha."""
    for b in barras:
        if b["t"] <= op.get("visto", 0):
            continue
        op["visto"] = b["t"]
        primeira = b["t"] == op["t_fill"]
        if b["l"] <= op["stop"] and (not primeira or b["o"] > op["stop"]):
            return _r(op["entrada"], op["stop"], op["risco"], F_MKT), "stop"
        if b["h"] >= op["alvo"]:
            return _r(op["entrada"], op["alvo"], op["risco"], F_LIM), "objetivo"
        if b["t"] >= op["t_fill"] + (HOLD - 1) * H4:
            return _r(op["entrada"], b["c"], op["risco"], F_MKT), "tempo"
    return None


def update(state, c4s, eu, now):
    st = state.setdefault("papel_panico", {"pend": {}, "abertas": {}, "fechadas": [], "perdidas": 0, "desde": int(now)})
    pend, ab = st["pend"], st["abertas"]
    for op in ab.values():                    # (01/11) as abertas antes da etiqueta tambem ficam marcadas
        if "tipo" not in op:
            op["tipo"] = tipo_panico((c4s or {}).get("BTC"), op.get("t_sig"))
    for a, c4 in (c4s or {}).items():
        if not c4:
            continue
        # ordem pendente: executa se o minimo tocar no limite nas 2 velas seguintes
        p = pend.get(a)
        if p:
            for b in c4:
                if p["t_sig"] < b["t"] <= p["t_sig"] + VALIDA * H4 and b["l"] <= p["lim"]:
                    e = min(p["lim"], b["o"])
                    stop = e - 2 * p["atr"]
                    if e - stop > 0:
                        _aviso(st, f"📝 Papel — compra no pânico executada em {a} a {e:.6g} (stop {stop:.6g}, "
                                   f"objetivo {e + 2 * (e - stop):.6g}, saída em 72 h). Só papel, sem dinheiro.")
                        ab[a] = {"entrada": e, "stop": stop, "alvo": e + 2 * (e - stop), "risco": e - stop,
                                 "t_sig": p["t_sig"], "t_fill": b["t"], "funding": p["funding"],
                                 "queda_3d_pct": p["queda_3d_pct"], "tipo": p.get("tipo")}
                    pend.pop(a)
                    break
            else:
                if c4[-1]["t"] >= p["t_sig"] + VALIDA * H4:
                    pend.pop(a)
                    st["perdidas"] = st.get("perdidas", 0) + 1
        op = ab.get(a)
        if op:
            fim = _seguir(op, [b for b in c4 if b["t"] >= op["t_fill"]])
            if fim:
                _aviso(st, f"📝 Papel — compra no pânico em {a} fechada ({fim[1]}){' — pânico ' + op['tipo'] if op.get('tipo') else ''}: {fim[0]:+.2f}R. "
                           f"Já vão {len(st['fechadas']) + 1} operações em papel.")
                st["fechadas"].append({"asset": a, "t_sig": op["t_sig"], "t_fill": op["t_fill"], "entrada": op["entrada"],
                                       "r": fim[0], "motivo": fim[1], "t_fim": op.get("visto"), "tipo": op.get("tipo")})
                ab.pop(a)
        if a not in pend and a not in ab and c4[-1]["t"] > st.setdefault("ultimo", {}).get(a, 0):
            s = sinal(c4, ((eu or {}).get("moedas") or {}).get(a, {}).get("funding"))
            if s:
                s["tipo"] = tipo_panico((c4s or {}).get("BTC"), s["t_sig"])
                pend[a] = s
                st["ultimo"][a] = s["t_sig"]
        elif a in ab and c4[-1]["t"] > st.setdefault("ultimo_real", {}).get(a, 0):
            # (31/10, Rui: "Quero que haja operacoes quando houver uma oportunidade") uma posicao em papel na
            # moeda nao pode impedir um sinal novo para o dinheiro real (a conta real e outra)
            s = sinal(c4, ((eu or {}).get("moedas") or {}).get(a, {}).get("funding"))
            st["ultimo_real"][a] = c4[-1]["t"]
            if s:
                s["tipo"] = tipo_panico((c4s or {}).get("BTC"), s["t_sig"])
                st.setdefault("pend_real", {})[a] = s
    pr_ = st.setdefault("pend_real", {})
    for a in [k for k, v in pr_.items() if (c4s or {}).get(k) and c4s[k][-1]["t"] >= v["t_sig"] + VALIDA * H4]:
        pr_.pop(a)
    del st["fechadas"][:-500]
    return resumo(st)


def _aviso(st, txt):
    st.setdefault("avisos", []).append(txt)
    del st["avisos"][:-20]


def pop_avisos(state):
    """(30/10, Rui: "quero que cada operacao me seja avisada") mensagens novas para o Telegram."""
    st = state.get("papel_panico") or {}
    out, st["avisos"] = list(st.get("avisos") or []), []
    return out


# ---------- dinheiro real (30/10): so com PANICO_L10 em "real_autorizados" ----------
ESTRATEGIA = "PANICO_L10"
MAX_REAIS = 2                       # no maximo 2 compras no panico reais abertas (caem juntas nas quedas)
TENTATIVAS = 3
REPETIR_S = 900


def real(state, precos, cfg, now):
    """Dinheiro real da compra no panico (so com autorizacao, execucao pronta e modo automatico).

    (01/11, Rui: "na corretora nao tenho nenhuma ordem limite") a ordem limite fica MESMO na Bybit, como no
    estudo: quando nasce um sinal, o executor poe a ordem limite com stop e objetivo anexados; se ha varios
    sinais, so o mais perto do preco (o saldo e de uma operacao de cada vez). O scanner pede a verificacao
    quando o preco toca no limite (e de 30 em 30 min), o cancelamento quando a ordem caduca e o fecho por
    tempo (72 h depois da execucao) ou quando a Bybit ja executou o stop ou o objetivo."""
    from . import acelerado, auto, execucao, promo
    st = state.get("papel_panico")
    if not st:
        return []
    rl = st.setdefault("real", {})
    estados = state.get("auto_ops") or {}
    pedidos = []

    def pedir(acao, oid):
        if execucao.request(state, acao, oid, now):
            pedidos.append((acao, oid))
            return True
        return False
    for oid, p in rl.items():
        p["estado"] = estados.get(oid)
        if p["estado"] is None and now - p["criado"] > 3600:   # o executor nunca respondeu: nao fica preso
            p["estado"] = "recusada"
        ex_ = p.get("exec") or {}
        if ex_.get("sair_em"):
            p["sair_em"] = ex_["sair_em"]
        px = (precos or {}).get(p["asset"])
        if p["estado"] == "pendente":
            # (01/11, SEI) ordem posta sem a alavancagem pedida antes de existir a descida passo a passo: refaz uma vez
            pedida = (p.get("alav") or [1])[0]
            if (ex_.get("alavancagem") or 1) < pedida and not p.get("refeita") and now < p["valido_ate"] - 600:
                if pedir("panico_refazer", oid):
                    p["refeita"] = int(now)
                continue
            if now >= p["valido_ate"]:
                if now - (p.get("pediu_cancelar") or 0) >= REPETIR_S and pedir("panico_cancelar", oid):
                    p["pediu_cancelar"] = int(now)
            elif now - (p.get("verif") or 0) >= (300 if px and px <= p["lim"] * 1.002 else 1800):
                if pedir("panico_verificar", oid):
                    p["verif"] = int(now)
        if p["estado"] == "aberta" and not p.get("pediu_fecho"):
            motivo = None
            if p.get("sair_em") and now >= p["sair_em"]:
                motivo = "tempo (72 h)"
            elif px and ex_.get("stop") and px <= ex_["stop"]:
                motivo = "stop"                    # a ordem de stop da Bybit ja disparou: o fecho limpa o resto
            elif px and ex_.get("alvo") and px >= ex_["alvo"]:
                motivo = "objetivo"
            if motivo and pedir("fechar", oid):
                p.update(pediu_fecho=int(now), motivo_fecho=motivo, px_fecho=px)
        if p["estado"] == "fechada" and not p.get("analisada") and ex_.get("entrada"):
            p["analisada"] = True
            _aviso(st, analise(p, st))
            if p.get("r_conta") is not None:
                st["composto"] = round(max(0.05, st.get("composto", 1.0) * (1 + p["r_conta"])), 4)
    for oid in [k for k, p in rl.items() if p.get("estado") in ("fechada", "recusada", "cancelada")
                and now - p["criado"] > 30 * 86400]:
        rl.pop(oid)
    autorizada = promo.AUTORIZADOS is not None and ESTRATEGIA in promo.AUTORIZADOS
    if not autorizada or not execucao.READY or not auto.active(state) or state.get("halt"):
        return pedidos
    pr = (cfg or {}).get("panico_real") or {}
    tudo = pr.get("modo") == "tudo"
    max_reais = 1 if tudo else MAX_REAIS
    abertas_todas = sum(1 for v in estados.values() if v == "aberta")
    minhas = sum(1 for p in rl.values() if p.get("estado") in (None, "pendente", "aberta") and not p.get("pediu_fecho"))
    if minhas >= max_reais or abertas_todas >= int(cfg.get("max_open_positions") or 4):
        return pedidos
    cands = []
    for a, pd in {**(st.get("pend_real") or {}), **(st.get("pend") or {})}.items():
        oid = f"PANICO-{a}-{pd['t_sig']}"
        valido = pd["t_sig"] + (1 + VALIDA) * H4
        px = (precos or {}).get(a)
        if not px or now >= valido - 300:
            continue
        ant = rl.get(oid)
        if ant:
            # (01/11, TIA e CRV) recusada por erro da Bybit: volta a tentar 15 min depois, no maximo 3 vezes
            mot = str(((ant.get("exec") or {}).get("motivo")) or "")
            if not (ant.get("estado") == "recusada" and mot.startswith("a Bybit recusou")
                    and ant.get("tentativas", 1) < TENTATIVAS and now - ant["criado"] >= REPETIR_S):
                continue
        cands.append((px / pd["lim"] - 1, a, pd, oid, valido))
    for _, a, pd, oid, valido in sorted(cands)[:max(0, max_reais - minhas)]:
        cc = {} if tudo else acelerado.cfg_para(ESTRATEGIA, state, cfg)
        risco = cc.get("max_risk_usdc")
        if not risco and not tudo:
            continue
        rl[oid] = {"asset": a, "symbol": f"{a}{cfg.get('quote') or 'USDC'}", "lim": pd["lim"], "atr": pd["atr"],
                   "risco_usdc": risco, "t_sig": pd["t_sig"], "valido_ate": valido, "sair_em": None,
                   "criado": int(now), "tipo": pd.get("tipo"), "acelerado_pct": cc.get("acelerado_pct"),
                   "tentativas": (rl.get(oid) or {}).get("tentativas", 0) + 1,
                   # (31/10, Rui: "leva-me esses 20$ a outro patamar") juros compostos: o teto cresce (e encolhe)
                   # com o resultado das operacoes reais fechadas; um deposito novo nao entra sozinho
                   "tudo_usdc": round(float(pr.get("max_usdc") or 0) * (st.get("composto", 1.0) if pr.get("composto") else 1.0), 2)
                   if tudo else None,
                   "alav": list(pr.get("alavancagem") or []) if tudo and pr.get("alavancagem") else None}
        pedir("panico_ordem", oid)
    return pedidos


def analise(p, st):
    """(31/10, Rui: "Quero que o programa e tu com meu mentor analise cada operacao") leitura do fecho."""
    ex_ = p.get("exec") or {}
    e, stop = ex_["entrada"], ex_.get("stop") or 0
    motivo = p.get("motivo_fecho") or ex_.get("motivo") or "fecho"
    saida = ex_.get("saida") or {"stop": stop, "objetivo": ex_.get("alvo")}.get(motivo) or p.get("px_fecho") or e
    risco = e - stop if stop and e > stop else None
    r = (saida - e) / risco if risco else None
    lev = ex_.get("alavancagem") or 1
    var = 100 * (saida / e - 1)
    p["r_conta"] = round((saida / e - 1 - 0.0035) * lev, 4)      # variacao da conta (comissoes incluidas)
    horas = ((ex_.get("fechado") or 0) - (ex_.get("criado") or 0)) / 3600 if ex_.get("fechado") else None
    papel = next((x for x in reversed(st.get("fechadas") or []) if x.get("asset") == p["asset"]
                  and abs((x.get("t_sig") or 0) - p["t_sig"]) <= 3 * H4), None)
    L = [f"🧠 Análise — compra no pânico em {p['asset']} (dinheiro real)",
         f"Saída por {motivo}: {var:+.1f}% no preço"
         + (f", {var * lev:+.0f}% na conta com {lev}x" if lev > 1 else "")
         + (f" ({r:+.2f}R)" if r is not None else "") + (f", {horas:.0f} h aberta." if horas else ".")]
    if r is not None:
        if r >= 1.5:
            L.append("Leitura: o ressalto depois do pânico chegou ao objetivo, como a estratégia procura.")
        elif r <= -0.8:
            L.append("Leitura: a queda continuou depois do sinal e o stop protegeu a conta. Faz parte: no histórico, "
                     "cerca de metade das operações perde.")
        else:
            L.append("Leitura: sem ressalto nem queda forte; saiu perto da entrada.")
    if papel:
        L.append(f"O papel na mesma moeda deu {papel['r']:+.2f}R ({papel['motivo']}).")
    rs = [x["r"] for x in st.get("fechadas") or []]
    if rs:
        L.append(f"Prova em papel até agora: {len(rs)} operações, média {sum(rs) / len(rs):+.2f}R.")
    f = st.get("composto", 1.0) * (1 + p["r_conta"])
    L.append(f"Conta do pânico desde o início: {100 * (f - 1):+.0f}% (a próxima operação usa esse valor).")
    return "\n".join(L)


def resumo(st):
    fc = (st or {}).get("fechadas") or []
    rs = [x["r"] for x in fc]
    return {"regra": "compra no pânico com ordem limite 1% abaixo (H23, só papel)", "desde": (st or {}).get("desde"),
            "n": len(rs), "r_medio": round(sum(rs) / len(rs), 3) if rs else None,
            "acerto_pct": round(100 * sum(1 for r in rs if r > 0) / len(rs)) if rs else None,
            "abertas": sorted((st or {}).get("abertas") or {}), "pendentes": sorted((st or {}).get("pend") or {}),
            # (01/11) ordens limite a espera (papel e real), para os agentes do escritorio mostrarem a distancia
            "ordens": sorted([{"asset": a, "lim": v["lim"], "ate": v["t_sig"] + (1 + VALIDA) * H4}
                              for a, v in {**((st or {}).get("pend_real") or {}), **((st or {}).get("pend") or {})}.items()],
                             key=lambda x: x["asset"]),
            "ordens_nao_executadas": (st or {}).get("perdidas", 0), "ultimas": fc[-10:],
            "real_composto_pct": round(100 * ((st or {}).get("composto", 1.0) - 1), 1),
            "por_tipo": {t: {"n": len(v), "r_medio": round(sum(v) / len(v), 3) if v else None}
                         for t in ("mercado", "isolado") for v in [[x["r"] for x in fc if x.get("tipo") == t]]},
            "meta": "60 operações ou 3 meses com média positiva antes de qualquer proposta de dinheiro real"}
