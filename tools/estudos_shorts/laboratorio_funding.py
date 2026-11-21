"""Shorts por FUNDING (posicionamento esticado dos longs) em velas de 4H, so para as moedas com funding (09/2024-11/2026).
Periodos proprios (amostra mais curta): TREINO 2024-09..2025-06, VALIDACAO 2025-07..2025-12, TESTE 2026."""
import gzip
import json
import os
import sys
import numpy as np
from tools.estudos_shorts import laboratorio as L

T_VAL = 1751328000     # 2025-07-01
T_TEST = 1767225600    # 2026-01-01


def funding(b):
    p = os.path.join(L.H, "history", "funding", b + ".csv.gz")
    if not os.path.exists(p):
        return None
    a = np.loadtxt(gzip.open(p), delimiter=",")
    return a[:, 0], a[:, 1]


def f_funding(S, p, F):
    """Media do funding das ultimas m leituras (8h) >= f, preco subiu x em k velas e fecho abaixo do maximo da vela
    (sinal de cansaco: fecho no terco inferior ou vela vermelha)."""
    ft, fv = F
    t, c, o, h, l = S["t"], S["c"], S["o"], S["h"], S["l"]
    # funding conhecido ate ao FECHO da vela i (t[i] + 4h): ultimo indice com ft <= t+4h
    pos = np.searchsorted(ft, t + 4 * 3600, side="right") - 1
    m = p["m"]
    cs = np.cumsum(np.r_[0, fv])
    med = np.where(pos >= m - 1, (cs[np.clip(pos + 1, 0, None)] - cs[np.clip(pos + 1 - m, 0, None)]) / m, np.nan)
    k = p["k"]
    r = np.full_like(c, np.nan)
    r[k:] = c[k:] / c[:-k] - 1
    cans = (c < o) if p["vela"] == "vermelha" else ((c - l) / np.maximum(h - l, 1e-12) <= 0.4)
    return np.where((med >= p["f"]) & (r >= p["x"]) & cans)[0]


GRID = [dict(m=m, f=f, k=k, x=x, vela=v) for m in (1, 3) for f in (0.0002, 0.0004, 0.0008) for k in (6, 18)
        for x in (0.05, 0.10) for v in ("vermelha", "terco")]


def main(saida):
    D = L.carregar()
    FF = {b: funding(b) for b in D}
    FF = {b: v for b, v in FF.items() if v is not None}
    TUR = {b: L.turtle_sinais(D[b]) for b in FF}
    print("moedas com funding", len(FF), flush=True)
    res = []
    for p in GRID:
        sig = {b: L.np.array([i for i in f_funding(D[b], p, FF[b])], dtype=int) for b in FF}
        nsig = sum(len(v) for v in sig.values())
        sobre = sum(1 for b, v in sig.items() for i in v if any(j in TUR[b] for j in range(i - 6, i + 1)))
        for sd in L.SAIDAS:
            ops = []
            for b in FF:
                ops += L.simular(D[b], b, sig[b], sd)
            ops = [x for x in ops if x[0] >= 1725148800]
            res.append({"fam": "funding", "p": p, "saida": sd, "sinais": nsig, "sobreposicao_turtle": round(sobre / max(1, nsig), 3),
                        "treino": L.resumo([x for x in ops if x[0] < T_VAL]),
                        "validacao": L.resumo([x for x in ops if T_VAL <= x[0] < T_TEST]),
                        "teste": L.resumo([x for x in ops if x[0] >= T_TEST])})
        print(p, flush=True)
    with open(saida, "w") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main(sys.argv[1])
