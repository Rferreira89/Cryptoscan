"""Diretor de Trading (agente central, decisao do Rui em 2026-10-14).

Coordena as analises, verifica conflitos e AUTORIZA ou REJEITA cada sinal
real antes de ser emitido. Nenhuma entrada passa sem ele.

Cada agente (o lutador que propoe e cada departamento) devolve um relatorio
estruturado:
  agente, ativo, timeframe, dados (fonte e timestamp), direcao, condicoes,
  entrada / stop / alvos (quando aplicavel), contra (evidencias contrarias),
  estado_dados (valido / atrasado / indisponivel) e invalidacao.

O diretor nao aceita "SOL parece bullish": decide so com evidencia
verificavel e com estas regras, definidas antes:

  R1 Dados: velas de 4H e 1D utilizaveis (validas ou com aviso) e a ultima vela de 4H fechada ha menos
     de 4h15m; precos das fontes com divergencia abaixo de 1%; preco na
     Bybit UE nao parado. Dados atrasados ou indisponiveis -> REJEITA.
  R2 Plano: stop do lado certo da entrada, objetivos do lado certo, R:R
     liquido final >= 1,2. Plano incoerente -> REJEITA.
  R3 Conflitos: 3 ou mais departamentos contra a direcao -> REJEITA.
     Nao contam as leituras que sao a propria premissa da estrategia
     (definidas por familia em ESPERADO): quem compra sobrevenda compra
     por definicao contra a tendencia, com vendedores no volume e a moeda
     mais fraca que o BTC; quem segue tendencia compra com RSI alto.
  R4 Macro: compra com a macroeconomia em "medo" -> REJEITA (exceto o
     lutador que compra precisamente o medo); venda com macro favoravel e
     tendencia a favor -> conta como conflito.
  R5 Derivados contra (compradores em excesso / funding extremo numa compra,
     ou o inverso numa venda) + mais um departamento contra -> REJEITA.

As rejeicoes ficam registadas com o plano completo e sao seguidas em papel:
o diretor tambem e avaliado (quantas vezes rejeitar evitou uma perda).
"""
import time

H4 = 14400
MAX_CONTRA = 3
MIN_RR = 1.2
# leituras contrarias que sao a premissa da familia (nao contam como conflito)
ESPERADO = {
    "sobrevenda": {"Tendência e estrutura", "Volume e fluxo", "Força relativa"},
    "capitulacao": {"Tendência e estrutura", "Volume e fluxo", "Força relativa"},
    "tendencia": {"Sobrevenda"},
    "volatilidade": set(),
    "short": {"Tendência e estrutura", "Volume e fluxo", "Força relativa", "Sobrevenda"},
}


def _ts(t):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if t else None


def data_state(row, c4, now):
    """('valido' | 'atrasado' | 'indisponivel', [motivos])."""
    why = []
    tfs = row.get("timeframes") or {}
    for tf in ("4h", "1d"):
        st = (tfs.get(tf) or {}).get("status")
        # DEGRADED = utilizavel com aviso (p. ex. um pico de volume antigo)
        if st not in ("VALID", "DEGRADED"):
            why.append(f"velas {tf.upper()}: {st or 'em falta'}")
    if not c4:
        return "indisponivel", why + ["sem velas de 4H"]
    age = now - (c4[-1]["t"] + H4)
    if age > H4 + 900:
        why.append(f"última vela de 4H fechou há {age / 3600:.1f}h")
    if (row.get("divergence_pct") or 0) > 1.0:
        why.append(f"fontes de preço divergem {row['divergence_pct']:.2f}%")
    if (row.get("venue") or {}).get("stale"):
        why.append("preço da Bybit UE parado")
    if not why:
        return "valido", []
    return ("indisponivel" if any("velas " in w and "fechou" not in w for w in why)
            else "atrasado"), why


