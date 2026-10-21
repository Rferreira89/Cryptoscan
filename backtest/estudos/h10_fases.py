"""H10 (pre-registado a 21/10, antes de correr; pedido do Rui: "agentes a
trabalhar em todas as fases do mercado, e nao so sobrevenda").

Pergunta: que estrategias do arsenal (todas as familias, compras e vendas a
descoberto) ganham em CADA fase do mercado, de forma repetida em dois periodos?

Fases: as do programa (engine/arena.market_regime, BTC diario): subida, lateral, queda.
Periodos: A = 2021-06-01 a 2024-05-31, B = 2024-06-01 a 2026-10-15.
Moedas: as 25 com mais volume das atuais + filtro de liquidez por data (5 M USD/dia).
Custos: os do ringue (0,25% + 0,10% por lado).
Criterio para uma estrategia ser APTA numa fase (fixado antes de ver):
  nos DOIS periodos: R medio por operacao >= +0,10, R medio por dia > 0 (cada
  dia conta uma vez), e pelo menos 15 dias distintos com entradas nessa fase.
As compras seguem o filtro do BTC acima da media de 200 dias, como ao vivo;
as vendas a descoberto nao (como ao vivo).
"""
import glob, gzip, os, sys, json, statistics
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import arena_ringue as AR
from engine import backtest as B, short as SH

DAY = 86400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
LIQ = 5e6
LONGS = ["BOUNCE_X30", "BOUNCE_ISOLADA", "REVERSAO_INTERVALO", "SQUEEZE_BB", "TURTLE", "BRK_ESPACO",
         "RETESTE", "VOLUME_ACUMULACAO", "CAPITULACAO", "DIP_TREND", "FIBO_RECUO",
         "MAIORES_RECUO", "MAIORES_TENDENCIA"]
SHORTS = ["SHORT_X30", "SHORT_ISOLADA", "SHORT_TURTLE", "SHORT_FLUXO",
          "SHORT_MAIORES_RECUO", "SHORT_MAIORES_TENDENCIA"]
MAIORES = {"BTC", "ETH", "SOL"}


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


BTC = load("/tmp/claude-0/hist/BTC.csv.gz")
ABOVE = AR.btc_above(BTC)
ALWAYS = {k: True for k in ABOVE}
RMAP = AR.regime_by_day(BTC)


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
    c4 = load(f"/tmp/claude-0/hist/{a}.csv.gz")
    m4 = SH.mirror(c4)
    AR.CTX.update(btc=BTC, bars={"BTC": BTC, a: c4}, funding={}, rank={},
                  daily={a: B.daily(c4)})
    lq = liquidez(c4)
    out = []
    for k in LONGS + SHORTS:
        if k.replace("SHORT_", "").startswith("MAIORES_") and a not in MAIORES:
            continue
        short = k.startswith("SHORT_")
        fn = AR.SHORT_SIGS[k] if short else AR.NEW_SIGS.get(k) or AR.MAIORES_SIGS.get(k)
        if short:
            AR.CTX["daily"] = {a: B.daily(m4)}
        else:
            AR.CTX["daily"] = {a: B.daily(c4)}
        try:
            for _, t in AR.generic_trades(a, m4 if short else c4, ALWAYS if short else ABOVE, A0, k, fn):
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
    for p in glob.glob("/tmp/claude-0/hist/*.csv.gz"):
        a = os.path.basename(p).split(".")[0]
        c = load(p)
        vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
    moedas = sorted(vol, key=lambda a: -vol[a])[:25]
    for m in MAIORES:
        if m not in moedas:
            moedas.append(m)
    with Pool(2) as pool:
        todos = [t for r in pool.map(trabalho, moedas) for t in r]
    json.dump(todos, open("/tmp/claude-0/estudo/h10_trades.json", "w"))
    print("moedas:", ", ".join(moedas))
    aptas = {}
    for fase in ("subida", "lateral", "queda"):
        print(f"\n=== Fase {fase} ===")
        for k in LONGS + SHORTS:
            ra = resumo([t for t in todos if t["k"] == k and t["fase"] == fase and A0 <= t["t"] < A1])
            rb = resumo([t for t in todos if t["k"] == k and t["fase"] == fase and B0 <= t["t"] < B1])
            if not ra["n"] and not rb["n"]:
                continue
            ok = all(x["n"] and x["r"] >= 0.10 and x["r_dia"] > 0 and x["dias"] >= 15 for x in (ra, rb))
            if ok:
                aptas.setdefault(fase, []).append(k)
            print(f"{k:24s} A {ra} | B {rb}{'  <== APTA' if ok else ''}")
    print("\nAPTAS:", json.dumps(aptas))
