"""Familias de sinais do Hunter (vetorizadas em numpy, sem olhar para a frente).

Cada familia: f(S, M, p) -> (indices LONG, indices SHORT), onde S sao as series de UMA moeda num timeframe
(arrays o,h,l,c,v,atr,t) e M o contexto de mercado alinhado por tempo (retorno do BTC, mediana das moedas,
funding da moeda). Na vela i so se usa informacao ate ao fecho de i (janelas sobre valores ANTERIORES: prev_max,
prev_min, medias deslocadas). Sinais de varias familias sao independentes entre si (cada uma avaliada sozinha).

Dados que NAO existem nas velas publicas e por isso nao entram (limite declarado): CVD e desequilibrio
comprador/vendedor por operacao (sem trades historicos), open interest historico por X-Perp (a OKX publica
agregados por moeda com pouco historico), liquidacoes historicas por X-Perp.
"""
import numpy as np


def _prev_ext(x, n, fn):
    """fn(x[i-n:i]) para cada i (NaN onde nao ha n valores anteriores)."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, n)          # w[k] = x[k:k+n]
    out[n:] = fn(w[:-1], axis=1)
    return out


def prev_max(x, n):
    return _prev_ext(x, n, np.max)


def prev_min(x, n):
    return _prev_ext(x, n, np.min)


def prev_mean(x, n):
    return _prev_ext(x, n, np.mean)


def prev_std(x, n):
    return _prev_ext(x, n, np.std)


def sh(x, k=1):
    """x deslocado k velas para a frente no tempo (valor de i-k em i); NaN no inicio. Nunca usa np.roll (que da a
    volta e poria o fim da serie - o futuro - no inicio)."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def ret(c, k):
    out = np.full(len(c), np.nan)
    out[k:] = c[k:] / c[:-k] - 1
    return out


def idx(m):
    return np.nonzero(np.nan_to_num(m, nan=0).astype(bool))[0]


# ------------------------------------------------- A. liquidez ---------------------------------------------------
def varrimento(S, M, p):
    """Liquidity sweep / stop hunt: o minimo fura o minimo de N velas e o fecho volta para dentro."""
    n = p["n"]
    lo, hi = prev_min(S["l"], n), prev_max(S["h"], n)
    L = (S["l"] < lo) & (S["c"] > lo)
    Sh = (S["h"] > hi) & (S["c"] < hi)
    return idx(L), idx(Sh)


def falso_rompimento(S, M, p):
    """A vela anterior fechou acima do maximo de N; esta fecha de volta abaixo desse nivel (e o espelho)."""
    n = p["n"]
    hi, lo = prev_max(S["h"], n), prev_min(S["l"], n)
    hi1, lo1 = sh(hi, 1), sh(lo, 1)
    c1 = sh(S["c"], 1)
    Sh = (c1 > hi1) & (S["c"] < hi1)
    L = (c1 < lo1) & (S["c"] > lo1)
    Sh[:n + 2] = False
    L[:n + 2] = False
    return idx(L), idx(Sh)


def rejeicao(S, M, p):
    """Pavio >= w da amplitude no extremo de N velas (rejeicao de zona de liquidez)."""
    n, w = p["n"], p["w"]
    rg = S["h"] - S["l"]
    inf = np.minimum(S["o"], S["c"]) - S["l"]
    sup = S["h"] - np.maximum(S["o"], S["c"])
    L = (S["l"] <= prev_min(S["l"], n)) & (inf >= w * rg) & (rg > 0)
    Sh = (S["h"] >= prev_max(S["h"], n)) & (sup >= w * rg) & (rg > 0)
    return idx(L), idx(Sh)


def recuperacao(S, M, p):
    """Depois de uma vela de queda >= k ATR (cascata), a vela seguinte fecha acima do meio dessa vela."""
    k = p["k"]
    atr1 = sh(S["atr"], 1)
    grande_queda = sh(S["o"] - S["c"], 1) >= k * atr1
    grande_subida = sh(S["c"] - S["o"], 1) >= k * atr1
    meio = sh((S["h"] + S["l"]) / 2, 1)
    L = grande_queda & (S["c"] > meio)
    Sh = grande_subida & (S["c"] < meio)
    L[:2] = Sh[:2] = False
    return idx(L), idx(Sh)


