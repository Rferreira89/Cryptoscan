"""Pos-morte automatico das operacoes reais (pedido do Rui, 20/10).

Para cada operacao real fechada: perdeu (ou ganhou) pelo sinal ou pela
execucao? Em que fase do mercado entrou, e a estrategia prova nessa fase?
Como saiu? E, no conjunto, que erros se repetem. So le o registo e os
resultados; nao mexe em dinheiro nem em risco."""
from collections import Counter, defaultdict

GAP_R = 0.15                # diferenca entre o real e o sinal que ja conta como erro de execucao
MIN_N_FASE = 20


def _r(x, d=2):
    return None if x is None else round(float(x), d)


def resultado(x):
    """R que conta: o real da Bybit, senao o que o Rui marcou, senao o do sinal."""
    for k in ("real_r", "user_result_r", "result_r"):
        if x.get(k) is not None:
            return float(x[k])
    return None


def fechadas(led):
    return [x for x in led or [] if x.get("mode") == "REAL" and x.get("executed") is True
            and x.get("status") == "CLOSED" and resultado(x) is not None]


def prova_na_fase(longo, estrategia, fase):
    """(prova, n, R) da estrategia nessa fase no ringue de um ano."""
    f = (((longo or {}).get(estrategia) or {}).get("por_regime") or {}).get(fase) or {}
    n, r, p95, met = f.get("n") or 0, f.get("avg_r"), f.get("acaso_p95"), f.get("metades")
    ok = n >= MIN_N_FASE and r is not None and r >= .15 and p95 is not None and r > p95 and bool(met) and min(met) > 0
    return ok, n, r


def analisar(x, longo=None):
    r, rs, rr = resultado(x), x.get("result_r"), x.get("real_r")
    lic, causa = [], None
    real = x.get("real") or {}
    if rr is not None and rs is not None:
        gap = rr - rs
        if gap <= -GAP_R:
            lic.append(f"a execução custou {gap:+.2f}R (sinal {rs:+.2f}R, real {rr:+.2f}R): deslize e comissões")
            if rs > 0 >= rr:
                causa = "execucao"
        if real.get("comissoes_usdc") and x.get("risk_usdc"):
            c = real["comissoes_usdc"] / x["risk_usdc"]
            if c >= .05:
                lic.append(f"comissões de {c:.2f}R ({real['comissoes_usdc']:.2f} USDC)")
    motivo = x.get("reason")
    if motivo == "STOP" and (x.get("tp_hit") or 0) == 0:
        lic.append("stop sem tocar no 1.º objetivo: a entrada não teve seguimento")
        causa = causa or "sinal"
    elif motivo == "BREAKEVEN":
        lic.append("tocou no 1.º objetivo e o resto saiu na entrada")
    elif motivo in ("TIME", "NOREACT"):
        lic.append("saiu por tempo, sem reação do preço")
    fase = x.get("fase")
    if fase:
        ok, n, rf = prova_na_fase(longo, x.get("strategy"), fase)
        if not ok:
            lic.append(f"entrou na fase {fase}, onde a estratégia não prova ({n} op., "
                       f"{'–' if rf is None else f'{rf:+.2f}R'} no último ano)")
            causa = "fase" if causa in (None, "sinal") else causa      # a fase errada explica o sinal falhado
    contra = [k for k, v in (x.get("deps") or {}).items() if v == "contra"]
    if len(contra) >= 2:
        lic.append(f"{len(contra)} departamentos estavam contra ({', '.join(contra)})")
    if r is not None and r > 0 and not causa:
        causa = "ganhou"
    elif r is not None and abs(r) < GAP_R and not causa:
        causa = "empate"
    return {"id": x.get("id"), "ativo": x.get("asset"), "estrategia": x.get("strategy"),
            "t": x.get("closed_at"), "r": _r(r), "r_sinal": _r(rs), "r_real": _r(rr),
            "usdc": _r(real.get("pnl_usdc") if real.get("pnl_usdc") is not None else (r or 0) * (x.get("risk_usdc") or 0)),
            "motivo": motivo, "fase": fase, "causa": causa or "sinal", "licoes": lic}


