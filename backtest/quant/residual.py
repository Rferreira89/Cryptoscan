"""Vantagem residual face ao BTC: o resultado da estrategia explicado pelo BTC (beta) e o que sobra (alfa).

  y_i = alfa + beta * x_i + e_i
Dois alinhamentos (escolhidos explicitamente; nunca se misturam):
  'por_operacao': y = R da operacao, x = retorno do BTC entre a entrada e a saida dessa mesma operacao (mais exato:
                  compara exatamente a mesma janela de tempo). Ordem pela hora de entrada.
  'diario':       y = soma do R das operacoes fechadas em cada dia UTC (0 nos dias ativos sem fecho),
                  x = retorno do BTC desse dia UTC.
OLS com erros Newey-West (nucleo de Bartlett, lags = floor(4 (n/100)^(2/9)) por defeito, correcao n/(n-k)), intervalos
de confianca pela t de Student com n-k graus de liberdade. Estabilidade: janelas moveis e metades. Regimes: BTC acima
ou abaixo da sua media movel de 'janela_regime' dias (mesma ideia do regime do scanner), regressao separada em cada um.

Timestamps: aceita segundos ou milissegundos (>= 1e12 e tratado como ms). Operacoes sem preco do BTC que cubra a
entrada e a saida ficam de fora e sao contadas em 'excluidas' (nunca se preenche um preco em falta)."""
import bisect
import math
import time

from backtest.quant import estatistica as E

MIN_OBS = 30


def seg(t):
    t = float(t)
    return t / 1000 if t >= 1e12 else t


def dia(t):
    return time.strftime("%Y-%m-%d", time.gmtime(seg(t)))


# ---------------------------------------------------------------- OLS com Newey-West
def lags_nw(n):
    return int(math.floor(4 * (n / 100) ** (2 / 9)))


def ols_hac(y, X, lags=None, nivel=0.95, correcao=True):
    """y: lista; X: lista de linhas JA com a coluna de 1. Devolve coeficientes, erros HAC, t, p, IC e R2."""
    n, k = len(y), len(X[0])
    if n <= k + 1:
        raise ValueError("observacoes insuficientes para a regressao")
    L = lags_nw(n) if lags is None else int(lags)
    Xt = E.transposta(X)
    XtX_inv = E.inversa(E.matmul(Xt, X))
    Xty = [sum(a * b for a, b in zip(col, y)) for col in Xt]
    b = [sum(XtX_inv[i][j] * Xty[j] for j in range(k)) for i in range(k)]
    e = [yi - sum(bj * xj for bj, xj in zip(b, xi)) for yi, xi in zip(y, X)]
    S = [[0.0] * k for _ in range(k)]
    for t in range(n):
        for i in range(k):
            for j in range(k):
                S[i][j] += e[t] * e[t] * X[t][i] * X[t][j]
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        for t in range(l, n):
            ee = e[t] * e[t - l]
            for i in range(k):
                for j in range(k):
                    S[i][j] += w * ee * (X[t][i] * X[t - l][j] + X[t - l][i] * X[t][j])
    V = E.matmul(E.matmul(XtX_inv, S), XtX_inv)
    if correcao:
        V = [[v * n / (n - k) for v in r] for r in V]
    se = [math.sqrt(max(V[i][i], 0.0)) for i in range(k)]
    gl = n - k
    q = E.t_ppf(1 - (1 - nivel) / 2, gl)
    tt = [b[i] / se[i] if se[i] > 0 else float("inf") for i in range(k)]
    p = [2 * (1 - E.t_cdf(abs(x), gl)) if math.isfinite(x) else 0.0 for x in tt]
    my = E.media(y)
    sst = sum((v - my) ** 2 for v in y)
    r2 = 1 - sum(v * v for v in e) / sst if sst > 0 else 0.0
    return {"n": n, "lags": L, "coef": b, "se": se, "t": tt, "p": p, "ic": [(b[i] - q * se[i], b[i] + q * se[i]) for i in range(k)],
            "r2": r2, "residuos": e, "gl": gl}


# ---------------------------------------------------------------- precos do BTC
class SerieBTC:
    """Precos do BTC [(t_segundos, preco)] ordenados. preco_em(t) = ultimo preco conhecido ate t, so se for recente."""
    def __init__(self, pontos, tolerancia_s=2 * 3600):
        p = sorted((seg(t), float(v)) for t, v in pontos if v)
        self.t = [x[0] for x in p]; self.v = [x[1] for x in p]; self.tol = tolerancia_s

    def preco_em(self, t):
        t = seg(t)
        i = bisect.bisect_right(self.t, t) - 1
        if i < 0 or t - self.t[i] > self.tol:
            return None
        return self.v[i]

    def fechos_diarios(self):
        out = {}
        for t, v in zip(self.t, self.v):
            out[dia(t)] = v                       # ultimo preco de cada dia UTC
        return out


def alinhar_por_operacao(ops, btc):
    """ops: [{t_entrada, t_saida, R}]. Devolve (linhas ordenadas, excluidas com motivo)."""
    linhas, excl = [], []
    for o in ops:
        te, ts, r = o.get("t_entrada"), o.get("t_saida"), o.get("R")
        if te is None or ts is None or r is None:
            excl.append((o, "sem entrada, saida ou R")); continue
        if seg(ts) <= seg(te):
            excl.append((o, "saida antes da entrada (timestamps desalinhados)")); continue
        p0, p1 = btc.preco_em(te), btc.preco_em(ts)
        if p0 is None or p1 is None:
            excl.append((o, "sem preco do BTC na entrada ou na saida")); continue
        linhas.append({"t": seg(te), "y": float(r), "x": p1 / p0 - 1, "dia": dia(te)})
    return sorted(linhas, key=lambda l: l["t"]), excl


