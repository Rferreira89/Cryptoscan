"""H11 (pre-registado a 22/10, ANTES de correr; pedido do Rui: "devemos ter
agentes para as estrategias de subida").

Contexto: no H10 nenhuma estrategia do arsenal ganhou na fase de subida nos
dois periodos. O TURTLE ficou perto (R por dia +0,12 e +0,29, mas R por
operacao -0,01 em 2021-24). O MOMENTUM nao entrou no H10.

Pergunta: alguma de 4 estrategias de tendencia, pensadas para a subida, ganha
nessa fase nos dois periodos?
  1. MOMENTUM          rotacao semanal: as 5 moedas mais fortes a 30 dias (do arsenal, nao testada no H10)
  2. TURTLE_55         rompimento do maximo de 55 dias (Sistema 2 das Tartarugas), stop 2N, 2R/5R e stop que segue
  3. RECUO_FORTES      moeda mais forte que o BTC a 30 dias, acima das medias de 50 e 200 dias,
                       recua ate a media de 20 dias (4H) e fecha acima do maximo da vela anterior;
                       stop no minimo das ultimas 6 velas, 2R/5R e stop que segue
  4. TURTLE_FORTES     o TURTLE de 20 dias, mas so em moedas mais fortes que o BTC a 30 dias

Fases, periodos, moedas, custos e liquidez: iguais ao H10 (25 moedas com mais
volume, 5 M USD/dia, 0,25% + 0,10% por lado, filtro BTC acima da media de 200 dias).
Criterio APTA (o do H10, fixado antes): nos DOIS periodos, so na fase subida,
R medio por operacao >= +0,10, R medio por dia > 0 e >= 15 dias distintos.
Contador global de hipoteses: +4.
"""
import glob, gzip, os, sys, json, statistics, time
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import arena_ringue as AR
from engine import backtest as B, paper_bounce as PB

DAY, H4 = 86400, 14400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
LIQ = 5e6
HIST = "/tmp/claude-0/hist"


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


BTC = load(f"{HIST}/BTC.csv.gz")
ABOVE = AR.btc_above(BTC)
RMAP = AR.regime_by_day(BTC)
BTC_T = [x["t"] + H4 for x in BTC]


def btc_ret30(t):
    import bisect
    k = bisect.bisect_right(BTC_T, t) - 1
    return BTC[k]["c"] / BTC[k - 180]["c"] - 1 if k >= 180 else None


def mais_forte(c4):
    b = btc_ret30(c4[-1]["t"] + H4)
    mine = c4[-1]["c"] / c4[-181]["c"] - 1 if len(c4) > 181 else None
    return mine is not None and b is not None and mine > b and mine > 0


def sig_turtle55(c4):
    d = [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]
    if len(d) < 60:
        return None
    hi = max(x["h"] for x in d[-56:-1])
    if not (c4[-1]["c"] > hi >= c4[-2]["c"]):
        return None
    tr = [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"]) for k in range(len(d) - 20, len(d))]
    return AR._trend_plan(c4, c4[-1]["c"] - 2 * sum(tr) / 20, gat="rompimento do máximo de 55 dias")


def sig_recuo_fortes(c4):
    if len(c4) < 1300 or not mais_forte(c4):
        return None
    c = [x["c"] for x in c4]
    sma = lambda n: sum(c[-n:]) / n
    s50, s200 = sma(300), sma(1200)            # 50 e 200 dias em velas de 4H
    if not (c[-1] > s50 > s200):
        return None
    e20 = sma(20)
    toque = min(x["l"] for x in c4[-3:]) <= e20 * 1.005
    if not (toque and c[-1] > c4[-2]["h"] and c[-1] > e20):
        return None
    return AR._trend_plan(c4, min(x["l"] for x in c4[-6:]) * 0.998, gat="recuo à média de 20 numa moeda forte")


def sig_turtle_fortes(c4):
    if len(c4) < 182 or not mais_forte(c4):
        return None
    return AR.sig_turtle(c4)


SIGS = {"MOMENTUM": AR.sig_momentum, "TURTLE_55": sig_turtle55, "RECUO_FORTES": sig_recuo_fortes,
        "TURTLE_FORTES": sig_turtle_fortes}
RANK = {}


def liquidez(c4):
    dv = {}
    for x in c4:
        d = x["t"] // DAY
        dv[d] = dv.get(d, 0) + x["v"] * x["c"]
    out, j = {}, []
    for d in sorted(dv):
        j.append(dv[d]); j = j[-30:]
        out[d] = statistics.median(j)
    return out


def trabalho(a):
    c4 = load(f"{HIST}/{a}.csv.gz")
    AR.CTX.update(btc=BTC, bars={"BTC": BTC, a: c4}, funding={}, rank=RANK, daily={a: B.daily(c4)})
    lq = liquidez(c4)
    out = []
    for k, fn in SIGS.items():
        try:
            for _, t in AR.generic_trades(a, c4, ABOVE, A0, k, fn):
                d = t["t"] // DAY
                if lq.get(d - 1, 0) >= LIQ:
                    out.append({"k": k, "a": a, "t": t["t"], "r": t["r"], "fase": RMAP.get(d - 1)})
        except Exception as e:
            print(a, k, type(e).__name__, e, file=sys.stderr)
    return out


def resumo(ts):
    if not ts:
        return {"n": 0, "dias": 0}
    dias = {}
    for t in ts:
        dias.setdefault(t["t"] // DAY, []).append(t["r"])
    md = [sum(v) / len(v) for v in dias.values()]
    return {"n": len(ts), "r": round(sum(t["r"] for t in ts) / len(ts), 3), "dias": len(dias),
            "r_dia": round(sum(md) / len(md), 3)}


if __name__ == "__main__":
    vol = {}
    for p in glob.glob(f"{HIST}/*.csv.gz"):
        a = os.path.basename(p).split(".")[0]
        c = load(p)
        vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
    moedas = sorted(vol, key=lambda a: -vol[a])[:25]
    for m in ("BTC", "ETH", "SOL"):
        if m not in moedas:
            moedas.append(m)
    # ranking de momentum so as segundas 00h UTC, entre as moedas do estudo
    bars = {a: load(f"{HIST}/{a}.csv.gz") for a in moedas}
    for t in range(A0 - A0 % (7 * DAY) + 4 * DAY, B1 + 7 * DAY, 7 * DAY):   # 1970-01-05 foi segunda
        RANK[t] = AR.momentum_rank(bars, t)
    del bars
    t0 = time.time()
    with Pool(2) as pool:
        todos = [t for r in pool.map(trabalho, moedas) for t in r]
    json.dump(todos, open("/tmp/claude-0/estudo/h11_trades.json", "w"))
    print("moedas:", ", ".join(moedas), f"({time.time() - t0:.0f}s)")
    aptas = []
    for fase in ("subida", "lateral", "queda"):
        print(f"\n=== Fase {fase}{' (a que conta)' if fase == 'subida' else ' (só para informação)'} ===")
        for k in SIGS:
            ra = resumo([t for t in todos if t["k"] == k and t["fase"] == fase and A0 <= t["t"] < A1])
            rb = resumo([t for t in todos if t["k"] == k and t["fase"] == fase and B0 <= t["t"] < B1])
            ok = fase == "subida" and all(x["n"] and x["r"] >= 0.10 and x["r_dia"] > 0 and x["dias"] >= 15 for x in (ra, rb))
            if ok:
                aptas.append(k)
            print(f"{k:16s} A {ra} | B {rb}{'  <== APTA' if ok else ''}")
    print("\nAPTAS na subida:", aptas)
