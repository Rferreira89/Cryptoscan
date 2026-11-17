"""(17/11) Self-Sustaining Engine: Kelly fracionado, tesouraria simulada e motor de sobrevivencia.

SO SIMULACAO. Este modulo nao importa executores, nao le chaves, nao envia ordens e nao altera config.json nem
okx_config.json. Os limites de risco autorizados sao LIDOS (nunca escritos) para mostrar quanto o Kelly
experimental ficaria cortado por eles. Repositorio publico: nada de valores em dinheiro nos ficheiros; a
tesouraria trabalha em % do capital e em multiplos do custo mensal (o valor do custo so entra em tempo de
execucao, por argumento, e nao e gravado).

Conceitos sempre separados (nomes iguais aos campos devolvidos):
  nocional_pct   valor da posicao em % do capital            margem_pct   nocional / alavancagem
  perda_max_pct  perda se o stop executar (com custos)        risco_pct    o que o dimensionamento arrisca
  exposicao_pct  soma do risco das posicoes abertas

Uso: python -m tools.autonomo <state.json publico> <saida.json> [qo_edge.json]
"""
import json
import math
import random
import sys

TETO_NOCIONAL_EXPERIMENTAL = 4.0     # % do capital por posicao (limite da experiencia original: NOCIONAL, nao risco)


# ---------------------------------------------------------------- Kelly ----------------------------------------
def kelly_r(rs):
    """Kelly para resultados em R (perda total = -1R): f* ~= media / variancia (aproximacao continua), em fracao do
    capital arriscada por operacao. Devolve 0 se a media nao e positiva."""
    rs = [float(x) for x in rs]
    if len(rs) < 2:
        return 0.0
    m = sum(rs) / len(rs)
    v = sum((x - m) ** 2 for x in rs) / (len(rs) - 1)
    return max(0.0, m / v) if v > 0 else 0.0


def kelly_prudente(rs, fracao=0.25, z=1.645, n_min=30):
    """Kelly fracionado sobre o LIMITE INFERIOR da media (incerteza da amostra): com menos de n_min operacoes ou
    limite inferior <= 0 devolve 0 (sem vantagem demonstrada = nao apostar). Resultado em % do capital em risco."""
    rs = [float(x) for x in rs]
    n = len(rs)
    if n < n_min:
        return {"risco_pct": 0.0, "motivo": f"amostra {n} < {n_min}", "n": n}
    m = sum(rs) / n
    v = sum((x - m) ** 2 for x in rs) / (n - 1)
    lo = m - z * math.sqrt(v / n)
    if lo <= 0 or v <= 0:
        return {"risco_pct": 0.0, "motivo": f"limite inferior da media {lo:+.3f}R <= 0", "n": n,
                "media_r": round(m, 4)}
    f = fracao * lo / v
    return {"risco_pct": round(100 * f, 3), "n": n, "media_r": round(m, 4), "media_inferior_r": round(lo, 4),
            "kelly_inteiro_pct": round(100 * m / v, 3), "fracao": fracao}


def ajustar_correlacao(risco_pct, n_posicoes, rho):
    """Com n posicoes correlacionadas (rho) a variancia agregada cresce ~ n*(1+(n-1)*rho): divide para manter o
    risco agregado equivalente ao de uma posicao independente."""
    n = max(1, int(n_posicoes))
    return risco_pct / math.sqrt(1 + (n - 1) * max(0.0, min(1.0, rho)))


def dimensionar(risco_pct, stop_pct, alavancagem, custo_ida_volta_pct, limites):
    """Separa nocional, margem, perda maxima e risco; corta pelo teto experimental (nocional 4%) e pelos limites
    AUTORIZADOS (lidos, nunca alterados). stop_pct: distancia ao stop em % do preco."""
    if stop_pct <= 0 or alavancagem <= 0:
        return None
    teto_risco = float(limites.get("risco_max_pct") or 0)
    r = min(risco_pct, teto_risco) if teto_risco else risco_pct
    nocional = 100 * r / (stop_pct + custo_ida_volta_pct)
    cortado_nocional = nocional > TETO_NOCIONAL_EXPERIMENTAL
    nocional = min(nocional, TETO_NOCIONAL_EXPERIMENTAL)
    perda = nocional * (stop_pct + custo_ida_volta_pct) / 100
    return {"nocional_pct": round(nocional, 4), "margem_pct": round(nocional / alavancagem, 4),
            "perda_max_pct": round(perda, 4), "risco_pct": round(perda, 4),
            "cortado_pelo_teto_nocional": cortado_nocional, "cortado_pelo_limite_autorizado": r < risco_pct}


