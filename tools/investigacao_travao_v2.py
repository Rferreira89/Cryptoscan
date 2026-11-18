"""(18/11, ordem final, prioridade 5) Comparacao rigorosa das regras de corte do papel. Investigacao: nao muda nada.

Regras: K1 (atual do paper_ring: media < 0 com n >= 20), K4 (t < -2,33 com n >= 20), K8 (Bayes P(mu<0) > 0,90 com
n >= 30, prior N(0; 0,15^2)). Todas verificadas a cada operacao fechada (como o paper_ring faz).

Distribuicao: R reais do ringue longo (arena-longo/longo.json). Calibracao: 'ultimas' de metade dos lutadores
(sorteio fixo); fora da amostra: a outra metade, e as 'ultimas' por regime (outras operacoes, outra forma).
Cada amostra e centrada e deslocada para a vantagem verdadeira mu (os custos ja estao nos R; um custo extra por
operacao e o mesmo que baixar mu, por isso a grelha de mu cobre-o; mostra-se tambem mu - 0,05 como 'custos +0,05R').

Dependencia temporal (tres modos):
  indep   operacoes independentes;
  fases   a vantagem alterna +-0,15R em fases de 25 operacoes (boas e mas fases de mercado), media mu;
  grupos  operacoes em grupos de 3 da mesma vela com um choque comum (correlacao ~0,5 dentro do grupo): nao sao
          observacoes independentes.
Horizontes 50, 100, 150 e 300 operacoes. 3000 sequencias por celula; sementes diferentes por celula.
Uso: python -m tools.investigacao_travao_v2 <longo.json> <saida.json>"""
import json
import math
import statistics
import sys

import numpy as np

MUS = (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20)
HORIZONTES = (50, 100, 150, 300)
SIMS = 3000
FASE, AMPL = 25, 0.15
GRUPO, RHO = 3, 0.5


def prefixos(R):
    n = np.arange(1, R.shape[1] + 1)
    c, c2 = R.cumsum(1), (R ** 2).cumsum(1)
    m = c / n
    return n, m, np.maximum(c2 / n - m ** 2, 1e-9)


def K1(R):
    n, m, _ = prefixos(R)
    return (n >= 20) & (m < 0)


def K4(R):
    n, m, v = prefixos(R)
    return (n >= 20) & (m / np.sqrt(v / n) < -2.33)


def K8(R, prior_sd=0.15, p=0.90):
    n, m, v = prefixos(R)
    prec = 1 / prior_sd ** 2 + n / v
    pm, psd = (n / v * m) / prec, np.sqrt(1 / prec)
    z = -pm / psd
    return (n >= 30) & (0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2))) > p)


REGRAS = {"K1 atual (media<0, n>=20)": K1, "K4 t<-2,33 (n>=20)": K4, "K8 Bayes P(mu<0)>0,90 (n>=30)": K8}


def amostras(base, mu, modo, H, rng):
    b = np.array(base)
    sd = b.std()
    if modo == "indep":
        return rng.choice(b, size=(SIMS, H)) + mu
    if modo == "fases":
        k = (np.arange(H)[None, :] + rng.integers(0, 2 * FASE, size=(SIMS, 1))) // FASE % 2
        return rng.choice(b, size=(SIMS, H)) + mu + np.where(k == 0, AMPL, -AMPL)
    # grupos: choque comum por grupo de 3 (mesma vela), variancia total igual a da amostra
    g = rng.normal(0, sd * math.sqrt(RHO), size=(SIMS, H // GRUPO + 1)).repeat(GRUPO, 1)[:, :H]
    e = rng.choice(b, size=(SIMS, H)) * math.sqrt(1 - RHO)
    return e + g + mu


def celula(regra, base, mu, modo, H, rng):
    M = regra(amostras(base, mu, modo, H, rng))
    hit = M.any(1)
    k = M.argmax(1) + 1
    nao_feitas = np.where(hit, H - k, 0)
    return {"p_corte": round(float(hit.mean()), 3),
            "n_mediano_corte": int(np.median(k[hit])) if hit.any() else None,
            ("R_evitado" if mu < 0 else "R_perdido"): round(float(abs(mu) * nao_feitas.mean()), 2)}


def main(src, dest):
    d = json.load(open(src))
    L = {k: v for k, v in d["lutadores"].items() if isinstance(v, dict) and len(v.get("ultimas") or []) >= 10}
    nomes = sorted(L)
    rng0 = np.random.default_rng(18)
    perm = list(rng0.permutation(len(nomes)))
    A = [nomes[i] for i in perm[: len(nomes) // 2]]
    B = [nomes[i] for i in perm[len(nomes) // 2:]]
    def centrar(xs):
        m = statistics.mean(xs)
        return [x - m for x in xs]
    bases = {
        "calibracao (metade A, ultimas)": centrar([r for k in A for r in L[k]["ultimas"]]),
        "fora da amostra (metade B, ultimas)": centrar([r for k in B for r in L[k]["ultimas"]]),
        "fora da amostra (ultimas por regime)": centrar([r for v in d["lutadores"].values() if isinstance(v, dict)
                                                         for x in (v.get("por_regime") or {}).values()
                                                         if isinstance(x, dict) for r in x.get("ultimas") or []]),
    }
    out = {"bases": {k: {"n": len(v), "desvio": round(statistics.pstdev(v), 3),
                         "assimetria": round(float(np.mean((np.array(v) / np.std(v)) ** 3)), 2)} for k, v in bases.items()},
           "sims": SIMS, "modos": ["indep", "fases", "grupos"], "horizontes": HORIZONTES, "resultados": {}}
    semente = 100
    for bn, base in bases.items():
        out["resultados"][bn] = {}
        for rn, regra in REGRAS.items():
            out["resultados"][bn][rn] = {}
            for modo in ("indep", "fases", "grupos"):
                for H in HORIZONTES:
                    linha = {}
                    for mu in MUS:
                        semente += 1
                        linha[str(mu)] = celula(regra, base, mu, modo, H, np.random.default_rng(semente))
                    out["resultados"][bn][rn][f"{modo}|{H}"] = linha
            print(bn, rn, "fases|150", {m: v["p_corte"] for m, v in out["resultados"][bn][rn]["fases|150"].items()},
                  flush=True)
    with open(dest, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
