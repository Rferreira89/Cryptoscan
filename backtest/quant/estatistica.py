"""Estatistica base do modulo quant (so biblioteca padrao: o CI e o servidor nao tem numpy nem scipy).

Momentos (media, desvio, assimetria, curtose NAO excessiva), normal (statistics.NormalDist), t de Student
(CDF pela beta incompleta regularizada; quantil por bissecao) e algebra linear pequena (Gauss-Jordan)."""
import math
from statistics import NormalDist

N01 = NormalDist()
EULER = 0.5772156649015329


def media(x):
    return sum(x) / len(x)


def desvio(x, ddof=1):
    m = media(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - ddof))


def assimetria(x):
    """Assimetria amostral (momento padronizado de 3a ordem, sem correcao de enviesamento)."""
    m, n = media(x), len(x)
    s = math.sqrt(sum((v - m) ** 2 for v in x) / n)
    return 0.0 if s == 0 else sum((v - m) ** 3 for v in x) / n / s ** 3


def curtose(x):
    """Curtose NAO excessiva (normal = 3), momento padronizado de 4a ordem."""
    m, n = media(x), len(x)
    s2 = sum((v - m) ** 2 for v in x) / n
    return 3.0 if s2 == 0 else sum((v - m) ** 4 for v in x) / n / s2 ** 2


def _betacf(a, b, x, it=300, eps=3e-14):
    """Fracao continuada da beta incompleta (Lentz modificado)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny
        dl = d * c; h *= dl
        if abs(dl - 1) < eps:
            break
    return h


def beta_inc(a, b, x):
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(ln) * _betacf(a, b, x) / a
    return 1 - math.exp(ln) * _betacf(b, a, 1 - x) / b


def t_cdf(t, gl):
    if gl > 1e6:
        return N01.cdf(t)
    x = gl / (gl + t * t)
    p = 0.5 * beta_inc(gl / 2, 0.5, x)
    return 1 - p if t > 0 else p


def t_ppf(q, gl):
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, gl) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------- algebra linear pequena
def transposta(A):
    return [list(r) for r in zip(*A)]


def matmul(A, B):
    Bt = transposta(B)
    return [[sum(a * b for a, b in zip(r, c)) for c in Bt] for r in A]


def inversa(A):
    """Gauss-Jordan com pivot parcial. Falha (ValueError) se a matriz for singular."""
    n = len(A)
    M = [list(map(float, r)) + [1.0 if i == j else 0.0 for j in range(n)] for i, r in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise ValueError("matriz singular (regressores colineares ou sem variacao)")
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [r[n:] for r in M]