# ------------------------------------------------- B. derivados --------------------------------------------------
def funding_extremo(S, M, p):
    """Funding da moeda (ultimo conhecido ate ao fecho) acima/abaixo do percentil z das ultimas 90 leituras:
    posicionamento esticado -> contra o lado que paga."""
    f = M.get("funding")
    if f is None:
        return idx(np.zeros(len(S["c"]))), idx(np.zeros(len(S["c"])))
    mu, sd = prev_mean(f, 90), prev_std(f, 90)
    z = (f - mu) / np.where(sd > 0, sd, np.nan)
    return idx(z <= -p["z"]), idx(z >= p["z"])


# --------------------------------------------- C. price action / volatilidade ------------------------------------
def compressao(S, M, p):
    a14 = S["atr"]
    a100 = prev_mean(a14, 100)
    comp = sh(a14 / a100, 1) < p["c"]
    hi, lo = prev_max(S["h"], 10), prev_min(S["l"], 10)
    return idx(comp & (S["c"] > hi)), idx(comp & (S["c"] < lo))


def extremo(S, M, p):
    """Reversao depois de um movimento de k velas acima de z desvios-padrao dos retornos de k velas."""
    k, z = p["k"], p["z"]
    r = ret(S["c"], k)
    sd = prev_std(r, 200)
    return idx(r <= -z * sd), idx(r >= z * sd)


def impulso_correcao(S, M, p):
    """Impulso (retorno de 6 velas >= x) seguido de correcao de 38-62% do impulso: continua no sentido do impulso."""
    x = p["x"]
    r6 = sh(ret(S["c"], 6), 3)
    topo = prev_max(S["h"], 9)
    base = prev_min(S["l"], 9)
    amp = topo - base
    corr_l = (topo - S["c"]) / np.where(amp > 0, amp, np.nan)
    corr_s = (S["c"] - base) / np.where(amp > 0, amp, np.nan)
    L = (r6 >= x) & (corr_l >= 0.38) & (corr_l <= 0.62) & (S["c"] > S["o"])
    Sh = (r6 <= -x) & (corr_s >= 0.38) & (corr_s <= 0.62) & (S["c"] < S["o"])
    return idx(L), idx(Sh)


def rompimento_reteste(S, M, p):
    """Rompeu o maximo de N nas ultimas 3 velas, voltou ao nivel (minimo toca o nivel +-0,3 ATR) e fecha acima."""
    n = p["n"]
    hi, lo = prev_max(S["h"], n), prev_min(S["l"], n)
    nivel_h = sh(hi, 3)
    nivel_l = sh(lo, 3)
    rompeu_h = np.maximum.reduce([sh(S["c"], k) for k in (1, 2, 3)]) > nivel_h
    rompeu_l = np.minimum.reduce([sh(S["c"], k) for k in (1, 2, 3)]) < nivel_l
    tol = 0.3 * S["atr"]
    L = rompeu_h & (np.abs(S["l"] - nivel_h) <= tol) & (S["c"] > nivel_h)
    Sh = rompeu_l & (np.abs(S["h"] - nivel_l) <= tol) & (S["c"] < nivel_l)
    L[:n + 4] = Sh[:n + 4] = False
    return idx(L), idx(Sh)


def estrutura(S, M, p):
    """Mudanca de estrutura: depois de N velas em queda (fecho < media de N), fecha acima do maximo de 5 velas
    com o fecho anterior abaixo dele (e o espelho)."""
    n = p["n"]
    sma = prev_mean(S["c"], n)
    tend_baixa = sh((S["c"] < sma).astype(float), 1) > 0.5
    tend_alta = sh((S["c"] > sma).astype(float), 1) > 0.5
    hi5, lo5 = prev_max(S["h"], 5), prev_min(S["l"], 5)
    L = tend_baixa & (S["c"] > hi5)
    Sh = tend_alta & (S["c"] < lo5)
    return idx(L), idx(Sh)


