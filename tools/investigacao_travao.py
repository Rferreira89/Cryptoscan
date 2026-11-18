"""(18/11, investigacao isolada; NAO e implementacao) Proposta de travao automatico por resultados negativos:
simula regras candidatas e mede falsos bloqueios (estrategias com vantagem real bloqueadas) e perdas evitadas.

Distribuicao das operacoes: R reais do ringue longo (ultimas operacoes de todos os lutadores, arena-longo/longo.json),
centradas e deslocadas para cada vantagem verdadeira mu. Dois modos: operacoes independentes, e "fases" (a vantagem
alterna +-0,15R em fases de 25 operacoes, com a mesma media mu: imita boas e mas fases de mercado).
Uso: python -m tools.investigacao_travao <longo.json> <saida.json>"""
import json
import math
import statistics
import sys

HORIZONTE = 150
MUS = (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20)
SIMS = 4000
FASE, AMPL = 25, 0.15


import numpy as np


def regras():
    """Cada regra recebe a matriz R (sims x HORIZONTE) e devolve uma matriz booleana 'bloqueia depois da op. k'."""
    def prefixos(R):
        n = np.arange(1, R.shape[1] + 1)
        c = R.cumsum(1)
        c2 = (R ** 2).cumsum(1)
        m = c / n
        var = np.maximum(c2 / n - m ** 2, 1e-9)
        return n, c, m, var
    def media_neg(n_min):
        def f(R):
            n, _, m, _ = prefixos(R)
            return (n >= n_min) & (m < 0)
        return f
    def t_neg(n_min, z):
        def f(R):
            n, _, m, var = prefixos(R)
            return (n >= n_min) & (m / np.sqrt(var / n) < -z)
        return f
    def pontos(cps, lim):
        def f(R):
            n, _, m, _ = prefixos(R)
            return np.isin(n, list(cps)) & (m < lim)
        return f
    def queda(x):
        def f(R):
            c = R.cumsum(1)
            pico = np.maximum(np.maximum.accumulate(c, 1), 0)
            return pico - c >= x
        return f
    def bayes(n_min, p, prior_sd=0.15):
        from math import erf, sqrt
        def f(R):
            n, _, m, var = prefixos(R)
            prec = 1 / prior_sd ** 2 + n / var
            pm, psd = (n / var * m) / prec, np.sqrt(1 / prec)
            z = (0 - pm) / (psd * sqrt(2))
            pr = 0.5 * (1 + np.vectorize(erf)(z))
            return (n >= n_min) & (pr > p)
        return f
    return {
        "K1 media<0 com n>=20 (regra atual do paper_ring)": media_neg(20),
        "K2 media<0 com n>=40": media_neg(40),
        "K3 t<-1,645 com n>=20 (vista continua)": t_neg(20, 1.645),
        "K4 t<-2,33 com n>=20 (vista continua)": t_neg(20, 2.33),
        "K5 media<-0,10 so nas revisoes n=30,60,100": pontos({30, 60, 100}, -0.10),
        "K6 queda >= 10R desde o pico": queda(10),
        "K7 Bayes P(mu<0)>0,95, n>=20": bayes(20, 0.95),
        "K8 Bayes P(mu<0)>0,90, n>=30": bayes(30, 0.90),
    }


def amostras(base, fases, mu, rng):
    if fases is None:
        return rng.choice(np.array(base), size=(SIMS, HORIZONTE)) + mu
    # fases de mercado: a vantagem alterna entre mu+AMPL e mu-AMPL em fases de FASE operacoes (inicio ao acaso);
    # a media ao longo do horizonte continua a ser mu
    k = (np.arange(HORIZONTE)[None, :] + rng.integers(0, 2 * FASE, size=(SIMS, 1))) // FASE % 2
    return rng.choice(np.array(base), size=(SIMS, HORIZONTE)) + mu + np.where(k == 0, AMPL, -AMPL)


def main(src, dest):
    d = json.load(open(src))
    seqs = [v["ultimas"] for v in d["lutadores"].values() if isinstance(v, dict) and len(v.get("ultimas") or []) >= 10]
    todos = [r for s in seqs for r in s]
    m0 = statistics.mean(todos)
    base = [r - m0 for r in todos]
    out = {"operacoes_base": len(base), "lutadores": len(seqs), "media_original": round(m0, 4),
           "desvio": round(statistics.pstdev(base), 3), "horizonte": HORIZONTE, "sims": SIMS, "regras": {}}
    rng = np.random.default_rng(2026)
    mats = {(modo, mu): amostras(base, bl, mu, rng) for modo, bl in (("independentes", None), ("fases", True))
            for mu in MUS}
    for nome, regra in regras().items():
        out["regras"][nome] = {}
        for modo in ("independentes", "fases"):
            linha = {}
            for mu in MUS:
                M = regra(mats[(modo, mu)])
                hit = M.any(1)
                ns = list((M.argmax(1) + 1)[hit])
                p = hit.mean()
                # R esperado por sequencia: evitado (mu<0) ou perdido (mu>0) = |mu| x operacoes nao feitas
                nao_feitas = sum(HORIZONTE - k for k in ns) / SIMS
                linha[str(mu)] = {"p_bloqueio": round(float(p), 3), "n_mediano_bloqueio": int(np.median(ns)) if ns else None,
                                  "R_evitado" if mu < 0 else "R_perdido": round(float(abs(mu) * nao_feitas), 2)}
            out["regras"][nome][modo] = linha
        print(nome, {m: {mu: (v["p_bloqueio"], v.get("R_evitado", v.get("R_perdido"))) for mu, v in out["regras"][nome][m].items()} for m in out["regras"][nome]}, flush=True)
    with open(dest, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
