"""Technical Analysis Engine: indicadores calculados so com velas fechadas.

Todas as funcoes devolvem listas alinhadas com a entrada; None durante o
periodo de aquecimento. O valor no indice i usa apenas dados ate i.
"""


def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    out = [None] * len(x)
    if len(x) < n:
        return out
    k = 2 / (n + 1)
    e = sum(x[:n]) / n
    out[n - 1] = e
    for i in range(n, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def _wilder(vals, n):
    """Media de Wilder sobre vals (sem None). Devolve lista alinhada."""
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    a = sum(vals[:n]) / n
    out[n - 1] = a
    for i in range(n, len(vals)):
        a = (a * (n - 1) + vals[i]) / n
        out[i] = a
    return out


def rsi(close, n=14):
    out = [None] * len(close)
    if len(close) <= n:
        return out
    gains = [max(close[i] - close[i - 1], 0.0) for i in range(1, len(close))]
    losses = [max(close[i - 1] - close[i], 0.0) for i in range(1, len(close))]
    ag, al = _wilder(gains, n), _wilder(losses, n)
    for i in range(n - 1, len(gains)):
        g, l = ag[i], al[i]
        out[i + 1] = 100.0 if l == 0 and g > 0 else 50.0 if l == 0 \
            else 100 - 100 / (1 + g / l)
    return out


def true_range(c):
    tr = [c[0]["h"] - c[0]["l"]]
    for i in range(1, len(c)):
        pc = c[i - 1]["c"]
        tr.append(max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - pc),
                      abs(c[i]["l"] - pc)))
    return tr


def atr(c, n=14):
    return _wilder(true_range(c), n)


def adx(c, n=14):
    out = [None] * len(c)
    if len(c) < 2 * n + 1:
        return out
    pdm, ndm = [], []
    for i in range(1, len(c)):
        up, dn = c[i]["h"] - c[i - 1]["h"], c[i - 1]["l"] - c[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0.0)
        ndm.append(dn if dn > up and dn > 0 else 0.0)
    tr = true_range(c)[1:]
    str_, sp, sn = _wilder(tr, n), _wilder(pdm, n), _wilder(ndm, n)
    dx = []
    for i in range(n - 1, len(tr)):
        if str_[i] == 0:
            dx.append(0.0)
            continue
        pdi, ndi = 100 * sp[i] / str_[i], 100 * sn[i] / str_[i]
        dx.append(0.0 if pdi + ndi == 0
                  else 100 * abs(pdi - ndi) / (pdi + ndi))
    a = _wilder(dx, n)
    for j, v in enumerate(a):
        if v is not None:
            out[j + n] = v          # dx[j] corresponde a vela j + n
    return out