# ------------------------------------------------- D. fluxo / volume ---------------------------------------------
def volume_anormal(S, M, p):
    """Volume >= m x mediana de 48 com vela no sentido e fecho no terco extremo (continuacao)."""
    m = p["m"]
    med = _prev_ext(S["v"], 48, np.median)
    rg = S["h"] - S["l"]
    pos = (S["c"] - S["l"]) / np.where(rg > 0, rg, np.nan)
    L = (S["v"] >= m * med) & (S["c"] > S["o"]) & (pos >= 2 / 3)
    Sh = (S["v"] >= m * med) & (S["c"] < S["o"]) & (pos <= 1 / 3)
    return idx(L), idx(Sh)


def divergencia_volume(S, M, p):
    """Novo maximo de N com volume abaixo de metade da media de N (subida sem participacao) -> SHORT; espelho."""
    n = p["n"]
    vm = prev_mean(S["v"], n)
    Sh = (S["h"] > prev_max(S["h"], n)) & (S["v"] < 0.5 * vm)
    L = (S["l"] < prev_min(S["l"], n)) & (S["v"] < 0.5 * vm)
    return idx(L), idx(Sh)


def acumulacao(S, M, p):
    """OBV a subir em N velas com preco lateral (retorno de N entre -1% e 1%): acumulacao -> LONG; espelho."""
    n = p["n"]
    obv = np.cumsum(np.sign(np.diff(S["c"], prepend=S["c"][0])) * S["v"])
    vm = prev_mean(S["v"], n)
    d = (obv - sh(obv, n)) / np.where(vm > 0, vm * n, np.nan)
    r = ret(S["c"], n)
    lat = np.abs(r) <= 0.01
    return idx(lat & (d >= 0.3)), idx(lat & (d <= -0.3))


# ------------------------------------------------- E. quantitativas ----------------------------------------------
def vwap_desvio(S, M, p):
    """Desvio do fecho ao VWAP de N velas em desvios-padrao: <= -z -> LONG (reversao); >= z -> SHORT."""
    n, z = p["n"], p["z"]
    tp = (S["h"] + S["l"] + S["c"]) / 3
    pv = prev_mean(tp * S["v"], n) / np.where(prev_mean(S["v"], n) > 0, prev_mean(S["v"], n), np.nan)
    sd = prev_std(S["c"], n)
    zz = (S["c"] - pv) / np.where(sd > 0, sd, np.nan)
    return idx(zz <= -z), idx(zz >= z)


def momentum_regime(S, M, p):
    """Retorno de k velas >= x no sentido do BTC (BTC acima/abaixo da sua media de 50 velas)."""
    k, x = p["k"], p["x"]
    r = ret(S["c"], k)
    up = M.get("btc_acima")
    if up is None:
        return idx(r >= x), idx(r <= -x)
    return idx((r >= x) & (up > 0.5)), idx((r <= -x) & (up < 0.5))


def forca_relativa(S, M, p):
    """Retorno de k velas da moeda menos o do BTC >= x (forte) -> LONG; <= -x (fraca) -> SHORT."""
    k, x = p["k"], p["x"]
    b = M.get("btc_ret_%d" % k)
    if b is None:
        return idx(np.zeros(len(S["c"]))), idx(np.zeros(len(S["c"])))
    rr = ret(S["c"], k) - b
    return idx(rr >= x), idx(rr <= -x)


# ------------------------------------------------- F. multiactivo ------------------------------------------------
def lideranca_btc(S, M, p):
    """O BTC moveu-se >= x na ultima vela e a moeda ainda nao (|retorno| < metade): entra no sentido do BTC."""
    x = p["x"]
    b = M.get("btc_ret_1")
    if b is None:
        return idx(np.zeros(len(S["c"]))), idx(np.zeros(len(S["c"])))
    r = ret(S["c"], 1)
    return idx((b >= x) & (r < 0.5 * b)), idx((b <= -x) & (r > 0.5 * b))


def forte_na_queda(S, M, p):
    """Mediana das moedas cai >= x em k velas e esta moeda sobe: forca relativa em queda -> LONG; espelho."""
    k, x = p["k"], p["x"]
    m = M.get("mercado_ret_%d" % k)
    if m is None:
        return idx(np.zeros(len(S["c"]))), idx(np.zeros(len(S["c"])))
    r = ret(S["c"], k)
    return idx((m <= -x) & (r > 0)), idx((m >= x) & (r < 0))