def alinhar_diario(ops, btc):
    """Soma do R por dia de fecho; 0 nos dias ativos (entre o 1o e o ultimo fecho) sem fecho. x = retorno diario do BTC."""
    fech = btc.fechos_diarios()
    dias_btc = sorted(fech)
    ret = {d: fech[d] / fech[a] - 1 for a, d in zip(dias_btc, dias_btc[1:])
           if (time.mktime(time.strptime(d, "%Y-%m-%d")) - time.mktime(time.strptime(a, "%Y-%m-%d"))) == 86400}
    soma, excl = {}, []
    for o in ops:
        if o.get("t_saida") is None or o.get("R") is None:
            excl.append((o, "sem saida ou R")); continue
        d = dia(o["t_saida"]); soma[d] = soma.get(d, 0.0) + float(o["R"])
    if not soma:
        return [], excl
    ini, fim = min(soma), max(soma)
    linhas = [{"t": time.mktime(time.strptime(d, "%Y-%m-%d")), "y": soma.get(d, 0.0), "x": ret[d], "dia": d}
              for d in sorted(ret) if ini <= d <= fim]
    for d in soma:
        if d not in ret:
            excl.append(({"dia": d}, "dia sem retorno do BTC"))
    return linhas, excl


def regimes(btc, janela=20):
    """{dia: 'subida'|'descida'} — BTC acima/abaixo da media dos ultimos 'janela' fechos diarios. Sem historia: ausente."""
    f = btc.fechos_diarios(); d = sorted(f); out = {}
    for i in range(janela, len(d)):
        mm = sum(f[x] for x in d[i - janela:i]) / janela
        out[d[i]] = "subida" if f[d[i]] > mm else "descida"
    return out


def _reg(linhas, lags=None):
    r = ols_hac([l["y"] for l in linhas], [[1.0, l["x"]] for l in linhas], lags=lags)
    a, b = r["coef"]
    return {"n": r["n"], "lags": r["lags"], "alfa": a, "beta": b, "se_alfa": r["se"][0], "se_beta": r["se"][1],
            "t_alfa": r["t"][0], "p_alfa": r["p"][0], "t_beta": r["t"][1], "p_beta": r["p"][1],
            "ic_alfa": r["ic"][0], "ic_beta": r["ic"][1], "r2": r["r2"], "residuos": r["residuos"]}


def analisar(ops, btc, modo="por_operacao", min_obs=MIN_OBS, janela_movel=None, janela_regime=20, lags=None):
    linhas, excl = (alinhar_por_operacao if modo == "por_operacao" else alinhar_diario)(ops, btc)
    out = {"modo": modo, "n": len(linhas), "excluidas": len(excl), "motivos_exclusao": sorted({m for _, m in excl}), "min_obs": min_obs}
    if len(linhas) < min_obs:
        return {**out, "estado": "insuficiente", "razao": f"{len(linhas)} observacoes alinhadas (minimo {min_obs})"}
    if E.desvio([l["x"] for l in linhas]) == 0:
        return {**out, "estado": "insuficiente", "razao": "o BTC nao variou nas janelas alinhadas"}
    g = _reg(linhas, lags)
    res = g.pop("residuos")
    alfa_puro = [l["y"] - g["beta"] * l["x"] for l in linhas]        # retorno residual = alfa + erro
    out.update(estado="calculado", **g, retorno_total=sum(l["y"] for l in linhas), parte_btc=g["beta"] * sum(l["x"] for l in linhas),
               retorno_residual=sum(alfa_puro), media_residual=E.media(alfa_puro))
    # estabilidade: metades e janelas moveis
    h = len(linhas) // 2
    out["metades"] = [{k: v for k, v in _reg(p, lags).items() if k in ("n", "alfa", "beta", "p_alfa")} if len(p) >= max(10, min_obs // 2) else {"n": len(p), "estado": "insuficiente"}
                      for p in (linhas[:h], linhas[h:])]
    w = janela_movel or max(min_obs, len(linhas) // 3)
    passo = max(1, w // 2)
    out["movel"] = [{"desde": linhas[i]["dia"], "ate": linhas[i + w - 1]["dia"], **{k: v for k, v in _reg(linhas[i:i + w], lags).items() if k in ("alfa", "beta", "p_alfa")}}
                    for i in range(0, len(linhas) - w + 1, passo)] if len(linhas) >= w + 1 else []
    reg = regimes(btc, janela_regime)
    out["regimes"] = {}
    for nome in ("subida", "descida"):
        p = [l for l in linhas if reg.get(l["dia"]) == nome]
        out["regimes"][nome] = ({"estado": "calculado", **{k: v for k, v in _reg(p, lags).items() if k != "residuos"}}
                                if len(p) >= max(10, min_obs // 2) else {"estado": "insuficiente", "n": len(p)})
    out["regimes"]["sem_regime"] = sum(1 for l in linhas if l["dia"] not in reg)
    out["veredito"] = ("vantagem residual positiva e significativa" if g["p_alfa"] < 0.05 and g["alfa"] > 0 else
                       "resultado residual negativo e significativo" if g["p_alfa"] < 0.05 else
                       "sem evidencia de vantagem propria alem do BTC")
    return out
