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
from tools.hunter import dados as DD, estat as ES, motor as MO


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


def main(pasta, dias=240, n_max=None, orcamento=400):
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
    res = MO.correr(dados, reg, log=lambda m: print(m, flush=True), orcamento_evolucao=int(orcamento))
    reg.guardar()
    # risco e tesouraria (simulacao) sobre as operacoes da validacao das melhores
    risco = {}
    for k, v in res["hipoteses"].items():
        if v["veredicto"] in ("CANDIDATA", "PROMISSORA", "EXPLORATORIA"):
            ops = v.get("_ops_validacao") or []
            if ops:
                rs = [r for _, r in ops]
                cr = comparar_risco(ops)
                risco[k] = {"niveis": cr, "tesouraria_risco_0_5pct": AU.tesouraria(
                    rs, 0.5, max(1, int(cr.get("dias_com_operacoes_por_mes", 1) * 3))),
                            "sobrevivencia": AU.sobrevivencia(rs),
                            "aviso": "simulacao sobre a VALIDACAO (dados historicos); nao e rentabilidade comprovada"}
    res["risco_simulado"] = risco
    res["funil_dados"] = funil
    res["segundos_total"] = round(time.time() - t0)
    data = time.strftime("%Y-%m-%d", time.gmtime(now))
    with open(p(f"pesquisa_{data}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    with open(p("papel_estrategias.json"), "w", encoding="utf-8") as f:
        json.dump({"t": now, "origem": f"pesquisa_{data}.json", "estrategias": res["papel"]}, f, ensure_ascii=False, indent=1)
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
