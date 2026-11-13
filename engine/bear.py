"""(13/11, ordem do Rui, D1) BEAR e ANALYST deterministicos, em OBSERVACAO: nunca bloqueiam nem mudam uma decisao.

BEAR: para cada sinal com plano (executado ou nao), procura razoes objetivas contra, so com dados do momento:
  grupo         >= 3 sinais da mesma estrategia na mesma vela (apostas correlacionadas)
  funding       o financiamento joga contra o lado (SHORT com funding < 0: os vendidos pagam; LONG com > 0,03%/8h)
  oi            open interest a 24h contra a ideia (SHORT com OI a cair > 5% e preco a cair: venda ja esgotada;
                LONG com OI a cair > 5% e preco a subir: subida so de fecho de vendas)
  stop_largo    distancia ao stop acima do percentil 90 dos planos anteriores da estrategia (>= 20 planos)
Cada objecao fica com o valor, a fonte e a hora.

ANALYST: responde a cada objecao com a historia da propria estrategia: R/op das operacoes (reais, papel e sombra
das rejeitadas) que tinham essa objecao contra as que nao tinham. Com menos de 20 casos de cada lado diz
"amostra insuficiente" e nada mais: nunca transforma opiniao em evidencia.
Passar uma objecao a filtro bloqueante exige, depois, diferenca fora da amostra com Holm e robustez (nao e feito aqui).
Sem dinheiro: so %, R e contagens."""
TF = 14400
MIN_N = 20
MAX_REG = 5000


def _st(state):
    st = state.setdefault("bear", {})
    st.setdefault("registos", [])
    return st


def objecoes(cand, k_grupo, stops_hist, now):
    """Lista de objecoes [{codigo, texto, valor, fonte, t}] para um candidato (dict com side, deriv, stop_pct)."""
    out = []
    side, dv = cand.get("side") or "LONG", cand.get("deriv") or {}

    def o(c, txt, v, fonte):
        out.append({"codigo": c, "texto": txt, "valor": v, "fonte": fonte, "t": int(now)})
    if k_grupo >= 3:
        o("grupo", f"{k_grupo} sinais da mesma estratégia nesta vela: apostas correlacionadas", k_grupo, "motor de sinais")
    fr = dv.get("funding_rate")
    if fr is not None:
        frp = float(fr) * 100 if abs(float(fr)) < 0.05 else float(fr)       # fracao ou % por 8 h
        if side == "SHORT" and frp < 0:
            o("funding", f"financiamento {frp:.4f}%/8h: os vendidos pagam", round(frp, 5), dv.get("venue") or "derivados")
        elif side == "LONG" and frp > 0.03:
            o("funding", f"financiamento {frp:.4f}%/8h: os comprados pagam muito", round(frp, 5), dv.get("venue") or "derivados")
    oi, pc = dv.get("oi_chg_24h_pct"), dv.get("price_chg_24h_pct")
    if oi is not None and pc is not None:
        if side == "SHORT" and oi < -5 and pc < 0:
            o("oi", f"OI {oi:+.1f}% e preço {pc:+.1f}% em 24 h: venda já esgotada?", round(oi, 2), dv.get("venue") or "derivados")
        elif side == "LONG" and oi < -5 and pc > 0:
            o("oi", f"OI {oi:+.1f}% e preço {pc:+.1f}% em 24 h: subida de fecho de vendas", round(oi, 2), dv.get("venue") or "derivados")
    sp = cand.get("stop_pct")
    if sp is not None and len(stops_hist) >= MIN_N:
        p90 = sorted(stops_hist)[int(0.9 * (len(stops_hist) - 1))]
        if sp > p90:
            o("stop_largo", f"stop a {sp:.1f}%, acima do percentil 90 da estratégia ({p90:.1f}%)", round(sp, 3),
              "planos anteriores")
    return out


def _resultados(state):
    """{chave: R} das operacoes fechadas: reais executadas, papel e sombra das rejeitadas."""
    out = {}
    for r in state.get("ledger") or []:
        if r.get("status") == "CLOSED" and r.get("result_r") is not None and r.get("issued_at"):
            t = int(r["issued_at"]) // TF * TF
            for tt in (t, t - TF):
                out.setdefault(f"{r.get('asset')}|{r.get('strategy')}|{tt}", float(r.get("real_r") or r["result_r"]))
    for f in ((state.get("sombra_rejeitadas") or {}).get("fechadas") or []):
        if f.get("r") is not None:
            out.setdefault(f.get("chave"), float(f["r"]))
    return out


def analista(state, estrategia, codigo):
    rs = _resultados(state)
    com, sem = [], []
    for reg in _st(state)["registos"]:
        if reg.get("strategy") != estrategia or reg.get("chave") not in rs:
            continue
        (com if any(o["codigo"] == codigo for o in reg.get("objecoes") or []) else sem).append(rs[reg["chave"]])
    res = {"n_com": len(com), "n_sem": len(sem),
           "r_com": round(sum(com) / len(com), 3) if com else None,
           "r_sem": round(sum(sem) / len(sem), 3) if sem else None}
    if len(com) < MIN_N or len(sem) < MIN_N:
        res["veredicto"] = f"amostra insuficiente ({len(com)} com, {len(sem)} sem; mínimo {MIN_N} de cada)"
    else:
        res["veredicto"] = (f"com a objeção {res['r_com']:+.3f}R/op contra {res['r_sem']:+.3f}R/op sem ela "
                            "(só observação: filtro bloqueante exige teste fora da amostra com Holm)")
    return res


def observar(state, cands, deriv, now):
    """cands: [(rank, asset, champ, sig, plano, d0)] do motor de sinais. Regista objecoes e a analise; devolve as
    linhas registadas. Nunca altera cands."""
    st = _st(state)
    grupos = {}
    for _, a, champ, sig, p, _ in cands:
        grupos[(champ, sig.get("t_sig"))] = grupos.get((champ, sig.get("t_sig")), 0) + 1
    stops = {}
    for reg in st["registos"][-2000:]:
        if reg.get("stop_pct") is not None:
            stops.setdefault(reg.get("strategy"), []).append(float(reg["stop_pct"]))
    feitas = []
    vistos = {r.get("chave") for r in st["registos"][-3000:]}
    for _, a, champ, sig, p, _ in cands:
        chave = f"{a}|{champ}|{int(sig.get('t_sig') or 0)}"
        if chave in vistos:
            continue
        px = p.get("_px") or p.get("entry_ref")
        sp = abs(float(sig["stop"]) - float(px)) / float(px) * 100 if px and sig.get("stop") else None
        cand = {"side": sig.get("side") or p.get("side") or "LONG", "deriv": deriv.get(a) or {}, "stop_pct": sp}
        obs = objecoes(cand, grupos[(champ, sig.get("t_sig"))], stops.get(champ, []), now)
        reg = {"chave": chave, "asset": a, "strategy": champ, "t_sig": int(sig.get("t_sig") or 0), "t": int(now),
               "lado": cand["side"], "stop_pct": round(sp, 3) if sp is not None else None, "objecoes": obs,
               "analise": {o["codigo"]: analista(state, champ, o["codigo"]) for o in obs}}
        st["registos"].append(reg)
        vistos.add(chave)
        feitas.append(reg)
    del st["registos"][:-MAX_REG]
    return feitas


def resumo(state):
    st = _st(state)
    por = {}
    for reg in st["registos"]:
        for o in reg.get("objecoes") or []:
            por[o["codigo"]] = por.get(o["codigo"], 0) + 1
    return {"sinais_observados": len(st["registos"]), "objecoes_por_tipo": por, "modo": "observação (não bloqueia)"}
