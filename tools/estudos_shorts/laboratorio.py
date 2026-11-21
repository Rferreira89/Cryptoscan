"""Laboratorio de SHORTS para o piloto OKX (21/11, ordem do Rui): mecanismos DIFERENTES da SHORT_TURTLE.
So backtest (velas de 4H 2021-2026, moedas vivas e deslistadas). Sem look-ahead: sinal na vela fechada, entrada na
abertura seguinte. Stop/objetivo/tempo; mesma vela com stop e objetivo conta o stop; salto de abertura acima do stop
sai na abertura. Custos OKX: comissao 0,05%/lado + deslize 0,05% (majors) ou 0,10% (resto) por lado + 0,05% extra no
stop. Periodos: TREINO 2021-2023, VALIDACAO 2024, TESTE 2025-01..2026-11 (so olhado no fim)."""
import gzip
import json
import os
import sys
import itertools
import numpy as np

H = os.environ.get("HIST", "/tmp/hist")   # pasta com os ramos history e history-delistadas clonados
T_VAL = 1704067200      # 2024-01-01
T_TEST = 1735689600     # 2025-01-01
MAJ = {"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "LINK", "AVAX", "LTC", "DOT", "TRX", "BCH"}
FEE = 0.0005
EXCL = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "PAXG", "BUSD", "AEUR", "USDE", "WBTC", "WBETH", "XUSD"}


def load(path):
    a = np.loadtxt(gzip.open(path), delimiter=",")
    if a.ndim != 2 or len(a) < 400:
        return None
    return a


def ema(x, n):
    a = 2 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return ema(tr, 2 * n - 1)  # Wilder approx


