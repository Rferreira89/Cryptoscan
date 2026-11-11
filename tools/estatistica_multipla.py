"""Estatistica para muitas hipoteses testadas contra os mesmos dados (auditoria
de 2026-11-11). Python puro (o ambiente do programa nao tem numpy).

O que resolve, e porque:
- prob_falso_positivo(k): a conta "1 - 0,95^k" do diario, mas declarada como o
  que e: um LIMITE sob independencia. Com estrategias correlacionadas o numero
  efetivo de testes e menor (n_efetivo_testes); com grelhas e maior.
- holm / benjamini_hochberg: controlo de multiplos testes sobre p-valores.
- p_acaso(): p-valor empirico de uma estrategia face as repeticoes do acaso.
- n_efetivo_testes(corr): numero efetivo de testes independentes a partir da
  matriz de correlacao dos resultados diarios (Nyholt 2004 e Li-Ji 2005).
- psr / dsr: Sharpe probabilistico e Sharpe deflacionado (Bailey e Lopez de
  Prado 2012/2014): corrige o Sharpe pela assimetria, curtose, amostra curta e
  pelo maximo esperado de N tentativas.
- pbo_cscv: probabilidade de sobreajustamento por validacao cruzada
  combinatoria simetrica (Bailey, Borwein, Lopez de Prado e Zhu 2015).
- eventos(): operacoes do mesmo instante contam como UM acontecimento. Foi a
  falha que a auditoria da BOUNCE_AMPLITUDE mostrou: 14 das 16 operacoes
  nasceram na mesma vela de 4H.
- acaso_agrupado(): teste contra o acaso em que as operacoes do mesmo
  acontecimento partilham o MESMO desvio ao acaso. O teste atual
  (engine/arena._dist) sorteia cada operacao a parte, o que estreita a
  distribuicao do acaso quando as operacoes estao agrupadas e facilita
  "passar o p95" com um so acontecimento.
"""
import bisect
import itertools
import math
import random

DAY = 86400


# ---------- normal ----------