def dept_reports(row, deps, side, c4, now, esperado=()):
    """Relatorio estruturado de cada departamento."""
    t4 = _ts(c4[-1]["t"] + H4) if c4 else None
    out = []
    for d in deps:
        favor = "verde" if side == "LONG" else "vermelho"
        contra = "vermelho" if side == "LONG" else "verde"
        direcao = "compra" if d["cor"] == "verde" else "venda" if d["cor"] == "vermelho" else "neutro"
        out.append({
            "agente": d["dep"], "ativo": row["asset"], "timeframe": "4H / 1D",
            "dados": [{"fonte": "velas 4H (Binance/OKX)", "t": t4}]
            + ([{"fonte": f"derivados ({(row.get('derivatives') or {}).get('venue', '–')})", "t": _ts(now)}]
               if d["dep"] == "Derivados" else [])
            + ([{"fonte": "macro (servidor europeu)", "t": _ts(now)}] if d["dep"] == "Macroeconomia" else []),
            "direcao": direcao, "condicoes": [d["texto"]],
            "contra": [d["texto"]] if d["cor"] == contra and d["dep"] not in esperado else [],
            "esperado": d["cor"] == contra and d["dep"] in esperado,
            "a_favor": d["cor"] == favor,
            "estado_dados": "indisponivel" if "sem dados" in d["texto"] or "indisponível" in d["texto"] else "valido",
            "invalidacao": []})
    return out


def proposer_report(row, dec, c4):
    """Relatorio estruturado do lutador (ou estrategia) que propoe a entrada."""
    p = dec.get("plan") or {}
    side = dec.get("decision")
    stop, tps = p.get("stop"), p.get("tp") or []
    venda = side == "SHORT"
    return {
        "agente": dec.get("strategy"), "ativo": row["asset"], "timeframe": "4H",
        "dados": [{"fonte": "vela de 4H fechada", "t": _ts(c4[-1]["t"] + H4) if c4 else None}],
        "direcao": "venda a descoberto" if venda else "compra",
        "condicoes": [dec.get("trigger") or dec.get("reason") or "gatilho da estratégia"],
        "entrada": p.get("entry_zone"), "stop": stop, "alvos": tps[:3],
        "contra": [], "estado_dados": "valido",
        "invalidacao": [
            f"fecho de 4H {'acima' if venda else 'abaixo'} de {stop:.6g} (stop)" if stop else "stop em falta",
            f"preço chega a {tps[0]:.6g} (primeiro objetivo) antes da entrada" if tps else "",
            "sinal sem entrada até ao fim da validade"]}


def check_plan(dec):
    p = dec.get("plan") or {}
    lo, hi = sorted(p.get("entry_zone") or [0, 0])
    stop, tps = p.get("stop"), p.get("tp") or []
    if not stop or not tps or not lo:
        return "plano incompleto (entrada, stop ou objetivos em falta)"
    if dec.get("decision") == "SHORT":
        if not (stop > hi and tps[0] < lo):
            return "plano de venda incoerente (stop tem de estar acima e objetivos abaixo)"
    elif not (stop < lo and tps[0] > hi):
        return "plano de compra incoerente (stop tem de estar abaixo e objetivos acima)"
    rr = p.get("rr")
    if rr is not None and rr < MIN_RR:
        return f"R:R líquido final {rr:.2f} abaixo de {MIN_RR}"
    return None


def review(row, dec, c4, macro, btc_c4, now):
    """Decide AUTORIZADO / REJEITADO para a decisao de entrada 'dec'."""
    from . import consultas, promo
    side = dec.get("decision")
    fam = promo.family(dec.get("strategy"))
    est, dwhy = data_state(row, c4, now)
    deps = row.get("departamentos") or consultas.departments(row, macro, btc_c4, c4)
    reps = [proposer_report(row, dec, c4)] + dept_reports(row, deps, side, c4, now, ESPERADO.get(fam, set()))
    contra = [r for r in reps[1:] if r["contra"]]
    favor = [r for r in reps[1:] if r["a_favor"]]
    motivos = []
    if est != "valido":                                          # R1
        motivos.append(f"dados {est}: " + "; ".join(dwhy))
    bad = check_plan(dec)                                        # R2
    if bad:
        motivos.append(bad)
    if len(contra) >= MAX_CONTRA:                                # R3
        motivos.append(f"{len(contra)} departamentos contra: " + ", ".join(r["agente"] for r in contra))
    st = (macro or {}).get("estado")
    if side == "LONG" and st == "medo" and not str(dec.get("strategy", "")).startswith("BOUNCE_MEDO"):
        motivos.append("macroeconomia em medo: compras suspensas")    # R4
    der = next((r for r in contra if r["agente"] == "Derivados"), None)
    if der and len(contra) >= 2 and not any("departamentos contra" in m for m in motivos):
        motivos.append("derivados contra e mais um departamento contra: "      # R5
                       + ", ".join(r["agente"] for r in contra))
    ok = not motivos
    deps = {r["agente"]: ("esperado" if r.get("esperado") else "contra" if r["contra"]
                          else "favor" if r["a_favor"] else "neutro") for r in reps[1:]}
    return {"decisao": "AUTORIZADO" if ok else "REJEITADO", "t": int(now), "deps": deps,
            "ativo": row["asset"], "estrategia": dec.get("strategy"), "lado": side,
            "motivos": motivos, "estado_dados": est, "familia": fam,
            "esperado": [r["agente"] for r in reps[1:] if r.get("esperado")],
            "a_favor": [f"{r['agente']}: {r['condicoes'][0]}" for r in favor],
            "contra": [f"{r['agente']}: {r['contra'][0]}" for r in contra],
            "invalidacao": [x for x in reps[0]["invalidacao"] if x],
            "relatorios": reps}