def relatorio(led, longo=None, campeoes=()):
    ops = [analisar(x, longo) for x in sorted(fechadas(led), key=lambda x: x.get("closed_at") or 0)]
    if not ops:
        return {"n": 0}
    rs = [o["r"] for o in ops]
    por = lambda k: {a: {"n": len(v), "r": _r(sum(v) / len(v)), "total": _r(sum(v))}
                     for a, v in _agrupar(ops, k).items()}
    med = [o for o in ops if o["r_real"] is not None and o["r_sinal"] is not None]
    gap = sum(o["r_real"] - o["r_sinal"] for o in med) / len(med) if med else None
    padroes, licoes = [], []
    est = por("estrategia")
    for e, v in sorted(est.items(), key=lambda kv: kv[1]["total"]):
        if v["n"] >= 3 and v["r"] <= -.5:
            fora = e not in set(campeoes)
            padroes.append(f"{e}: {v['n']} operações, {v['r']:+.2f}R de média" + (" — já está fora do dinheiro real" if fora else " — continua campeão: vigiar"))
    dias = Counter(int((o["t"] or 0) // 86400) for o in ops if o["motivo"] == "STOP")
    cadeia = [d for d, c in dias.items() if c >= 2]
    if cadeia:
        padroes.append(f"perdas em cadeia: {len(cadeia)} dia(s) com 2 ou mais stops (já há limite de entradas por vela e uma operação por família)")
    sem_seg = sum(1 for o in ops if o["motivo"] == "STOP" and o["causa"] in ("sinal", "fase"))
    if sem_seg:
        padroes.append(f"{sem_seg} de {len(ops)} saíram no stop sem tocar no 1.º objetivo")
        if sem_seg * 2 >= len(ops):
            licoes.append("a maioria das perdas vem do sinal (entradas sem seguimento), não da execução: só devem operar estratégias que provaram na fase atual, e é isso que a prova dupla faz desde 20/10")
    if gap is not None and gap <= -.1:
        padroes.append(f"execução: o real fica {gap:+.2f}R por operação abaixo do sinal ({len(med)} medidas)")
        licoes.append("preferir moedas com spread baixo na Bybit UE e objetivos mais largos: o custo de execução pesa mais nas operações pequenas")
    fase_err = [o for o in ops if o["causa"] == "fase"]
    if fase_err:
        licoes.append(f"{len(fase_err)} operação(ões) entraram numa fase em que a estratégia não prova: a prova dupla por fase (desde 20/10) já trava isto")
    if not med:
        licoes.append("ainda poucas operações com o resultado real medido na Bybit: as conclusões ganham peso com mais operações")
    elif len(med) < 10:
        licoes.append(f"só {len(med)} operações com resultado real medido: conclusões ainda fracas")
    causas = Counter(o["causa"] for o in ops)
    gap_est = {}                               # (22/10) custo real por estrategia: ultimas 20 medidas
    for o in med:
        gap_est.setdefault(o["estrategia"], []).append(o["r_real"] - o["r_sinal"])
    gap_est = {e: {"n": len(v[-20:]), "gap": _r(sum(v[-20:]) / len(v[-20:]))} for e, v in gap_est.items()}
    return {"n": len(ops), "r_total": _r(sum(rs)), "r_medio": _r(sum(rs) / len(rs)),
            "acerto": round(sum(1 for r in rs if r > 0) / len(rs) * 100), "usdc": _r(sum(o["usdc"] or 0 for o in ops)),
            "gap_execucao_r": _r(gap), "medidas": len(med), "causas": dict(causas), "gap_por_estrategia": gap_est,
            "por_estrategia": est, "por_ativo": por("ativo"), "por_motivo": por("motivo"),
            "padroes": padroes, "licoes": licoes, "ops": ops[-20:]}


def _agrupar(ops, k):
    g = defaultdict(list)
    for o in ops:
        if o["r"] is not None:
            g[o.get(k) or "–"].append(o["r"])
    return g


CAUSA_TXT = {"execucao": "perdeu na execução", "sinal": "o sinal falhou", "fase": "fase errada", "ganhou": "ganhou", "empate": "saiu perto da entrada"}


CUSTO_N, CUSTO_LIMITE = 20, -0.10


def custo_aviso(state, rel, now):
    """(22/10, auditoria S/R, OK do Rui) A vantagem do Ramiro cai para metade com custos a
    dobrar. Se, nas ultimas CUSTO_N operacoes reais medidas de uma estrategia, o resultado
    real ficar em media pior do que o do sinal em mais de 0,10R, avisa (uma vez, e de novo
    ao fim de 7 dias se continuar). Nao mexe em dinheiro."""
    vis = state.setdefault("custo_alarme", {})
    out = []
    for e, v in ((rel or {}).get("gap_por_estrategia") or {}).items():
        mau = v["n"] >= CUSTO_N and v["gap"] is not None and v["gap"] < CUSTO_LIMITE
        ant = vis.get(e)
        if mau and (not ant or now - ant >= 7 * 86400):
            vis[e] = int(now)
            out.append(f"💸 <b>Custo de execução alto em {e}</b>: nas últimas {v['n']} operações reais, o resultado "
                       f"real ficou {v['gap']:+.2f}R por operação abaixo do sinal (limite −0,10R). A vantagem desta "
                       "estratégia é fina: convém rever as moedas permitidas (spread e volume na Bybit UE).")
        elif not mau and ant:
            vis.pop(e, None)
    return out


def novos(state, rel):
    """Mensagens de pos-morte para as operacoes fechadas desde a ultima vez.
    Na primeira corrida so marca as que ja existiam (sem enviar nada)."""
    vistos = state.get("posmortem_vistos")
    ids = [o["id"] for o in rel.get("ops") or []]
    if vistos is None:
        state["posmortem_vistos"] = ids[-100:]
        return []
    out = []
    for o in rel.get("ops") or []:
        if o["id"] in vistos:
            continue
        vistos.append(o["id"])
        li = "; ".join(o["licoes"][:3]) or "nada a apontar"
        out.append(f"🔍 <b>Pós-morte {o['ativo']}</b> ({o['estrategia']}): {o['r']:+.2f}R — {CAUSA_TXT.get(o['causa'], o['causa'])}. {li}.")
    state["posmortem_vistos"] = vistos[-100:]
    return out