# ------------------------------------------------------------- simulacao ---------------------------------------
def monte_carlo(rs, risco_pct, ops_mes, meses=12, custo_mes_pct=0.0, n=2000, ruina_pct=50.0, seed=7,
                meses_sem_ops=0):
    """Capital (100 = inicial) com reamostragem das operacoes, risco fixo em % do capital corrente, custos mensais
    em % do capital INICIAL (fixos, como uma fatura) e meses sem oportunidades. Devolve percentis e risco de ruina
    (queda abaixo de ruina_pct% do inicial em algum momento)."""
    rs = [float(x) for x in rs]
    if not rs:
        return None
    rng = random.Random(seed)
    finais, dds, ruinas = [], [], 0
    for _ in range(n):
        cap, pico, dd, ruina = 100.0, 100.0, 0.0, False
        for m in range(meses):
            k = 0 if m < meses_sem_ops else ops_mes
            for _ in range(k):
                cap += cap * risco_pct / 100 * rs[rng.randrange(len(rs))]
            cap -= custo_mes_pct
            pico = max(pico, cap)
            dd = max(dd, (pico - cap) / pico * 100 if pico > 0 else 100)
            if cap <= ruina_pct:
                ruina = True
            if cap <= 0:
                cap = 0.0
                break
        finais.append(cap)
        dds.append(dd)
        ruinas += ruina
    finais.sort()
    dds.sort()
    q = lambda xs, p: round(xs[int(p * (len(xs) - 1))], 2)
    return {"capital_final_p05": q(finais, 0.05), "capital_final_mediana": q(finais, 0.5),
            "capital_final_p95": q(finais, 0.95), "drawdown_mediano_pct": q(dds, 0.5), "drawdown_p95_pct": q(dds, 0.95),
            "risco_ruina_pct": round(100 * ruinas / n, 2)}


def tesouraria(rs, risco_pct, ops_mes, custo_mensal_em_capital_pct=None):
    """Autossustentabilidade em multiplos do custo mensal (sem dinheiro no repositorio):
      retorno_mes_pct = ops_mes * risco_pct * media_R (% do capital por mes, esperado)
      capital_minimo  = custo_mensal / retorno_mes  -> 'capital_minimo_em_custos_mensais' (x custo mensal)
    Distribuicao simulada de cada lucro mensal: 1) custos operacionais, 2) reserva de seguranca (25% do resto),
    3) crescimento da banca (o restante); distribuicao ao dono = 0 enquanto a reserva < 6 meses de custos."""
    rs = [float(x) for x in rs]
    if not rs:
        return {"estado": "sem operacoes"}
    m = sum(rs) / len(rs)
    ret = ops_mes * risco_pct * m
    out = {"media_r": round(m, 4), "ops_mes": ops_mes, "risco_pct": risco_pct,
           "retorno_mes_esperado_pct": round(ret, 4)}
    if ret <= 0:
        out.update(estado="NAO SUSTENTAVEL: retorno esperado <= 0", capital_minimo_em_custos_mensais=None)
        return out
    out["capital_minimo_em_custos_mensais"] = round(100 / ret, 1)
    out["regra_de_distribuicao"] = ["custos operacionais", "reserva de seguranca 25% do resto",
                                    "crescimento da banca (resto)", "distribuicao 0 ate reserva >= 6 meses de custos"]
    if custo_mensal_em_capital_pct is not None:
        c = float(custo_mensal_em_capital_pct)
        out["custo_mensal_pct_do_capital"] = c
        out["margem_mes_pct"] = round(ret - c, 4)
        out["estado"] = "SUSTENTAVEL EM ESPERANCA" if ret > c else "NAO SUSTENTAVEL com este capital"
    return out


# ------------------------------------------------------------ sobrevivencia ------------------------------------
LIMITES_SOBREVIVENCIA = {"drawdown_r": 8.0, "perdas_seguidas": 6, "janela": 30, "media_min_r": -0.15,
                         "falhas_execucao": 3}


