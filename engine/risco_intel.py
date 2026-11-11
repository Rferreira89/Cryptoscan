"""(11/11) Risk Intelligence e Execution Intelligence de investigacao. So mede e recomenda; nao altera limites
reais, executores, ordens nem posicoes.

Risco (sobre uma lista de R por operacao, um ambiente de cada vez):
  - cauda: VaR e CVaR a 5% por operacao e por dia (soma diaria: as operacoes do mesmo dia nao sao independentes);
  - sequencias de perdas: a maior observada e a probabilidade, por reamostragem dos dias, de ver N perdas seguidas
    em 100 operacoes;
  - queda maxima em R: observada e distribuicao por bootstrap de blocos de dias (mediana e percentil 95);
  - dependencia do BTC e risco por regime: vem de backtest/quant/residual.py e robustez.por_grupo (nao duplicado);
  - custos acumulados: soma de custo_r (engine.contabilidade) quando ha dados de custos reais.
Execucao (papel contra real, no mesmo sinal): diferenca de entrada e de saida em R e no resultado.
Recomendacoes: so frases ligadas a um numero medido e ao limite que o motivou; nunca uma alteracao automatica."""
import math
import random

DIA = 86400


def _perc(xs, q):
    s = sorted(xs)
    if not s:
        return None
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def cauda(rs, alfa=0.05):
    if len(rs) < 10:
        return {"n": len(rs), "var": None, "cvar": None}
    v = _perc(rs, alfa)
    pior = [r for r in rs if r <= v]
    return {"n": len(rs), "var": round(v, 4), "cvar": round(sum(pior) / len(pior), 4)}


def maior_sequencia(rs):
    seq = pior = 0
    for r in rs:
        seq = seq + 1 if r < 0 else 0
        pior = max(pior, seq)
    return pior


def queda_maxima(rs):
    acum = pico = dd = 0.0
    for r in rs:
        acum += r
        pico = max(pico, acum)
        dd = min(dd, acum - pico)
    return round(dd, 4)


def por_dias(ops):
    d = {}
    for o in ops:
        if o.get("R") is None:
            continue
        d.setdefault(int(o["t_entrada"] // DIA), []).append(o["R"])
    return [d[k] for k in sorted(d)]


def simular(ops, n_ops=100, n_sim=2000, bloco=3, semente=13, limiar_seq=(5, 8, 10)):
    """Reamostra blocos de dias seguidos ate juntar n_ops operacoes; mede queda maxima e sequencias de perdas."""
    dias = por_dias(ops)
    if len(dias) < 5:
        return None
    rnd = random.Random(semente)
    dds, seqs = [], []
    for _ in range(n_sim):
        rs = []
        while len(rs) < n_ops:
            i = rnd.randrange(len(dias))
            for j in range(bloco):
                rs += dias[(i + j) % len(dias)]
        rs = rs[:n_ops]
        dds.append(queda_maxima(rs))
        seqs.append(maior_sequencia(rs))
    return {"n_ops": n_ops, "simulacoes": n_sim, "queda_mediana_r": round(_perc(dds, 0.5), 3),
            "queda_p95_r": round(_perc(dds, 0.05), 3),
            "prob_sequencia": {str(k): round(sum(1 for s in seqs if s >= k) / n_sim, 4) for k in limiar_seq}}


def relatorio(ops, risco_pct=1.0, travao_pct=45.0):
    """Risco de uma estrategia num ambiente. risco_pct: % da conta por operacao (so para traduzir R em % da conta,
    com o valor configurado hoje; nao muda nada)."""
    ops = sorted((o for o in ops if o.get("R") is not None), key=lambda o: o["t_entrada"])
    rs = [o["R"] for o in ops]
    diarios = [sum(d) for d in por_dias(ops)]
    sim = simular(ops)
    out = {"n": len(rs), "cauda_operacao": cauda(rs), "cauda_dia": cauda(diarios), "maior_sequencia_perdas": maior_sequencia(rs),
           "queda_maxima_r": queda_maxima(rs), "simulacao_100_ops": sim,
           "custos_acumulados_r": round(sum(o.get("custo_r") or 0 for o in ops), 3) if any(o.get("custo_r") is not None for o in ops) else None}
    out["recomendacoes"] = recomendar(out, risco_pct, travao_pct)
    return out


def recomendar(r, risco_pct, travao_pct):
    rec = []
    sim = r.get("simulacao_100_ops") or {}
    if sim.get("queda_p95_r") is not None:
        q = -sim["queda_p95_r"] * risco_pct
        rec.append(f"em 100 operacoes, 5% das simulacoes tem uma queda maior do que {q:.0f}% da conta a {risco_pct:g}% por operacao"
                   + (f" (acima do travao de {travao_pct:g}%)" if q > travao_pct else f" (abaixo do travao de {travao_pct:g}%)"))
    cd = r.get("cauda_dia") or {}
    if cd.get("cvar") is not None and cd["cvar"] < -3:
        rec.append(f"cauda diaria: nos 5% piores dias perde-se em media {-cd['cvar']:.1f}R num so dia (operacoes simultaneas)")
    if (sim.get("prob_sequencia") or {}).get("8", 0) > 0.2:
        rec.append(f"probabilidade de 8 perdas seguidas em 100 operacoes: {100 * sim['prob_sequencia']['8']:.0f}%")
    return rec


def papel_contra_real(reais, papel):
    """reais: okx.json real.hist; papel: okx.json fechadas. Junta pelo ativo e pela hora do sinal."""
    idx = {(p.get("asset"), p.get("t_sig")): p for p in papel}
    out = []
    for h in reais:
        if h.get("estado") != "fechada" or not h.get("entrada") or not h.get("stop") or not h.get("saida"):
            continue
        p = idx.get((h.get("asset"), h.get("t_sig")))
        risco = h["entrada"] - h["stop"]
        r_real = (h["saida"] - h["entrada"]) / risco
        out.append({"ativo": h.get("asset"), "t_sig": h.get("t_sig"), "r_real_preco": round(r_real, 4),
                    "r_papel": p.get("r") if p else None, "motivo_papel": p.get("motivo") if p else None,
                    "diferenca_r": round(r_real - p["r"], 4) if p and p.get("r") is not None else None})
    difs = [x["diferenca_r"] for x in out if x["diferenca_r"] is not None]
    return {"pares": out, "n": len(difs), "diferenca_media_r": round(sum(difs) / len(difs), 4) if difs else None,
            "nota": "R real so de precos (sem comissoes nem funding; esses vem da contabilidade cifrada); o papel ja inclui custos estimados"}