# ------------------------------------------------- G. shorts para o piloto (21/11) ------------------------------
def _ema(x, n):
    """Media exponencial causal (o valor em i so usa x[..i])."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    a, m = 2.0 / (n + 1), np.nan
    for i, v in enumerate(x):
        if v != v:
            out[i] = m
            continue
        m = v if m != m else a * v + (1 - a) * m
        out[i] = m
    return out


def venda_repique(S, M, p):
    """(21/11, investigacao de shorts pedida pelo Rui) Vender o repique num mercado em queda: fecho abaixo da media de
    p["tendencia"] velas (tendencia de baixa), o preco subiu mais de x nas ultimas k velas (repique) e a vela tocou
    na media de p["ema"] velas mas fechou abaixo dela (rejeicao) -> SHORT. Sem lado LONG.
    Backtest 4H 2021-2026, 252 moedas (vivas e deslistadas), custos OKX: ver
    backtest/estudos/shorts_piloto_2026-11-21.json (ramo main)."""
    c, h = S["c"], S["h"]
    e = _ema(c, p["ema"])
    t = _ema(c, p["tendencia"])
    r = ret(c, p["k"])
    sinal = (c < t) & (h >= e) & (c < e) & (r > p["x"])
    sinal[: p["tendencia"]] = False                       # media longa ainda sem historico suficiente
    return idx(np.zeros(len(c))), idx(sinal)


FAMILIAS = {
    # grupo A - liquidez
    "varrimento": (varrimento, [{"n": n} for n in (12, 24, 48)]),
    "falso_rompimento": (falso_rompimento, [{"n": n} for n in (12, 24, 48)]),
    "rejeicao": (rejeicao, [{"n": n, "w": w} for n in (24, 48) for w in (0.5, 0.65)]),
    "recuperacao": (recuperacao, [{"k": k} for k in (2.5, 3.5)]),
    # grupo B - derivados
    "funding_extremo": (funding_extremo, [{"z": z} for z in (1.5, 2.0)]),
    # grupo C - price action / volatilidade
    "compressao": (compressao, [{"c": c} for c in (0.5, 0.7)]),
    "extremo": (extremo, [{"k": k, "z": z} for k in (1, 4) for z in (3.0, 4.0)]),
    "impulso_correcao": (impulso_correcao, [{"x": x} for x in (0.03, 0.06)]),
    "rompimento_reteste": (rompimento_reteste, [{"n": n} for n in (24, 48)]),
    "estrutura": (estrutura, [{"n": n} for n in (24, 48)]),
    # grupo D - fluxo / volume
    "volume_anormal": (volume_anormal, [{"m": m} for m in (3.0, 5.0)]),
    "divergencia_volume": (divergencia_volume, [{"n": n} for n in (24, 48)]),
    "acumulacao": (acumulacao, [{"n": n} for n in (24, 48)]),
    # grupo E - quantitativas
    "vwap_desvio": (vwap_desvio, [{"n": n, "z": z} for n in (24, 48) for z in (2.0, 3.0)]),
    "momentum_regime": (momentum_regime, [{"k": k, "x": x} for k in (3, 12) for x in (0.02, 0.05)]),
    "forca_relativa": (forca_relativa, [{"k": k, "x": x} for k in (6, 24) for x in (0.03, 0.08)]),
    # grupo F - multiactivo
    "lideranca_btc": (lideranca_btc, [{"x": x} for x in (0.01, 0.02)]),
    "forte_na_queda": (forte_na_queda, [{"k": k, "x": x} for k in (6, 24) for x in (0.02, 0.05)]),
    # grupo G - shorts para o piloto (21/11)
    "venda_repique": (venda_repique, [{"ema": 50, "k": 6, "x": 0.03, "tendencia": 300}]),
}
GRUPO = {"varrimento": "A", "falso_rompimento": "A", "rejeicao": "A", "recuperacao": "A", "funding_extremo": "B",
         "compressao": "C", "extremo": "C", "impulso_correcao": "C", "rompimento_reteste": "C", "estrutura": "C",
         "volume_anormal": "D", "divergencia_volume": "D", "acumulacao": "D", "vwap_desvio": "E",
         "momentum_regime": "E", "forca_relativa": "E", "lideranca_btc": "F", "forte_na_queda": "F",
         "venda_repique": "G"}


# (17/11) hipotese economica de cada familia (registo: condicoes, regime esperado, custos e riscos especificos).
HIPOTESES = {
    "varrimento": ("stops acumulados abaixo/acima de minimos/maximos sao varridos e o preco regressa (liquidez "
                   "absorvida)", "lateral", "baixo (entrada no fecho)", "rutura verdadeira continua o movimento"),
    "falso_rompimento": ("rompimento sem seguimento prende compradores tardios que saem e empurram o preco de volta",
                         "lateral", "baixo", "tendencia forte transforma falsos em verdadeiros"),
    "rejeicao": ("pavio longo no extremo = oferta/procura agressiva rejeitou o nivel", "lateral", "baixo",
                 "pavio de pouca liquidez (contratos C) nao significa nada"),
    "recuperacao": ("depois de uma cascata de liquidacoes o preco recupera metade da vela (vendedores forcados acabaram)",
                    "queda", "medio (volatilidade alta)", "cascatas em serie"),
    "funding_extremo": ("posicionamento esticado (quem paga funding) desfaz-se contra o lado que paga",
                        "qualquer", "funding entra no resultado", "historico de funding curto (3 meses)"),
    "compressao": ("volatilidade comprimida antecede expansao; o lado do rompimento indica a direcao",
                   "lateral -> tendencia", "baixo", "falsos rompimentos depois da compressao"),
    "extremo": ("movimentos de varios desvios-padrao sao em parte excesso (reversao)", "qualquer",
                "alto em 30m", "tendencias fortes continuam"),
    "impulso_correcao": ("depois de um impulso, a correcao de 38-62% e reentrada de quem perdeu o movimento",
                         "tendencia", "medio", "correcao vira inversao"),
    "rompimento_reteste": ("o nivel rompido passa de resistencia a suporte; o reteste confirma", "subida",
                           "baixo com stop de 4H", "reteste falha e volta para dentro do intervalo"),
    "estrutura": ("primeiro maximo mais alto depois de uma queda = mudanca de controlo", "inversao", "medio",
                  "sinal precoce numa queda que continua"),
    "volume_anormal": ("volume anormal no sentido da vela = informacao nova a entrar", "qualquer", "medio",
                       "picos de volume em contratos iliquidos"),
    "divergencia_volume": ("extremo sem participacao (volume baixo) e fragil", "qualquer", "baixo",
                           "volume das X-Perps nao representa o mercado todo"),
    "acumulacao": ("OBV a subir com preco lateral = acumulacao antes do movimento", "lateral", "baixo",
                   "OBV com volume de uma so bolsa"),
    "vwap_desvio": ("desvios grandes ao VWAP revertem (custo de inventario dos market makers)", "lateral", "baixo",
                    "tendencias afastam-se do VWAP de proposito"),
    "momentum_regime": ("momentum funciona a favor do regime do BTC (fluxo do mercado inteiro)", "subida/queda",
                        "medio", "inversoes do BTC"),
    "forca_relativa": ("forca relativa persiste a curto prazo (rotacao lenta de capital)", "qualquer", "medio",
                       "reversao da forca relativa"),
    "lideranca_btc": ("as altcoins seguem o BTC com atraso (descoberta de preco centrada no BTC)", "movimentos do BTC",
                      "medio", "um so acontecimento do BTC vira dezenas de operacoes correlacionadas"),
    "forte_na_queda": ("o que sobe com o mercado a cair tem procura propria", "queda", "medio",
                       "noticias especificas de uma moeda"),
    "venda_repique": ("num mercado em queda os repiques ate a media sao vendidos por quem ficou preso mais acima",
                      "queda", "medio (stop largo de 3 ATR de 4H)", "o repique vira inversao de tendencia"),
}