def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def phi_inv(p):
    """Inversa da normal (Acklam), erro relativo < 1,2e-9."""
    if not 0.0 < p < 1.0:
        raise ValueError("p tem de estar em (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > hi:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# ---------- muitos testes ----------

def prob_falso_positivo(k, alfa=0.05):
    """P(pelo menos um falso positivo) com k testes INDEPENDENTES ao nivel alfa.
    E um limite de referencia, nao uma probabilidade exata."""
    return 1.0 - (1.0 - alfa) ** max(0, k)


def limiar_sidak(k, alfa=0.05):
    """Nivel por teste que mantem a taxa familiar em alfa com k testes."""
    return 1.0 - (1.0 - alfa) ** (1.0 / max(1, k))


def holm(pvals, alfa=0.05):
    """Holm-Bonferroni (passo a passo, controla a taxa familiar com qualquer
    dependencia). Devolve [(p, p_ajustado, rejeita)] pela ordem de entrada."""
    m = len(pvals)
    ordem = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    corrente = 0.0
    for r, i in enumerate(ordem):
        corrente = max(corrente, min(1.0, (m - r) * pvals[i]))
        adj[i] = corrente
    return [(pvals[i], adj[i], adj[i] <= alfa) for i in range(m)]


def benjamini_hochberg(pvals, q=0.10):
    """Taxa de falsas descobertas (BH). Devolve [(p, p_ajustado, descoberta)]."""
    m = len(pvals)
    ordem = sorted(range(m), key=lambda i: pvals[i], reverse=True)
    adj = [0.0] * m
    corrente = 1.0
    for r, i in enumerate(ordem):
        rank = m - r
        corrente = min(corrente, pvals[i] * m / rank)
        adj[i] = min(1.0, corrente)
    return [(pvals[i], adj[i], adj[i] <= q) for i in range(m)]


def p_acaso(valor, medias_acaso):
    """p-valor empirico unilateral: fracao das repeticoes do acaso >= valor,
    com a correcao (b + 1) / (n + 1) para nunca dar zero."""
    n = len(medias_acaso)
    if not n:
        return None
    b = sum(1 for x in medias_acaso if x >= valor)
    return (b + 1) / (n + 1)


# ---------- correlacao e numero efetivo de testes ----------

def correlacao(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def matriz_correlacao(series):
    """series: {nome: {dia: valor}}. Dias sem operacao contam 0 (fora do
    mercado), so nos dias em que pelo menos uma das duas operou."""
    nomes = sorted(series)
    m = [[1.0] * len(nomes) for _ in nomes]
    for i, a in enumerate(nomes):
        for j in range(i + 1, len(nomes)):
            b = nomes[j]
            dias = sorted(set(series[a]) | set(series[b]))
            r = correlacao([series[a].get(d, 0.0) for d in dias],
                           [series[b].get(d, 0.0) for d in dias])
            m[i][j] = m[j][i] = 0.0 if r is None else r
    return nomes, m


def valores_proprios(m, iters=100, tol=1e-12):
    """Valores proprios de uma matriz simetrica (metodo de Jacobi)."""
    n = len(m)
    a = [row[:] for row in m]
    for _ in range(iters):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < tol:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-15:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
    return sorted((a[i][i] for i in range(n)), reverse=True)


def n_efetivo_testes(m):
    """{nyholt, li_ji, participacao}: tres estimativas do numero de testes
    independentes equivalentes a matriz de correlacao m (M testes)."""
    lam = valores_proprios(m)
    M = len(lam)
    if M == 0:
        return {"M": 0, "nyholt": 0, "li_ji": 0, "participacao": 0}
    var = sum((x - 1.0) ** 2 for x in lam) / (M - 1) if M > 1 else 0.0
    nyholt = 1 + (M - 1) * (1 - var / M)
    li_ji = sum((1 if abs(x) >= 1 else 0) + (abs(x) - math.floor(abs(x))) for x in lam)
    part = sum(lam) ** 2 / sum(x * x for x in lam)
    return {"M": M, "nyholt": round(nyholt, 2), "li_ji": round(li_ji, 2),
            "participacao": round(part, 2)}


# ---------- Sharpe probabilistico e deflacionado ----------

def momentos(xs):
    n = len(xs)
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    if sd == 0:
        return mu, 0.0, 0.0, 3.0
    sk = sum(((x - mu) / sd) ** 3 for x in xs) / n
    ku = sum(((x - mu) / sd) ** 4 for x in xs) / n
    return mu, sd, sk, ku


def psr(xs, sr_ref=0.0):
    """Probabilidade de o Sharpe verdadeiro (por periodo) ser > sr_ref."""
    n = len(xs)
    if n < 3:
        return None
    mu, sd, sk, ku = momentos(xs)
    if sd == 0:
        return None
    sr = mu / sd
    den = 1 - sk * sr + (ku - 1) / 4 * sr * sr
    if den <= 0:
        return None
    return phi((sr - sr_ref) * math.sqrt(n - 1) / math.sqrt(den))


def sr_max_esperado(n_tentativas, var_sr):
    """Maximo esperado do Sharpe de N tentativas sem vantagem (Bailey e Lopez
    de Prado): sqrt(V) * ((1-g) z(1-1/N) + g z(1-1/(N e)))."""
    if n_tentativas <= 1 or var_sr <= 0:
        return 0.0
    g = 0.5772156649015329
    return math.sqrt(var_sr) * ((1 - g) * phi_inv(1 - 1.0 / n_tentativas)
                                + g * phi_inv(1 - 1.0 / (n_tentativas * math.e)))


def dsr(xs, n_tentativas, var_sr):
    """Sharpe deflacionado: PSR contra o maximo esperado de N tentativas.
    var_sr: variancia dos Sharpe (por periodo) das tentativas feitas."""
    return psr(xs, sr_max_esperado(n_tentativas, var_sr))


# ---------- PBO por CSCV ----------

def pbo_cscv(matriz, blocos=10):
    """matriz: lista de T linhas (periodos) x N colunas (configuracoes) de
    resultados. Parte T em `blocos` blocos (par), escolhe a melhor configuracao
    em cada metade combinatoria e mede a sua ordem na outra metade.
    Devolve {pbo, n_combinacoes, logits} (pbo = fracao com logit <= 0)."""
    T = len(matriz)
    if T == 0:
        raise ValueError("matriz vazia")
    N = len(matriz[0])
    if N < 2:
        raise ValueError("precisa de pelo menos 2 configuracoes")
    if blocos % 2 or blocos < 2:
        raise ValueError("numero de blocos tem de ser par")
    tam = T // blocos
    if tam < 1:
        raise ValueError("periodos insuficientes para os blocos")
    partes = [matriz[i * tam:(i + 1) * tam] for i in range(blocos)]

    def score(linhas, j):
        xs = [l[j] for l in linhas]
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0
        return mu / sd if sd > 0 else mu * 1e6

    logits = []
    for comb in itertools.combinations(range(blocos), blocos // 2):
        dentro = [l for k in comb for l in partes[k]]
        fora = [l for k in range(blocos) if k not in comb for l in partes[k]]
        sin = [score(dentro, j) for j in range(N)]
        best = max(range(N), key=lambda j: sin[j])
        sout = [score(fora, j) for j in range(N)]
        rank = sum(1 for j in range(N) if sout[j] < sout[best]) + 1   # 1 = pior
        w = rank / (N + 1)
        logits.append(math.log(w / (1 - w)))
    pbo = sum(1 for x in logits if x <= 0) / len(logits)
    return {"pbo": round(pbo, 4), "n_combinacoes": len(logits),
            "logit_mediano": round(sorted(logits)[len(logits) // 2], 4)}


# ---------- acontecimentos (operacoes agrupadas) ----------

def eventos(trs, janela_s=4 * 3600):
    """Agrupa operacoes cuja entrada cai no mesmo intervalo de `janela_s`
    (por omissao a mesma vela de 4H). Devolve lista de listas de R."""
    g = {}
    for t in trs:
        g.setdefault(int(t["t"]) // janela_s, []).append(t["r"])
    return [g[k] for k in sorted(g)]


def resumo_eventos(trs, janela_s=4 * 3600, z=1.645):
    """N de operacoes, N de acontecimentos, efeito de desenho e intervalo de
    90% da media POR ACONTECIMENTO (cada acontecimento pesa o mesmo)."""
    ev = eventos(trs, janela_s)
    n_op = sum(len(e) for e in ev)
    medias = [sum(e) / len(e) for e in ev]
    k = len(medias)
    out = {"n_operacoes": n_op, "n_acontecimentos": k,
           "maior_acontecimento": max((len(e) for e in ev), default=0),
           "media_por_operacao": round(sum(t["r"] for t in trs) / n_op, 4) if n_op else None,
           "media_por_acontecimento": round(sum(medias) / k, 4) if k else None,
           "ic90_por_acontecimento": None}
    if k >= 2:
        mu = sum(medias) / k
        sd = math.sqrt(sum((x - mu) ** 2 for x in medias) / (k - 1))
        out["ic90_por_acontecimento"] = [round(mu - z * sd / math.sqrt(k), 4),
                                         round(mu + z * sd / math.sqrt(k), 4)]
    return out


def n_necessario(sd, efeito, alfa=0.05, poder=0.8):
    """Acontecimentos independentes necessarios para detetar `efeito` (R) com
    desvio-padrao `sd` por acontecimento, teste unilateral."""
    if efeito <= 0 or sd <= 0:
        return None
    return math.ceil(((phi_inv(1 - alfa) + phi_inv(poder)) * sd / efeito) ** 2)


# ---------- teste contra o acaso com acontecimentos agrupados ----------

def _sim(c4, j, geo, fee_pct, slip_pct, max_bars, tf=4 * 3600):
    from engine import trade
    e = c4[j]["o"]
    plan = {"stop": e * (1 + geo["stop"]), "partials": geo["partials"],
            "tp": [e * (1 + x) for x in geo["tp"]],
            "max_hold_s": geo.get("max_hold_s"), "no_react_s": geo.get("no_react_s"),
            "trail_r": geo.get("trail_r")}
    pos = trade.open_position(plan, e, c4[j]["t"], fee_pct, slip_pct,
                              breakeven=geo.get("breakeven", True), side="LONG")
    k = j
    while not pos["closed"] and k < len(c4) and k - j <= max_bars:
        x = c4[k]
        trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + tf)   # o tempo maximo vem no plano
        k += 1
    return pos["r"] if pos["closed"] else None


def acaso_agrupado(trs, bars, rng, reps=300, janela=90, agrupar=True,
                   fee_pct=0.25, slip_pct=0.1, max_bars=6 * 90, janela_s=4 * 3600):
    """Distribuicao do R medio por operacao com entradas ao acaso (mesma moeda,
    mesma geometria `geo`, ate `janela` velas antes ou depois). Com
    agrupar=True as operacoes do mesmo acontecimento usam o MESMO desvio em
    velas em cada repeticao, como no mercado, onde as moedas caem e sobem
    juntas. Com agrupar=False reproduz o metodo atual (cada uma a parte).
    Devolve {mediana, p95, medias}."""
    idx = []
    for t in trs:
        c4 = bars.get(t["asset"]) or []
        ts = [b["t"] for b in c4]
        i = bisect.bisect_left(ts, int(t["t"]))
        if i >= len(ts) or ts[i] != int(t["t"]):
            i = bisect.bisect_right(ts, int(t["t"])) - 1
        idx.append((t, c4, i))
    grupos = {}
    for n, (t, _, _) in enumerate(idx):
        grupos.setdefault(int(t["t"]) // janela_s if agrupar else n, []).append(n)
    cache = {}
    medias = []
    for _ in range(reps):
        rs = []
        for _, membros in grupos.items():
            d = rng.randint(-janela, janela)
            for n in membros:
                t, c4, i = idx[n]
                j = min(max(0, i + d), len(c4) - 2)
                key = (t["asset"], j, id(t["geo"]))
                if key not in cache:
                    cache[key] = _sim(c4, j, t["geo"], fee_pct, slip_pct, max_bars)
                if cache[key] is not None:
                    rs.append(cache[key])
        if rs:
            medias.append(sum(rs) / len(rs))
    medias.sort()
    if not medias:
        return {"mediana": None, "p95": None, "medias": []}
    return {"mediana": medias[len(medias) // 2],
            "p95": medias[int(0.95 * (len(medias) - 1))], "medias": medias}