def rolling_max(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def rolling_min(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def rolling_mean(x, n):
    c = np.cumsum(np.r_[0, x])
    out = np.full_like(x, np.nan, dtype=float)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def carregar():
    D = {}
    for pasta in ("history", "history-delistadas"):
        for f in sorted(os.listdir(os.path.join(H, pasta))):
            if not f.endswith(".csv.gz"):
                continue
            b = f[:-7]
            if b in EXCL or b in D:
                continue
            a = load(os.path.join(H, pasta, f))
            if a is None:
                continue
            t, o, h, l, c, v = a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
            tb = a[:, 6] if a.shape[1] > 6 else np.full_like(v, np.nan)
            q = v * c                                              # volume em USD aproximado
            S = dict(t=t, o=o, h=h, l=l, c=c, v=v, tb=tb, q=q)
            S["atr"] = atr(h, l, c)
            S["e20"] = ema(c, 20)
            S["e50"] = ema(c, 50)
            S["e300"] = ema(c, 300)                                # ~50 dias
            S["qd"] = rolling_mean(q, 6 * 30) * 6                  # volume diario medio de 30 dias
            S["vm"] = rolling_mean(v, 20)
            D[b] = S
    return D


def btc_ctx(D):
    B = D["BTC"]
    idx = {int(t): i for i, t in enumerate(B["t"])}
    return B, idx


# ------------------------------------------------------------------ familias (indices de sinal SHORT) -----------
def f_pump_fade(S, p, ctx):
    k, x, m = p["k"], p["x"], p["m"]
    c = S["c"]
    r = np.full_like(c, np.nan)
    r[k:] = c[k:] / c[:-k] - 1
    return np.where((r >= x) & (c >= S["e20"] + m * S["atr"]))[0]


def f_bull_trap(S, p, ctx):
    n, w = p["n"], p["w"]
    h, l, c, o = S["h"], S["l"], S["c"], S["o"]
    ph = np.r_[np.nan, rolling_max(h, n)[:-1]]                     # maximo das n velas anteriores
    rng = np.maximum(h - l, 1e-12)
    wick = (h - np.maximum(o, c)) / rng
    return np.where((h > ph) & (c < ph) & (wick >= w))[0]


def f_sell_rally(S, p, ctx):
    e = S["e20"] if p["ema"] == 20 else S["e50"]
    c, h = S["c"], S["h"]
    k = p["k"]
    r = np.full_like(c, np.nan)
    r[k:] = c[k:] / c[:-k] - 1
    down = c < S["e300"]
    return np.where(down & (h >= e) & (c < e) & (r > p["x"]))[0]


def f_rel_weak(S, p, ctx):
    B, bidx = ctx
    c = S["c"]
    k = p["k"]
    bi = np.array([bidx.get(int(t), -1) for t in S["t"]])
    ok = bi >= k
    bc = np.where(ok, B["c"][np.clip(bi, 0, None)], np.nan)
    bk = np.where(ok, B["c"][np.clip(bi - k, 0, None)], np.nan)
    r = np.full_like(c, np.nan)
    r[k:] = c[k:] / c[:-k] - 1
    rel = r - (bc / bk - 1)
    return np.where((rel <= -p["x"]) & (c < S["e50"]) & (np.r_[np.nan, rel[:-1]] > -p["x"]))[0]


def f_blowoff(S, p, ctx):
    tb, v, h, l, c, o = S["tb"], S["v"], S["h"], S["l"], S["c"], S["o"]
    ratio = tb / np.maximum(v, 1e-12)
    rng = h - l
    pos = (c - l) / np.maximum(rng, 1e-12)
    return np.where((ratio >= p["q"]) & (rng >= p["r"] * S["atr"]) & (pos <= 0.5) & (v >= 2 * S["vm"]))[0]


def f_vol_div_high(S, p, ctx):
    n = p["n"]
    c, v = S["c"], S["v"]
    ph = np.r_[np.nan, rolling_max(c, n)[:-1]]
    return np.where((c > ph) & (v < p["f"] * S["vm"]))[0]


FAM = {
    "pump_fade": (f_pump_fade, [dict(k=k, x=x, m=m) for k in (3, 6, 12) for x in (0.10, 0.15, 0.25) for m in (2, 3)]),
    "bull_trap": (f_bull_trap, [dict(n=n, w=w) for n in (20, 60, 120) for w in (0.4, 0.6)]),
    "sell_rally": (f_sell_rally, [dict(ema=e, k=k, x=x) for e in (20, 50) for k in (3, 6) for x in (0.0, 0.03)]),
    "rel_weak": (f_rel_weak, [dict(k=k, x=x) for k in (18, 42) for x in (0.10, 0.20)]),
    "blowoff": (f_blowoff, [dict(q=q, r=r) for q in (0.55, 0.60) for r in (2.0, 3.0)]),
    "vol_div_high": (f_vol_div_high, [dict(n=n, f=f) for n in (20, 60) for f in (0.5, 0.7)]),
}
SAIDAS = [dict(k=k, tp=tp, hold=hd) for k in (1.5, 2.0, 3.0) for tp in (1.0, 1.5, 2.5) for hd in (6, 18, 30)]


def simular(S, b, sinais, sd, liq_min=5e6):
    """Devolve [(t_entrada, r_liquido, b)]; um sinal so se nao houver posicao aberta nesta moeda."""
    o, h, l, c, t, A = S["o"], S["h"], S["l"], S["c"], S["t"], S["atr"]
    desl = 0.0005 if b in MAJ else 0.001
    out, livre = [], -1
    n = len(c)
    for i in sinais:
        if i <= livre or i + 1 >= n or not (A[i] > 0) or not (S["qd"][i] >= liq_min):
            continue
        e = o[i + 1] * (1 - desl)                                  # vende abaixo (deslize)
        R = sd["k"] * A[i]
        stop, alvo = e + R, e - sd["tp"] * R
        fim = min(n - 1, i + sd["hold"])
        sai, j = None, i + 1
        for j in range(i + 1, fim + 1):
            if j > i + 1 and o[j] >= stop:                         # salto acima do stop
                sai = o[j] * (1 + desl + 0.0005)
                break
            if h[j] >= stop:
                sai = stop * (1 + desl + 0.0005)
                break
            if l[j] <= alvo:
                sai = alvo * (1 + desl)
                break
        if sai is None:
            sai = c[fim] * (1 + desl)
            j = fim
        bruto = (e - sai) / R
        custo = FEE * (e + sai) / R
        out.append((t[i + 1], bruto - custo, b))
        livre = j
    return out


def resumo(ops, seed=7):
    if not ops:
        return {"n": 0}
    rs = np.array([r for _, r, _ in ops])
    sem = np.array([int(t) // (7 * 86400) for t, _, _ in ops])
    us = np.unique(sem)
    soma = {s: rs[sem == s].sum() for s in us}
    cnt = {s: (sem == s).sum() for s in us}
    rng = np.random.default_rng(seed)
    bs = []
    keys = list(us)
    for _ in range(1000):
        pick = rng.integers(0, len(keys), len(keys))
        tot = sum(soma[keys[q]] for q in pick)
        nn = sum(cnt[keys[q]] for q in pick)
        bs.append(tot / nn)
    lo, hi = np.percentile(bs, [5, 95])
    return {"n": int(len(rs)), "semanas": int(len(us)), "r": round(float(rs.mean()), 4), "ic90": [round(float(lo), 4), round(float(hi), 4)],
            "acerto": round(float((rs > 0).mean()), 3), "pf": round(float(rs[rs > 0].sum() / max(1e-9, -rs[rs < 0].sum())), 3)}


def turtle_sinais(S):
    """SHORT_TURTLE aproximada: fecho de 4H abaixo do minimo das 120 velas (20 dias) anteriores."""
    pm = np.r_[np.nan, rolling_min(S["l"], 120)[:-1]]
    return set(np.where(S["c"] < pm)[0].tolist())


def main(saida):
    D = carregar()
    ctx = btc_ctx(D)
    print("moedas", len(D), flush=True)
    TUR = {b: turtle_sinais(S) for b, S in D.items()}
    res = []
    for fam, (fn, grid) in FAM.items():
        for p in grid:
            sig = {b: fn(S, p, ctx) for b, S in D.items()}
            nsig = sum(len(v) for v in sig.values())
            sobre = sum(1 for b, v in sig.items() for i in v if any(j in TUR[b] for j in range(i - 6, i + 1)))
            for sd in SAIDAS:
                ops = []
                for b, S in D.items():
                    ops += simular(S, b, sig[b], sd)
                tr = [x for x in ops if x[0] < T_VAL]
                va = [x for x in ops if T_VAL <= x[0] < T_TEST]
                te = [x for x in ops if x[0] >= T_TEST]
                res.append({"fam": fam, "p": p, "saida": sd, "sinais": nsig,
                            "sobreposicao_turtle": round(sobre / max(1, nsig), 3),
                            "treino": resumo(tr), "validacao": resumo(va), "teste": resumo(te)})
            print(fam, p, "feito", flush=True)
    with open(saida, "w") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main(sys.argv[1])
