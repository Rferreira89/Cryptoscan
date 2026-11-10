"""Probabilidade de sobreajuste do backtest (PBO) por validacao cruzada simetrica combinatoria (CSCV).
Bailey, Borwein, Lopez de Prado e Zhu (2017), "The Probability of Backtest Overfitting", Journal of Computational
Finance 20(4).

Entrada: matriz M (T periodos x N configuracoes) com o desempenho de cada configuracao em cada periodo, por ordem
cronologica (por exemplo, R por dia de cada estrategia da arena).
  1. Divide as T linhas em S blocos contiguos (S par). Nao ha baralhar: a ordem temporal mantem-se.
  2. Para cada combinacao C de S/2 blocos (C(S, S/2) combinacoes): treino J = blocos em C, teste = os outros.
  3. Escolhe no treino a configuracao n* com melhor metrica (Sharpe por defeito).
  4. No teste, ordena as N configuracoes; w = posicao de n* / (N + 1) (1 = pior, N = melhor; empates pela media).
  5. lambda = ln(w / (1 - w)). PBO = fracao das combinacoes com lambda <= 0 (n* abaixo da mediana fora da amostra).
Tambem: degradacao (regressao do desempenho fora da amostra de n* sobre o de dentro) e probabilidade de perda fora.

Fugas de informacao: treino e teste sao sempre conjuntos disjuntos de blocos; com 'embargo' > 0 retiram-se do teste
as primeiras/ultimas 'embargo' linhas de cada bloco de teste que encosta a um bloco de treino (operacoes que atravessam
a fronteira nao contaminam o teste). A escolha de n* usa so o treino."""
import math
from itertools import combinations

from backtest.quant import estatistica as E

MIN_LINHAS_BLOCO = 5


def _metrica(col, tipo):
    if tipo == "media":
        return E.media(col)
    s = E.desvio(col) if len(col) > 1 else 0.0
    m = E.media(col)
    if s == 0:
        return 0.0 if m == 0 else math.copysign(1e9, m)
    return m / s


def _posicoes(valores):
    """Posicao de cada valor por ordem crescente (1 = pior), empates com a media das posicoes."""
    ordem = sorted(range(len(valores)), key=lambda i: valores[i])
    pos = [0.0] * len(valores)
    i = 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and valores[ordem[j + 1]] == valores[ordem[i]]:
            j += 1
        for k in range(i, j + 1):
            pos[ordem[k]] = (i + j) / 2 + 1
        i = j + 1
    return pos


def blocos(t, s):
    """Limites [inicio, fim) de s blocos contiguos; o resto da divisao vai para os ultimos blocos."""
    base, resto = divmod(t, s)
    out, ini = [], 0
    for b in range(s):
        fim = ini + base + (1 if b >= s - resto else 0)
        out.append((ini, fim)); ini = fim
    return out


def indices(lims, treino, embargo=0):
    """Linhas de treino e de teste para uma combinacao. Teste perde 'embargo' linhas junto a cada fronteira com treino."""
    s = len(lims)
    tr, te = [], []
    for b, (a, z) in enumerate(lims):
        if b in treino:
            tr.extend(range(a, z))
        else:
            a2 = a + (embargo if b - 1 >= 0 and (b - 1) in treino else 0)
            z2 = z - (embargo if b + 1 < s and (b + 1) in treino else 0)
            te.extend(range(a2, max(a2, z2)))
    return tr, te


def cscv(M, s=8, metrica="sharpe", embargo=0, nomes=None):
    t = len(M)
    n = len(M[0]) if t else 0
    out = {"t": t, "n": n, "s": s, "metrica": metrica, "embargo": embargo}
    if n < 2:
        return {**out, "estado": "insuficiente", "razao": "precisa de pelo menos 2 configuracoes"}
    if s < 2 or s % 2:
        return {**out, "estado": "insuficiente", "razao": "S tem de ser par e >= 2"}
    if t // s < MIN_LINHAS_BLOCO + 2 * embargo:
        return {**out, "estado": "insuficiente", "razao": f"{t} periodos para {s} blocos (minimo {MIN_LINHAS_BLOCO + 2 * embargo} por bloco)"}
    lims = blocos(t, s)
    lambdas, pares, escolhidas = [], [], {}
    for comb in combinations(range(s), s // 2):
        tr, te = indices(lims, set(comb), embargo)
        dentro = [_metrica([M[i][j] for i in tr], metrica) for j in range(n)]
        fora = [_metrica([M[i][j] for i in te], metrica) for j in range(n)]
        best = max(range(n), key=lambda j: (dentro[j], -j))           # empate: a primeira (deterministico)
        w = _posicoes(fora)[best] / (n + 1)
        lambdas.append(math.log(w / (1 - w)))
        pares.append((dentro[best], fora[best]))
        escolhidas[best] = escolhidas.get(best, 0) + 1
    pbo = sum(1 for x in lambdas if x <= 0) / len(lambdas)
    xs, ys = [p[0] for p in pares], [p[1] for p in pares]
    mx, my = E.media(xs), E.media(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    inclinacao = None if sxx == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    nome = (lambda j: nomes[j]) if nomes else (lambda j: j)
    return {**out, "estado": "calculado", "combinacoes": len(lambdas), "pbo": pbo, "lambda_mediana": sorted(lambdas)[len(lambdas) // 2],
            "lambdas": lambdas, "degradacao_inclinacao": inclinacao, "prob_perda_fora": sum(1 for y in ys if y < 0) / len(ys),
            "media_dentro": mx, "media_fora": my, "escolhidas": {nome(k): v for k, v in sorted(escolhidas.items(), key=lambda kv: -kv[1])},
            "veredito": "sobreajuste provavel: a melhor no treino fica abaixo da mediana fora" if pbo > 0.5 else
                        ("risco moderado de sobreajuste" if pbo > 0.2 else "selecao robusta fora da amostra")}


def matriz_diaria(series, dias=None):
    """series: {nome: {dia: valor}}. Devolve (dias ordenados, nomes, M) com 0 nos dias sem operacao (a estrategia
    estava disponivel mas nao fechou nada). Dias fora do intervalo comum a todas as series sao cortados para nao
    misturar periodos em que uma configuracao ainda nao existia com zeros."""
    nomes = sorted(series)
    ini = max(min(v) for v in series.values() if v)
    fim = min(max(v) for v in series.values() if v)
    todos = dias or sorted({d for v in series.values() for d in v})
    todos = [d for d in todos if ini <= d <= fim]
    return todos, nomes, [[series[n].get(d, 0.0) for n in nomes] for d in todos]