def gate(state, rows, c4s, macro, now):
    """Passa todas as decisoes de entrada reais pelo diretor. As rejeitadas
    passam a NO TRADE e ficam registadas (com o plano, para serem seguidas)."""
    dr = state.setdefault("diretor", {"decisoes": [], "rejeitados": []})
    btc = c4s.get("BTC")
    for r in rows:
        for key in ("decision", "decision_short"):
            d = r.get(key) or {}
            if d.get("decision") not in ("LONG", "SHORT") or d.get("mode", "REAL") != "REAL":
                continue
            if d.get("diretor"):                    # ja revista neste scan
                continue
            try:
                v = review(r, d, c4s.get(r["asset"]), macro, btc, now)
            except Exception as e:          # sem revisao nao ha entrada (falha fechada)
                v = {"decisao": "REJEITADO", "motivos": [f"diretor sem leitura ({type(e).__name__})"],
                     "a_favor": [], "contra": [], "invalidacao": [], "estado_dados": "indisponivel",
                     "t": int(now), "ativo": r["asset"], "estrategia": d.get("strategy"),
                     "lado": d["decision"], "familia": None, "esperado": [], "relatorios": []}
            d["diretor"] = {k: v.get(k) for k in ("decisao", "motivos", "a_favor", "contra", "invalidacao",
                                                  "estado_dados", "esperado", "deps")}
            short = {k: v[k] for k in ("decisao", "t", "ativo", "estrategia", "lado", "motivos",
                                       "a_favor", "contra", "invalidacao", "estado_dados",
                                       "familia", "esperado")}
            short["relatorios"] = v["relatorios"]
            same = lambda x: (x.get("ativo"), x.get("estrategia"), x.get("lado")) == \
                (r["asset"], d.get("strategy"), d["decision"])
            # a mesma proposta revista de 5 em 5 minutos: fica so a ultima leitura
            dr["decisoes"] = ([x for x in dr["decisoes"] if not (same(x) and now - x["t"] < H4)]
                              + [short])[-30:]
            if v["decisao"] == "REJEITADO" and not any(
                    same(x) and x.get("estado") == "aberto" for x in dr["rejeitados"]):
                p = d.get("plan") or {}
                dr["rejeitados"] = (dr["rejeitados"] + [{
                    "t": int(now), "ativo": r["asset"], "estrategia": d.get("strategy"), "lado": d["decision"],
                    "entrada": (p.get("entry_ref") or (p.get("entry_zone") or [None, None])[1]),
                    "stop": p.get("stop"), "tp": (p.get("tp") or [])[:2], "motivos": v["motivos"],
                    "deps": v.get("deps"), "estado": "aberto"}])[-60:]
            if v["decisao"] == "REJEITADO":
                d.update(decision="NO TRADE", reason="Diretor de Trading: " + "; ".join(v["motivos"]))
    return dr


