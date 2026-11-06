"""(06/11, P3, preparacao isolada; NAO LIGADO) Registo unico de desempenho de todas as estrategias.

Cada operacao fechada passa a uma forma comum, SEM perder nada: o registo original vai inteiro em "bruto".
Origens rigorosamente separadas: "real" (executada com dinheiro), "papel" (simulada ao vivo), "sombra" (o que a
estrategia faria, ao lado de outra), "investigacao" (backtest ou estudo). As metricas sao sempre calculadas por
(estrategia, origem): misturar origens numa so conta e recusado.

So le os ficheiros que os agentes ja publicam (state.json, okx.json, okx_tfshort.json); nao muda nenhum subsistema.

Forma comum: estrategia, origem, corretora, moeda, lado, t_entrada, t_saida, R (None se a fonte nao o tem),
motivo, regime, custos {comissao, spread, deslize, financiamento} (None quando a fonte nao separa), fonte,
id_origem, bruto."""
import copy

ORIGENS = ("real", "papel", "sombra", "investigacao")
CUSTOS = ("comissao", "spread", "deslize", "financiamento")
SEMANA = 7 * 86400


def op(estrategia, origem, corretora, moeda, fonte, id_origem, bruto, R=None, lado=None, t_entrada=None,
       t_saida=None, motivo=None, regime=None, custos=None):
    if origem not in ORIGENS:
        raise ValueError(f"origem invalida: {origem}")
    c = {k: None for k in CUSTOS}
    c.update(custos or {})
    return {"estrategia": estrategia, "origem": origem, "corretora": corretora, "moeda": moeda,
            "lado": (lado or "").upper() or None, "t_entrada": t_entrada, "t_saida": t_saida,
            "R": None if R is None else float(R), "motivo": motivo, "regime": regime, "custos": c,
            "fonte": fonte, "id_origem": str(id_origem), "bruto": copy.deepcopy(bruto)}


# ---------- adaptadores (um por subsistema; so leitura) ----------
def do_ledger(state):
    """Sinais do scanner (Bybit). executed=True -> real (real_r); fechados sem execucao -> sombra (result_r): e o que a
    estrategia real teria feito, mas a ordem nao chegou a ser executada."""
    out = []
    for i, r in enumerate(state.get("ledger") or []):
        if r.get("status") != "CLOSED":
            continue
        real = r.get("executed") is True
        rid = r.get("id") or ""
        estr = r.get("strategy") or (rid.split("-")[1] if rid.count("-") >= 2 else "?")
        out.append(op(estr, "real" if real else "sombra", "bybit", r.get("asset"), "state.ledger",
                      r.get("id") or f"ledger-{i}", r, R=r.get("real_r") if real else r.get("result_r"),
                      lado=r.get("side"), t_entrada=r.get("opened_at"), t_saida=r.get("closed_at"),
                      motivo=r.get("reason"), regime=r.get("regime")))
    return out


def _lista_fechadas(xs, estr, origem, corretora, fonte, chave_r="r", t0="opened_at", t1="closed_at", motivo="reason"):
    out = []
    for i, r in enumerate(xs or []):
        out.append(op(r.get("strategy") or estr, origem, corretora, r.get("asset"), fonte,
                      f"{fonte}-{r.get('asset')}-{r.get(t0) or r.get('t_sig')}-{i}", r, R=r.get(chave_r),
                      lado=r.get("side") or r.get("lado"), t_entrada=r.get(t0) or r.get("t_sig"),
                      t_saida=r.get(t1) or r.get("t_fim"), motivo=r.get(motivo) or r.get("motivo")))
    return out


def do_state_papel(state):
    """Subsistemas de papel do scanner (Bybit)."""
    out = []
    pp = state.get("papel_panico") or {}
    out += _lista_fechadas(pp.get("fechadas"), "PANICO_BYBIT", "papel", "bybit", "state.papel_panico",
                           t0="t_fill", t1="t_fim", motivo="motivo")
    out += _lista_fechadas((state.get("paper_trend") or {}).get("closed"), "TREND_DAILY", "papel", "bybit",
                           "state.paper_trend", t0="entry_t", t1="exit_t")
    out += _lista_fechadas((state.get("paper_shadow") or {}).get("closed"), "SOMBRA", "sombra", "bybit", "state.paper_shadow")
    for nome, v in (state.get("paper_ring") or {}).items():
        out += _lista_fechadas((v or {}).get("closed"), nome, "papel", "bybit", f"state.paper_ring.{nome}")
    for g, v in ((state.get("paper_bounce") or {}).get("geo") or {}).items():
        out += _lista_fechadas((v or {}).get("closed"), f"BOUNCE_{g}", "papel", "bybit", f"state.paper_bounce.{g}")
    pf = state.get("papel_fases") or {}
    for fase in ("lateral", "subida"):
        out += _lista_fechadas((pf.get(fase) or {}).get("fechadas"), f"FASES_{fase.upper()}", "papel", "bybit",
                               f"state.papel_fases.{fase}")
    return out


def do_okx(okx):
    """Agente OKX: real (historico das ordens reais, R calculado a partir de entrada/stop/saida) e papel (H40, H46)."""
    out = []
    for i, h in enumerate((okx.get("real") or {}).get("hist") or []):
        if h.get("estado") != "fechada":
            continue                                        # canceladas nao sao operacoes
        R = None
        e, s, x = h.get("entrada"), h.get("stop"), h.get("saida")
        if e and s and x and e != s:
            R = round((x - e) / (e - s), 4)                 # long (o okx_exec atual so compra)
        estr = "H46" if h.get("estrategia") == "recuo" or h.get("tipo") == "recuo" else "H40"
        out.append(op(estr, "real", "okx", h.get("asset"), "okx.real.hist", h.get("ordId") or f"okx-{i}", h, R=R,
                      lado="LONG", t_entrada=h.get("t_fill"), t_saida=h.get("fechado"), motivo=h.get("motivo")))
    out += _lista_fechadas(okx.get("fechadas"), "H40", "papel", "okx", "okx.fechadas", t0="t_sig", t1="t_fim")
    out += _lista_fechadas((okx.get("recuo") or {}).get("fechadas"), "H46", "papel", "okx", "okx.recuo.fechadas",
                           t0="t_sig", t1="t_fim")
    return out