def sobrevivencia(rs, falhas_execucao=0, limites=None):
    """Bloqueia NOVAS entradas do ambiente experimental quando um limite e ultrapassado. Nunca fecha nem abandona
    posicoes abertas (a gestao continua): devolve so a decisao e os motivos, para registo e alerta."""
    L = dict(LIMITES_SOBREVIVENCIA, **(limites or {}))
    rs = [float(x) for x in rs]
    motivos = []
    eq = pico = dd = 0.0
    for x in rs:
        eq += x
        pico = max(pico, eq)
        dd = max(dd, pico - eq)
    if dd >= L["drawdown_r"]:
        motivos.append(f"drawdown {dd:.2f}R >= {L['drawdown_r']}R")
    seguidas = 0
    for x in reversed(rs):
        if x < 0:
            seguidas += 1
        else:
            break
    if seguidas >= L["perdas_seguidas"]:
        motivos.append(f"{seguidas} perdas seguidas")
    ult = rs[-L["janela"]:]
    if len(ult) >= L["janela"] and sum(ult) / len(ult) < L["media_min_r"]:
        motivos.append(f"media das ultimas {L['janela']} = {sum(ult) / len(ult):+.3f}R (expectativa degradada)")
    if falhas_execucao >= L["falhas_execucao"]:
        motivos.append(f"{falhas_execucao} falhas de execucao")
    return {"novas_entradas": not motivos, "motivos": motivos, "drawdown_r": round(dd, 3),
            "perdas_seguidas": seguidas, "posicoes_abertas": "geridas normalmente (nunca abandonadas)"}


def stress(rs, risco_pct, ops_mes):
    """Cenarios adversos sobre a mesma distribuicao: custos a dobrar (-0,05R por op), meses sem operacoes,
    sequencia de perdas no inicio."""
    base = monte_carlo(rs, risco_pct, ops_mes)
    piores = [x - 0.05 for x in rs]
    return {"base": base,
            "custos_a_dobrar": monte_carlo(piores, risco_pct, ops_mes),
            "tres_meses_sem_operacoes": monte_carlo(rs, risco_pct, ops_mes, meses_sem_ops=3),
            "inicio_com_10_perdas": monte_carlo([-1.0] * 10 + rs, risco_pct, ops_mes)}


# ------------------------------------------------------------------ main ----------------------------------------
def series_do_estado(St):
    """{(modo, estrategia): [R]} das operacoes fechadas do registo publico (ordem de fecho)."""
    out = {}
    for r in sorted(St.get("ledger") or [], key=lambda r: r.get("closed_at") or 0):
        if r.get("status") != "CLOSED" or r.get("result_r") is None:
            continue
        modo = r.get("mode") or "?"
        if modo == "REAL" and r.get("executed") is not True:
            continue
        out.setdefault((modo, r.get("strategy")), []).append(float(r.get("real_r") or r["result_r"]))
        if modo == "REAL":
            out.setdefault(("REAL", "TODAS"), []).append(float(r.get("real_r") or r["result_r"]))
    for est, v in (St.get("paper_ring") or {}).items():               # papel continuo da arena
        rs = [float(c["r"]) for c in sorted(v.get("closed") or [], key=lambda c: c.get("closed_at") or 0)
              if c.get("r") is not None]
        if rs:
            out[("PAPEL", est)] = rs
    return out


def series_do_edge(E):
    """{("TESTE_FORA_DA_AMOSTRA", hipotese): [R]} do tools/qo_edge (operacoes do periodo de teste)."""
    return {("TESTE_FORA_DA_AMOSTRA", "QO " + k): v.get("rs_teste") or []
            for k, v in ((E or {}).get("hipoteses") or {}).items() if v.get("rs_teste")}


def main(state_p, dest, edge_p=None, limites=None):
    with open(state_p, encoding="utf-8") as f:
        St = json.load(f)
    E = None
    if edge_p:
        with open(edge_p, encoding="utf-8") as f:
            E = json.load(f)
    lim = limites or {"risco_max_pct": 5.0}
    res = {}
    todas = {**series_do_estado(St), **series_do_edge(E)}
    for (modo, est), rs in sorted(todas.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 10:
            continue
        k = kelly_prudente(rs)
        ops_mes = 8
        risco = k["risco_pct"]
        res[f"{modo}|{est}"] = {
            "n": len(rs), "media_r": round(sum(rs) / len(rs), 4), "kelly_r_inteiro_pct": round(100 * kelly_r(rs), 3),
            "kelly_prudente": k, "fracoes": {str(f): kelly_prudente(rs, fracao=f)["risco_pct"] for f in (0.1, 0.25, 0.5)},
            "dimensao_exemplo_stop5_alav5": dimensionar(risco, 5.0, 5, 0.5, lim) if risco else None,
            "tesouraria": tesouraria(rs, max(risco, 0.5), ops_mes),
            "sobrevivencia": sobrevivencia(rs),
            "stress_risco_0_5pct": stress(rs, 0.5, ops_mes)}
    out = {"modo": "SIMULACAO (sem ordens, sem dinheiro)", "limites_autorizados_lidos": lim, "estrategias": res}
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    r = main(*sys.argv[1:4])
    for k, v in r["estrategias"].items():
        print(k, v["n"], v["media_r"], v["kelly_prudente"].get("risco_pct"), v["tesouraria"].get("estado"),
              v["sobrevivencia"]["novas_entradas"])
