"""H12 (pre-registado a 22/10, ANTES de correr; pacote aprovado pelo Rui).

Pergunta: outra saida melhora o SHORT_TURTLE (Ramiro) na fase lateral, onde opera?
Base: objetivos 2R e 5R (metade em cada), stop para a entrada no 1.o, depois segue o
preco a 1R, maximo 20 dias.
Variantes (4 hipoteses):
  V1 maximo 10 dias            V2 objetivos 1,5R e 3R
  V3 tudo no 2R                V4 seguir o preco a 0,5R
Dados e custos: os do H10/H10b (25 moedas, 5 M USD/dia, 0,25% + 0,10% por lado,
juro do emprestimo 20% ao ano sobre a posicao).
Criterio (fixado antes): uma variante substitui a base so se, nos DOIS periodos e na
fase lateral, o R liquido por operacao for >= base + 0,05 E o R liquido por dia >= o da
base, com >= 15 dias distintos. Contador global de hipoteses: +4.
"""
import json, sys, gzip, glob, os, statistics
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import arena_ringue as AR
from engine import backtest as B, short as SH, trade
import engine.paper_bounce as PB
DAY, H4 = 86400, 14400
APR = 0.20
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
exec(open("/tmp/claude-0/estudo/h10_fases.py").read().split("def trabalho")[0].split('"""', 2)[2])


def variante(nome):
    base = AR.SHORT_SIGS["SHORT_TURTLE"]

    def f(m4):
        s = base(m4)
        if not s or nome == "BASE":
            return s
        e, st = m4[-1]["c"], s["stop"]
        r = e - st
        s = dict(s)
        if nome == "V1_10DIAS":
            s["hold_s"] = 10 * DAY
        elif nome == "V2_1_5R_3R":
            s["tp"] = [e + 1.5 * r, e + 3 * r]
        elif nome == "V3_TUDO_2R":
            s["tp"], s["partials"] = [e + 2 * r], [100]
        elif nome == "V4_TRAIL_0_5":
            s["trail_r"] = 0.5
        return s
    return f


VARS = ["BASE", "V1_10DIAS", "V2_1_5R_3R", "V3_TUDO_2R", "V4_TRAIL_0_5"]


def corre(a):
    c4 = load(f"/tmp/claude-0/hist/{a}.csv.gz"); m4 = SH.mirror(c4)
    AR.CTX.update(btc=BTC, bars={"BTC": BTC, a: c4}, daily={a: B.daily(m4)}, asset=a)
    lq = liquidez(c4); out = []
    for v in VARS:
        fn, busy = variante(v), -1
        for i in range(250, len(m4) - 1):
            t_sig = m4[i]["t"] + H4
            if i < busy or t_sig < A0:
                continue
            sig = fn(m4[:i + 1])
            if not sig:
                continue
            px = m4[i + 1]["o"]
            if not (sig["stop"] < px < sig["tp"][0]):
                continue
            pos = trade.open_position(dict(sig, max_hold_s=None), px, m4[i + 1]["t"], PB.FEE_PCT, PB.SLIP_PCT, breakeven=True)
            k = i + 1; fim = None
            while not pos["closed"] and k < len(m4):
                x = m4[k]
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"])); trade._finish(pos, "TIME", x["t"] + H4)
                fim = x["t"] + H4; k += 1
            if not pos["closed"]:
                continue
            busy = k
            d = pos["opened_at"] // DAY
            if lq.get(d - 1, 0) < LIQ:
                continue
            dias = (fim - pos["opened_at"]) / DAY
            stop = abs(sig["stop"] / px - 1)
            juro_r = APR * dias / 365 / stop if stop else 0
            out.append({"v": v, "a": a, "t": pos["opened_at"], "r": pos["r"] - juro_r, "fase": RMAP.get(d - 1)})
    return out


def res(ts):
    if not ts:
        return {"n": 0, "dias": 0}
    dd = {}
    for t in ts:
        dd.setdefault(t["t"] // DAY, []).append(t["r"])
    md = [sum(v) / len(v) for v in dd.values()]
    return {"n": len(ts), "r": round(sum(t["r"] for t in ts) / len(ts), 3), "dias": len(dd), "r_dia": round(sum(md) / len(md), 3)}


if __name__ == "__main__":
    from multiprocessing import Pool
    vol = {}
    for p in glob.glob("/tmp/claude-0/hist/*.csv.gz"):
        a = os.path.basename(p).split(".")[0]; c = load(p); vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
    moedas = sorted(vol, key=lambda a: -vol[a])[:25]
    with Pool(2) as pool:
        T = [t for r in pool.map(corre, moedas) for t in r]
    json.dump(T, open("/tmp/claude-0/estudo/h12_trades.json", "w"))
    aprov = []
    for fase in ("lateral", "queda", "subida"):
        print(f"\n=== Fase {fase}{' (a que conta)' if fase == 'lateral' else ' (informação)'} ===")
        base = {p: res([t for t in T if t["v"] == "BASE" and t["fase"] == fase and a0 <= t["t"] < a1]) for p, a0, a1 in (("A", A0, A1), ("B", B0, B1))}
        for v in VARS:
            rr = {p: res([t for t in T if t["v"] == v and t["fase"] == fase and a0 <= t["t"] < a1]) for p, a0, a1 in (("A", A0, A1), ("B", B0, B1))}
            ok = v != "BASE" and fase == "lateral" and all(
                rr[p]["n"] and base[p]["n"] and rr[p]["dias"] >= 15 and rr[p]["r"] >= base[p]["r"] + 0.05 and rr[p]["r_dia"] >= base[p]["r_dia"] for p in "AB")
            if ok:
                aprov.append(v)
            print(f"{v:14s} A {rr['A']} | B {rr['B']}{'  <== MELHOR' if ok else ''}")
    print("\nAPROVADAS:", aprov)
