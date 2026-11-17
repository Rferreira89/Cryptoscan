"""Corrida completa de investigacao do Hunter (workflow hunter-pesquisa no ramo de investigacao).

Uso: python -m tools.hunter.correr <pasta_autonomo> [dias] [n_max] [orcamento_evolucao]
Le e atualiza na pasta (copia do ramo autonomo): hunter/registo.json (Holm cumulativo e acessos ao teste final),
hunter/universo_historico.json (instrumentos vistos e desaparecidos). Escreve hunter/pesquisa_<data>.json,
hunter/papel_estrategias.json (o que o papel corre a seguir) e hunter/funil_dados.json.
"""
import json
import os
import sys
import time

from tools import autonomo as AU
from tools.hunter import dados as DD, estat as ES, familias as FA, motor as MO, painel as PN

MAX_PAPEL = 16
OPS_PAINEL = {}


def comparar_risco(ops, max_simultaneas=3, meses=12, n=1000, seed=7):
    """Niveis de risco SO em simulacao, com as operacoes agrupadas por DIA (as de um mesmo dia sao o mesmo
    acontecimento: no maximo max_simultaneas por dia, as primeiras pela hora) e reamostragem de dias inteiros.
    ops: [(t, r)]. Kelly calculado sobre o R diario por posicao; Kelly 0,1/0,25/0,5/1 e fixos 0,25/0,5/1/2%.
    O teto experimental de 4% e de NOCIONAL por posicao (tools/autonomo.dimensionar), nao de risco."""
    import random as _r
    dias = {}
    for t, r in sorted(ops):
        dias.setdefault(int(t) // 86400, []).append(r)
    blocos = [v[:max_simultaneas] for v in dias.values()]
    if not blocos:
        return {}
    span = max(1, (max(dias) - min(dias) + 1))
    dias_mes = 30 * len(blocos) / span
    por_pos = [x for b in blocos for x in b]
    k = AU.kelly_r(por_pos)
    niveis = {f"kelly_{f}": 100 * f * k for f in (0.1, 0.25, 0.5, 1.0)}
    niveis.update({f"fixo_{x}pct": x for x in (0.25, 0.5, 1.0, 2.0)})
    out = {"dias_com_operacoes": len(blocos), "dias_com_operacoes_por_mes": round(dias_mes, 2),
           "max_posicoes_simultaneas": max_simultaneas, "kelly_inteiro_pct": round(100 * k, 3)}
    rng = _r.Random(seed)
    for nome, risco in niveis.items():
        risco = min(risco, 10.0)
        if risco <= 0:
            out[nome] = {"risco_pct": 0.0, "nota": "Kelly = 0 (sem media positiva)"}
            continue
        finais, dds, ruinas = [], [], 0
        for _ in range(n):
            cap, pico, dd = 100.0, 100.0, 0.0
            for _ in range(int(round(dias_mes * meses))):
                b = blocos[rng.randrange(len(blocos))]
                cap += sum(cap * risco / 100 * x for x in b)       # as posicoes do dia correm em simultaneo
                pico = max(pico, cap)
                dd = max(dd, (pico - cap) / pico * 100 if pico > 0 else 100)
                if cap <= 0:
                    cap = 0.0
                    break
            finais.append(cap)
            dds.append(dd)
            ruinas += cap <= 50
        finais.sort()
        dds.sort()
        q = lambda xs, p: round(xs[int(p * (len(xs) - 1))], 2)
        out[nome] = {"risco_pct": round(risco, 3), "capital_12m_p05": q(finais, 0.05), "capital_12m_mediana": q(finais, 0.5),
                     "capital_12m_p95": q(finais, 0.95), "drawdown_mediano_pct": q(dds, 0.5), "drawdown_p95_pct": q(dds, 0.95),
                     "prob_acabar_abaixo_de_metade_pct": round(100 * ruinas / n, 2)}
    return out


def carteira(ops_por_est, max_por_acontecimento, custo_extra_r=0.0):
    """Carteira de todas as estrategias: uma posicao por moeda e por acontecimento (vela de sinal) e no maximo
    max_por_acontecimento posicoes em cada acontecimento (None = sem limite). Devolve [(t, r)]."""
    todas = sorted(((o["t"], o["b"], k, o["r"] - custo_extra_r) for k, ops in ops_por_est.items() for o in ops))
    vistos, por_ac, out = set(), {}, []
    for t, b, k, r in todas:
        if (b, t) in vistos:
            continue
        if max_por_acontecimento and por_ac.get(t, 0) >= max_por_acontecimento:
            continue
        vistos.add((b, t))
        por_ac[t] = por_ac.get(t, 0) + 1
        out.append((t, r))
    return out


def pior_sequencia(rs):
    n = m = 0
    for x in rs:
        n = n + 1 if x < 0 else 0
        m = max(m, n)
    return m


def risco_simulado(ops_por_est):
    """SO SIMULACAO (nada disto muda o risco real). Por estrategia e em carteira: limites de concentracao,
    risco variavel (Kelly 0,1/0,25/0,5) e fixo (0,25/0,5/1/2%), custos adversos (+0,1R por operacao),
    pior sequencia de perdas e cenario extremo (as 10% piores dias repetidos)."""
    out = {"aviso": "simulacao sobre treino+validacao (historico); nao e rentabilidade comprovada; "
                    "1% por operacao nao e recomendado quando o drawdown simulado e de 60-97%",
           "por_estrategia": {}, "carteira": {}}
    for k, ops in ops_por_est.items():
        par = [(o["t"], o["r"]) for o in ops]
        if par:
            out["por_estrategia"][k] = {"niveis": comparar_risco(par), "pior_sequencia_de_perdas": pior_sequencia([r for _, r in sorted(par)])}
    for lim in (1, 3, 5, None):
        c = carteira(ops_por_est, lim)
        if not c:
            continue
        nome = f"max{lim}_por_acontecimento" if lim else "sem_limite"
        adv = carteira(ops_por_est, lim, custo_extra_r=0.1)
        dias = {}
        for t, r in c:
            dias.setdefault(t // 86400, []).append(r)
        piores = sorted(dias.values(), key=lambda v: sum(v))[:max(1, len(dias) // 10)]
        extremo = [(d * 86400, x) for d, v in enumerate(piores * 3) for x in v]
        out["carteira"][nome] = {"operacoes": len(c), "acontecimentos": len({t for t, _ in c}),
                                 "r_medio": round(sum(r for _, r in c) / len(c), 4),
                                 "pior_sequencia_de_perdas": pior_sequencia([r for _, r in sorted(c)]),
                                 "niveis": comparar_risco(c, max_simultaneas=lim or 10),
                                 "custos_adversos_mais_0_1R": comparar_risco(adv, max_simultaneas=lim or 10),
                                 "cenario_extremo_piores_dias": comparar_risco(extremo, max_simultaneas=lim or 10, meses=3)}
    return out


def _ler(caminho, padrao):
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    return padrao


def painel_e_estados(p, dados, SS, MM, cortes, res, reg, now):
    """Mantem as estrategias ja em papel (as 8 de 17/11), junta as novas desta ronda (ate MAX_PAPEL), calcula o
    painel de cada uma em treino+validacao e aplica a maquina de estados. Escreve papel_estrategias.json."""
    antes = _ler(p("papel_estrategias.json"), {"estrategias": []})["estrategias"]
    est_papel = _ler(p("papel_estado.json"), {}).get("resumo") or {}
    estados = _ler(p("estados.json"), {"estrategias": {}})
    lista = {e["id"]: e for e in antes}
    chave = lambda e: (e["familia"], e["tf"], e["lado"], e.get("filtro"))
    for e in res["papel"]:
        # (17/11) sem clones: uma variante nova da mesma familia/tf/lado/filtro nao entra (a ja em papel continua)
        if e["id"] not in lista and chave(e) not in {chave(x) for x in lista.values()} and len(lista) < MAX_PAPEL:
            lista[e["id"]] = e
    painel, final = {}, []
    for k, e in lista.items():
        sig = MO.sinais(SS, MM, e["tf"], e["familia"], e["parametros"], e["lado"])
        inv = MO.inverso_de(SS, MM, e)
        ops = []
        for per in ("treino", "validacao"):
            ops += MO.operacoes(SS, MM, dados, e["tf"], sig, e["lado"], e["saida"], e["stop_ref"], per, cortes,
                                filtro=MO.FILTROS.get(e.get("filtro")), inverso=inv)
        m = PN.metricas(ops)
        hv = res["hipoteses"].get(k) or {}
        p_holm = hv.get("p_holm_validacao", (estados["estrategias"].get(k) or {}).get("p_holm"))
        teste = (reg.d["acessos_teste"].get(k) or {}).get("resultado")
        pa = est_papel.get(k)
        crit = PN.criterios(m, p_holm, teste, pa)
        rej = PN.rejeicao_papel(pa)
        estado, porque = PN.estado(m, crit, em_papel=True, rejeitar_papel=rej)
        anterior = (estados["estrategias"].get(k) or {}).get("estado")
        hist = (estados["estrategias"].get(k) or {}).get("historico") or []
        if estado != anterior:
            hist.append({"t": now, "de": anterior, "para": estado, "porque": porque})
        estados["estrategias"][k] = {"estado": estado, "porque": porque, "p_holm": p_holm, "historico": hist,
                                    "nome": f"{e['familia']} {e['tf']} {e['lado']}" + (f" ({e['filtro']})" if e.get("filtro") else "")}
        OPS_PAINEL[k] = ops
        painel[k] = {"estrategia": {q: e.get(q) for q in ("familia", "parametros", "tf", "lado", "filtro", "stop_ref", "saida")},
                     "hipotese_economica": FA.HIPOTESES.get(e["familia"]), "estado": estado, "porque": porque,
                     "backtest_treino_validacao": m, "papel": pa, "teste_final": teste or "nao usado",
                     "criterios_por_cumprir": [c for c, ok, _ in crit if not ok],
                     "criterios": [{"criterio": c, "ok": ok, "valor": v} for c, ok, v in crit]}
        if estado != "REJEITADA":
            final.append(dict(e, estado=estado))
    estados["t"] = now
    with open(p("papel_estrategias.json"), "w", encoding="utf-8") as f:
        json.dump({"t": now, "estrategias": final}, f, ensure_ascii=False, indent=1)
    return painel, estados


def registo_familias(res):
    """Por familia: hipotese economica, regime esperado, custos, riscos, resultado do diagnostico (treino) e da
    validacao, e a decisao fundamentada (para nao repetir a mesma investigacao com outro nome)."""
    out = {}
    for fam, (hip, regime, custos, riscos) in FA.HIPOTESES.items():
        dg = {k: v for k, v in res["diagnostico"].items() if k.split()[0] == fam and v.get("n_treino")}
        vs = [v for v in res["hipoteses"].values() if v["familia"] == fam]
        melhor = max((v["deriva_liquida_max_atr"] for v in dg.values()), default=None)
        onde = {}
        for v in dg.values():
            onde[v.get("onde_falha")] = onde.get(v.get("onde_falha"), 0) + 1
        estados = sorted({v["veredicto"] for v in vs})
        decisao = ("EM PAPEL / VALIDACAO" if any(x in ("CANDIDATA", "PROMISSORA", "EXPLORATORIA") for x in estados) else
                   "REJEITADA nesta ronda: " + (max(onde, key=onde.get) if onde else "sem sinais"))
        out[fam] = {"grupo": FA.GRUPO[fam], "hipotese": hip, "regime_esperado": regime, "custos_esperados": custos,
                    "riscos": riscos, "variantes_diagnostico": len(dg), "onde_falha": onde,
                    "melhor_deriva_liquida_atr_treino": melhor, "validacao": [
                        {"tf": v["tf"], "lado": v["lado"], "n": v["validacao"].get("n"), "r": v["validacao"].get("r_medio"),
                         "p_holm": v.get("p_holm_validacao"), "veredicto": v["veredicto"]} for v in vs],
                    "decisao": decisao}
    return out


def main(pasta, dias=240, n_max=None, orcamento=150):
    os.makedirs(os.path.join(pasta, "hunter"), exist_ok=True)
    p = lambda n: os.path.join(pasta, "hunter", n)
    t0 = time.time()
    now = int(time.time())
    dados, uni, funil = DD.recolher(int(dias), n_max and int(n_max), now=now)
    mud = DD.guardar_historico(p("universo_historico.json"), uni, now)
    funil["universo_novos"] = len(mud["novos"])
    funil["universo_desaparecidos"] = mud["desaparecidos"]
    funil["survivorship"] = ("os X-Perps deslistados antes da primeira corrida nao estao nos dados (a OKX so lista "
                             "os vivos); a partir de agora ficam no historico do universo")
    print("dados:", json.dumps({k: v for k, v in funil.items() if k not in ("excluidos", "falhas_api")}), flush=True)
    reg = ES.Registo(p("registo.json"))
    res = MO.correr(dados, reg, log=lambda m: print(m, flush=True), orcamento_evolucao=min(int(orcamento), 150))
    SS, MM, cortes = res.pop("_ctx")
    painel, estados = painel_e_estados(p, dados, SS, MM, cortes, res, reg, now)
    reg.guardar()
    res["painel"] = painel
    res["risco_simulado"] = risco_simulado(OPS_PAINEL)
    res["funil_dados"] = funil
    res["segundos_total"] = round(time.time() - t0)
    data = time.strftime("%Y-%m-%d", time.gmtime(now))
    with open(p(f"pesquisa_{data}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    with open(p("painel.json"), "w", encoding="utf-8") as f:
        json.dump({"t": now, "aviso": "treino + validacao (teste final intocado) e papel prospetivo; nada disto e real",
                   "estrategias": painel}, f, ensure_ascii=False, indent=1, default=str)
    with open(p("estados.json"), "w", encoding="utf-8") as f:
        json.dump(estados, f, ensure_ascii=False, indent=1)
    with open(p("familias_registo.json"), "w", encoding="utf-8") as f:
        json.dump(registo_familias(res), f, ensure_ascii=False, indent=1)
    with open(p("funil_dados.json"), "w", encoding="utf-8") as f:
        json.dump(funil, f, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    r = main(a[0], *(a[1:4]))
    from collections import Counter
    print("veredictos:", dict(Counter(v["veredicto"] for v in r["hipoteses"].values())))
    for k, v in sorted(r["hipoteses"].items(), key=lambda kv: -(kv[1]["validacao"].get("r_medio") or -9))[:15]:
        rv = v["validacao"]
        print(v["veredicto"], v["familia"], v["parametros"], v["tf"], v["lado"], v.get("filtro"), v["stop_ref"], v["saida"],
              "| val n", rv.get("n"), "R", rv.get("r_medio"), "vant", rv.get("vantagem_sobre_acaso"), "p_holm", v["p_holm_validacao"],
              "| teste", (v.get("teste") or {}).get("r_medio"))
