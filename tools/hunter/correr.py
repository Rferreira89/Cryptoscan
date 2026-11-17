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


def comparar_risco(rs, ops_mes):
    """Niveis de risco so em simulacao (R por operacao -> capital): Kelly 0,1/0,25/0,5/1 e fixos 0,25/0,5/1/2%."""
    out = {}
    k = AU.kelly_r(rs)
    niveis = {f"kelly_{f}": 100 * f * k for f in (0.1, 0.25, 0.5, 1.0)}
    niveis.update({f"fixo_{x}pct": x for x in (0.25, 0.5, 1.0, 2.0)})
    for nome, risco in niveis.items():
        risco = min(risco, 20.0)
        mc = AU.monte_carlo(rs, risco, ops_mes, meses=12, n=1000) if risco > 0 else None
        out[nome] = {"risco_pct": round(risco, 3), **(mc or {"nota": "Kelly = 0 (sem media positiva)"})}
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
            dias_val = max(1, (res["cortes"]["validacao_ate"] - res["cortes"]["treino_ate"]) / 86400)
            ops_mes = max(1, int(v["validacao"]["n"] / dias_val * 30))
            rs = v.get("_rs_validacao") or []
            if rs:
                risco[k] = {"ops_mes": ops_mes, "niveis": comparar_risco(rs, ops_mes),
                            "tesouraria": AU.tesouraria(rs, 0.5, ops_mes), "sobrevivencia": AU.sobrevivencia(rs)}
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