def follow(state, c4s, now):
    """Segue em papel os sinais que o diretor rejeitou: diz se a rejeicao
    evitou uma perda (stop) ou custou um ganho (objetivo)."""
    dr = state.get("diretor") or {}
    for x in dr.get("rejeitados") or []:
        if x.get("estado") != "aberto" or not x.get("stop") or not x.get("tp") or not x.get("entrada"):
            continue
        c4 = c4s.get(x["ativo"]) or []
        short = x["lado"] == "SHORT"
        for b in c4:
            if b["t"] < x["t"]:
                continue
            hit_stop = b["h"] >= x["stop"] if short else b["l"] <= x["stop"]
            hit_tp = b["l"] <= x["tp"][0] if short else b["h"] >= x["tp"][0]
            if hit_stop:
                x.update(estado="evitou perda", fechado=b["t"] + H4)
                break
            if hit_tp:
                x.update(estado="custou ganho", fechado=b["t"] + H4)
                break
        if x.get("estado") == "aberto" and now - x["t"] > 7 * 86400:
            x["estado"] = "sem resultado"
    rs = dr.get("rejeitados") or []
    return {"evitou_perda": sum(1 for x in rs if x.get("estado") == "evitou perda"),
            "custou_ganho": sum(1 for x in rs if x.get("estado") == "custou ganho"),
            "em_curso": sum(1 for x in rs if x.get("estado") == "aberto")}


def summary(state, now):
    """Resumo para a pagina: ultimas decisoes (sem os relatorios completos
    das antigas, para a pagina ficar leve) e rejeicoes seguidas."""
    dr = state.get("diretor") or {}
    dec = sorted(dr.get("decisoes") or [], key=lambda x: -x["t"])
    out = [dict(x) if i < 6 else {k: v for k, v in x.items() if k != "relatorios"}
           for i, x in enumerate(dec[:15])]
    hoje = [x for x in dec if now - x["t"] < 86400]
    return {"decisoes": out,
            "autorizados_24h": sum(1 for x in hoje if x["decisao"] == "AUTORIZADO"),
            "rejeitados_24h": sum(1 for x in hoje if x["decisao"] == "REJEITADO"),
            "rejeitados": sorted(dr.get("rejeitados") or [], key=lambda x: -x["t"])[:15],
            "departamentos": scoreboard(state), "regras": REGRAS}


# ---------- avaliacao dos departamentos ----------
# Em cada operacao fechada (e em cada rejeicao seguida em papel) ve-se quem
# tinha razao: a favor e ganhou, ou contra e perdeu = acerto. As leituras
# neutras e as "esperadas pela estrategia" nao contam. Com 30 avaliacoes
# um departamento tem amostra para pesar nas regras do diretor.
MIN_AVAL = 30


def _outcomes(state):
    """[(deps, ganhou)] das operacoes fechadas e das rejeicoes ja resolvidas."""
    out = []
    for r in state.get("ledger") or []:
        if r.get("deps") and r.get("status") == "CLOSED" and r.get("result_r") is not None:
            out.append((r["deps"], r["result_r"] > 0))
    for x in (state.get("diretor") or {}).get("rejeitados") or []:
        if x.get("deps") and x.get("estado") in ("evitou perda", "custou ganho"):
            out.append((x["deps"], x["estado"] == "custou ganho"))
    return out


def scoreboard(state):
    """Taxa de acerto de cada departamento (quando estava a favor ou contra)."""
    tab = {}
    for deps, won in _outcomes(state):
        for dep, pos in deps.items():
            if pos not in ("favor", "contra"):
                continue
            t = tab.setdefault(dep, {"dep": dep, "n": 0, "acertos": 0})
            t["n"] += 1
            t["acertos"] += int((pos == "favor") == won)
    for t in tab.values():
        t["taxa"] = round(100 * t["acertos"] / t["n"], 1)
        t["amostra"] = t["n"] >= MIN_AVAL
    return sorted(tab.values(), key=lambda t: (not t["amostra"], -t["taxa"], -t["n"]))


REGRAS = [
    "R1 Dados: velas de 4H e 1D utilizáveis, última vela de 4H fechada há menos de 4h15m, "
    "fontes de preço com divergência abaixo de 1% e preço da Bybit UE ativo.",
    "R2 Plano: stop e objetivos do lado certo da entrada e R:R líquido final de pelo menos 1,2.",
    "R3 Conflitos: 3 ou mais departamentos contra a direção rejeitam (não contam as leituras "
    "que são a premissa da própria estratégia).",
    "R4 Macro: com a macroeconomia em medo não há compras (exceto o lutador do medo).",
    "R5 Derivados contra mais outro departamento contra rejeitam.",
]
