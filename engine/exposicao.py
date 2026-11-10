"""(ordem do Rui de 10/11, ponto 5) Mapa diario de exposicao e correlacao: que posicoes e sinais sao, na pratica, a
MESMA aposta.

Entrada: fechos (ex.: velas de 1 h dos ultimos 30 dias) por ativo e a lista de exposicoes (posicoes reais, ordens
pendentes, sinais de papel/sombra) com o lado (LONG/SHORT). Saida, sem valores em dinheiro:
  - grupos de ativos com correlacao >= limiar (engine.guarda.grupos_por_correlacao);
  - por grupo e lado, quantas exposicoes caem na mesma aposta;
  - numero efetivo de apostas independentes: n / (1 + (n - 1) * rho_medio), com o sinal de cada lado (um long e um
    short no mesmo grupo cancelam-se em parte: entram com correlacao negativa).
So leitura e calculo: nao esta ligado a nenhum executor nem bloqueia nada."""
import math

from engine import guarda as G


def retornos(fechos):
    return {a: [c[i] / c[i - 1] - 1 for i in range(1, len(c)) if c[i - 1]] for a, c in fechos.items()}


def correlacao(x, y):
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x, y = x[-n:], y[-n:]
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x)); sy = math.sqrt(sum((v - my) ** 2 for v in y))
    return sum((p - mx) * (q - my) for p, q in zip(x, y)) / (sx * sy) if sx and sy else 0.0


def apostas_efetivas(exposicoes, rets):
    """exposicoes: [(ativo, lado)]. Numero efetivo de apostas independentes (1 = tudo a mesma aposta)."""
    xs = [(a, 1 if l == "LONG" else -1) for a, l in exposicoes if a in rets]
    n = len(xs)
    if n <= 1:
        return float(n)
    pares = [s1 * s2 * correlacao(rets[a1], rets[a2]) for i, (a1, s1) in enumerate(xs) for a2, s2 in xs[i + 1:]]
    rho = sum(pares) / len(pares)
    den = 1 + (n - 1) * rho
    return round(n / den, 2) if den > 0 else float(n)


def mapa(fechos, exposicoes, limiar=0.7):
    """fechos: {ativo: [fechos]}; exposicoes: [{'ativo', 'lado', 'origem'}]."""
    rets = retornos(fechos)
    grupos = G.grupos_por_correlacao(rets, limiar)
    por = {}
    for e in exposicoes:
        g = grupos.get(e["ativo"], f"sem_dados:{e['ativo']}")
        por.setdefault((g, e["lado"]), []).append(e)
    concentracoes = [{"grupo": g, "lado": l, "n": len(v), "ativos": sorted({x["ativo"] for x in v}),
                      "origens": sorted({x.get("origem") or "?" for x in v})}
                     for (g, l), v in por.items() if len(v) > 1]
    return {"grupos": grupos, "concentracoes": sorted(concentracoes, key=lambda c: -c["n"]),
            "n_exposicoes": len(exposicoes),
            "apostas_efetivas": apostas_efetivas([(e["ativo"], e["lado"]) for e in exposicoes], rets)}