def do_tfshort(st):
    """Paper TF-SHORT: os dois registos ficam como estrategias separadas (sinais teoricos vs conta executavel)."""
    out = []
    for livro, nome in (("sinais", "TF-SHORT sinais"), ("conta", "TF-SHORT conta")):
        for i, r in enumerate((st.get(livro) or {}).get("fechadas") or []):
            custos = {"financiamento": r.get("fund_usd")} if livro == "conta" else {}
            if livro == "conta" and r.get("custos_usd") is not None:
                custos["comissao"] = r.get("custos_usd")   # o modulo junta comissao+deslize+spread num so valor
            out.append(op(nome, "papel", "okx", r.get("moeda"), f"okx_tfshort.{livro}",
                          f"{livro}-{r.get('moeda')}-{r.get('t')}-{i}", r, R=r.get("R"), lado="SHORT",
                          t_entrada=r.get("t"), t_saida=r.get("t_saida"), motivo=r.get("motivo"),
                          regime=None, custos=custos))
    return out


def de_lista(ops, estrategia, origem="investigacao", corretora=None, fonte="investigacao"):
    """Operacoes de um backtest/estudo (lista de dicts com R) como origem 'investigacao'."""
    return [op(estrategia, origem, corretora, o.get("a") or o.get("moeda"), fonte, f"{fonte}-{i}", o,
               R=o.get("R"), lado=o.get("lado"), t_entrada=o.get("te"), t_saida=o.get("ts"), regime=o.get("regime"))
            for i, o in enumerate(ops)]


# ---------- metricas uniformes ----------
def metricas(ops):
    """Metricas de UMA estrategia numa UMA origem. Operacoes sem R contam em 'sem_r' e ficam fora das contas de R."""
    origens = {o["origem"] for o in ops}
    if len(origens) > 1:
        raise ValueError(f"origens misturadas: {sorted(origens)} (real e simulado nunca se somam)")
    rs = [o["R"] for o in ops if o["R"] is not None]
    ts = [o["t_saida"] or o["t_entrada"] for o in ops if (o["t_saida"] or o["t_entrada"])]
    eq = pk = dd = 0.0
    for o in sorted((o for o in ops if o["R"] is not None), key=lambda o: o["t_saida"] or o["t_entrada"] or 0):
        eq += o["R"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    ganhos, perdas = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    semanas = max(1.0, (max(ts) - min(ts)) / SEMANA) if len(ts) > 1 else 1.0
    custos = {k: (round(sum(o["custos"][k] for o in ops if o["custos"][k] is not None), 6)
                  if any(o["custos"][k] is not None for o in ops) else None) for k in CUSTOS}

    def grupo(chave):
        g = {}
        for o in ops:
            if o["R"] is not None:
                g.setdefault(o[chave] or "?", []).append(o["R"])
        return {k: {"n": len(v), "soma_r": round(sum(v), 4), "media_r": round(sum(v) / len(v), 4)} for k, v in sorted(g.items())}
    return {"origem": next(iter(origens)) if origens else None, "fechadas": len(ops), "com_r": len(rs),
            "sem_r": len(ops) - len(rs), "soma_r": round(sum(rs), 4), "expectativa_r": round(sum(rs) / len(rs), 4) if rs else None,
            "profit_factor": round(ganhos / perdas, 3) if perdas else (None if not ganhos else float("inf")),
            "queda_max_r": round(dd, 4), "acerto_pct": round(100 * sum(1 for r in rs if r > 0) / len(rs), 1) if rs else None,
            "por_semana": round(len(ops) / semanas, 2), "custos": custos, "por_moeda": grupo("moeda"), "por_regime": grupo("regime")}


def tabela(ops):
    """{(estrategia, origem): metricas} para tudo o que foi migrado."""
    g = {}
    for o in ops:
        g.setdefault((o["estrategia"], o["origem"]), []).append(o)
    return {k: metricas(v) for k, v in sorted(g.items())}


# ---------- prova de preservacao ----------
def reconciliar(fontes, ops):
    """Para cada fonte: quantos registos fechados tinha o original e quantos ficaram, soma de R original vs migrada,
    e se cada registo original esta intacto em 'bruto'. fontes: {fonte: (lista_original, chave_r)}."""
    rel = {}
    for fonte, (orig, chave_r) in fontes.items():
        mig = [o for o in ops if o["fonte"] == fonte]
        soma_o = round(sum((x.get(chave_r) or 0) for x in orig if isinstance(x.get(chave_r), (int, float))), 6)
        soma_m = round(sum((o["bruto"].get(chave_r) or 0) for o in mig if isinstance(o["bruto"].get(chave_r), (int, float))), 6)
        intactos = sum(1 for o, x in zip(mig, orig) if o["bruto"] == x)
        rel[fonte] = {"originais": len(orig), "migrados": len(mig), "soma_r_original": soma_o, "soma_r_migrada": soma_m,
                      "intactos": intactos, "ok": len(orig) == len(mig) == intactos and soma_o == soma_m}
    return rel
