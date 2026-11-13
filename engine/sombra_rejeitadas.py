"""(13/11, ordem do Rui, A1) Sombra das oportunidades REJEITADAS: cada sinal de um campeao que nao virou ordem fica
guardado com o plano completo e e seguido virtualmente com as MESMAS regras de saida das operacoes reais e de papel
(engine/trade: parciais nos objetivos, stop para a entrada depois do 1.o, gap no stop, tempo maximo), com custos
(comissao 0,25%/lado, deslize 0,1%, juro do emprestimo nos SHORT), para medir o que cada filtro custa ou poupa.

- Sem olhar para o futuro: entrada ao preco do momento da decisao; so velas de 4h que abrem DEPOIS da vela em curso
  e ja fechadas sao usadas (a vela em curso e saltada, como em engine/paper_shadow).
- Sem duplicados: chave moeda|estrategia|vela do sinal; a mesma oportunidade recusada por varios filtros conta uma
  vez (fica o primeiro motivo).
- Historico completo (sem o limite dos 100 de promo_lost); so % e R (nunca dinheiro).
- Nunca gera ordens nem mensagens. Nao muda nenhum filtro: os dados servem para decidir depois, com estatistica."""
from . import trade

TF = 14400
FEE_PCT, SLIP_PCT = 0.25, 0.1
JURO_DIA_PADRAO = 0.0003            # fracao/dia quando nao ha taxa real da Bybit para a moeda
MAX_FECHADAS = 20000


def _st(state):
    st = state.setdefault("sombra_rejeitadas", {})
    st.setdefault("abertas", {})
    st.setdefault("fechadas", [])
    st.setdefault("chaves", [])
    return st


def filtro_de(why):
    w = (why or "").strip()
    return (w.split(":")[0] if ":" in w else w)[:40] or "?"


def registar(state, now, asset, champ, why, sig, price, plano=None, extra=None):
    """Guarda a oportunidade recusada para a sombra. Devolve a chave, ou None se nao ha plano utilizavel."""
    if not sig or not price or sig.get("stop") is None or not sig.get("tp"):
        return None
    st = _st(state)
    chave = f"{asset}|{champ}|{int(sig.get('t_sig') or 0)}"
    if chave in st["abertas"] or chave in set(st["chaves"][-5000:]):
        return None
    side = sig.get("side") or "LONG"
    stop, px = float(sig["stop"]), float(price)
    if (side == "LONG" and not stop < px) or (side == "SHORT" and not stop > px):
        return None                                    # plano incoerente: preco ja do lado errado do stop
    tps = [float(x) for x in sig["tp"]]
    partials = list(sig.get("partials") or [100])
    plan = {"stop": stop, "tp": tps, "partials": partials, "max_hold_s": sig.get("hold_s"),
            "no_react_s": sig.get("no_react_s"), "trail_r": sig.get("trail_r")}
    pos = trade.open_position(plan, px, int(now), FEE_PCT, SLIP_PCT, breakeven=sig.get("breakeven", True), side=side)
    juros = ((state.get("juros_bybit") or {}).get("m") or {})
    jd = juros.get(asset)
    try:
        jd = float(jd) / 100 if jd is not None and side == "SHORT" else (JURO_DIA_PADRAO if side == "SHORT" else 0.0)
    except (TypeError, ValueError):
        jd = JURO_DIA_PADRAO if side == "SHORT" else 0.0
    pl = plano or {}
    reg = ((state.get("mercado") or {}).get("regime"))
    pos.update(chave=chave, asset=asset, corretora="bybit_ue", strategy=champ, lado=side, t_sig=int(sig.get("t_sig") or 0),
               decidido=int(now), motivo=(why or "")[:160], filtro=filtro_de(why), regime=reg, juro_dia=jd,
               next_t=int(sig.get("t_sig") or now) + TF,
               plano={"entrada": px, "stop": stop, "tp": tps, "partials": partials,
                      "max_hold_s": sig.get("hold_s"), "breakeven": sig.get("breakeven", True),
                      "risk_pct": pl.get("risk_pct"), "position_pct": pl.get("position_pct"),
                      "stop_pct": round(abs(stop - px) / px * 100, 3)},
               dados=dict({"atr": sig.get("atr"), "preco": px}, **(extra or {})))
    st["abertas"][chave] = pos
    st["chaves"].append(chave)
    del st["chaves"][:-5000]
    return chave


def atualizar(state, bars, now):
    """Avanca as abertas com as velas de 4h fechadas; fecha as que as regras fecham. Devolve as fechadas agora."""
    st = _st(state)
    feitas = []
    for k in list(st["abertas"]):
        pos = st["abertas"][k]
        c4 = bars.get(pos["asset"]) or []
        for x in c4:
            if pos["closed"]:
                break
            if x["t"] < pos["next_t"] or x["t"] + TF > now:
                continue                                  # vela ja usada, ou ainda por fechar
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
            pos["next_t"] = x["t"] + TF
        if not pos["closed"]:
            continue
        dias = max(0.0, ((pos.get("closed_at") or now) - pos["opened_at"]) / 86400)
        if pos.get("juro_dia"):                           # juro do emprestimo sobre toda a posicao vendida
            pos["realized"] -= pos["juro_dia"] * dias * pos["entry"]
            pos["r"] = round(pos["realized"] / pos["risk_unit"], 3)
        f = {c: pos.get(c) for c in ("chave", "asset", "corretora", "strategy", "lado", "t_sig", "decidido", "motivo",
                                     "filtro", "regime", "plano", "dados", "exit_reason", "closed_at", "r", "tp_hit")}
        f["dias"] = round(dias, 2)
        st["fechadas"].append(f)
        feitas.append(f)
        del st["abertas"][k]
    del st["fechadas"][:-MAX_FECHADAS]
    return feitas


def resumo(state):
    """Por filtro, estrategia e regime: n, R contrafactual, % vencedoras, perdas evitadas e ganhos perdidos (em R)."""
    st = _st(state)
    fx = st["fechadas"]

    def agrega(chave):
        out = {}
        for f in fx:
            out.setdefault(f.get(chave) or "?", []).append(float(f["r"]))
        res = {}
        for k, rs in sorted(out.items()):
            g = [x for x in rs if x > 0]
            p = [x for x in rs if x <= 0]
            res[k] = {"n": len(rs), "soma_r": round(sum(rs), 3), "r_op": round(sum(rs) / len(rs), 3),
                      "vencedoras_pct": round(100 * len(g) / len(rs), 1),
                      "ganhos_perdidos_r": round(sum(g), 3), "perdas_evitadas_r": round(-sum(p), 3)}
        return res
    return {"abertas": len(st["abertas"]), "fechadas": len(fx), "por_filtro": agrega("filtro"),
            "por_estrategia": agrega("strategy"), "por_regime": agrega("regime"), "por_corretora": agrega("corretora")}
