"""Autopsia de um lutador morto da arena (investigacao, 2026-10-17).

Corre a funcao de sinal do ringue (tools.arena_ringue.NEW_SIGS[chave]) vela
a vela no historico de 4H (so velas fechadas: o sinal da vela i so ve as
velas ate i; entrada na abertura de i+1), com o filtro do BTC acima da
SMA200 conhecido no fecho do dia anterior, uma operacao de cada vez por
moeda, a gestao de engine/trade.py e os custos do papel (0,25% + 0,1% por
lado). Para cada operacao guarda a saida, a duracao, a excursao maxima a
favor (MFE, em R), o risco e a hora. Compara com entradas ao acaso na mesma
moeda (+-90 velas, mesma geometria) por tools.research_rlib.control_rs.

Por omissao a autopsia so olha para a JANELA DE DESENHO (18 primeiros meses
dos ultimos 24): a reserva fica de fora para nao contaminar um sucessor.

Uso: python -m tools.autopsia_arena <historico> <CHAVE> [--tudo]
"""
import collections
import json
import random
import sys
import time

from engine import backtest as B, paper_bounce as PB, trade
from tools import arena_ringue as AR
from tools import research_rlib as R
from tools.research_dip import window

H4, DAY = B.H4, 86400
LOOKBACK = 400          # velas passadas a funcao de sinal (66 dias: chega para a SMA50 diaria)


def walk(asset, c4, above, fn, t0, t1, lookback=LOOKBACK):
    """Operacoes de `fn` na moeda com sinal em [t0, t1). So passado no sinal."""
    AR.CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if i < busy or not t0 <= t_sig < t1 or not AR._known(t_sig, above):
            continue
        sig = fn(c4[max(0, i - lookback + 1):i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]
        if not sig["stop"] < px < sig["tp"][0]:
            continue
        risk = px - sig["stop"]
        pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"],
                                  PB.FEE_PCT, PB.SLIP_PCT, breakeven=True)
        k, mfe = i + 1, 0.0
        while not pos["closed"] and k < len(c4):
            x = c4[k]
            mfe = max(mfe, (x["h"] - px) / risk)
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H4)
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append({"asset": asset, "i": i + 1, "t": pos["opened_at"], "r": pos["r"],
                    "exit": pos["exit_reason"], "mfe": round(mfe, 3),
                    "dur_h": (pos["closed_at"] - pos["opened_at"]) / 3600,
                    "risk": risk / px, "tp1_r": (sig["tp"][0] - px) / risk,
                    "hour": time.gmtime(t_sig).tm_hour, "hold": sig["hold_s"],
                    "geo": {"stop": sig["stop"] / px - 1,
                            "tp": [z / px - 1 for z in sig["tp"]],
                            "partials": list(sig["partials"]), "breakeven": True}})
    return out


def stats(tr):
    if not tr:
        return {"n": 0}
    r = [t["r"] for t in tr]
    return {"n": len(r), "r_medio": round(sum(r) / len(r), 3),
            "acerto_pct": round(100 * sum(1 for x in r if x > 0) / len(r), 1)}


def vs_random(tr, data, reps=1000, seed=7):
    pools, real = [], []
    for t in tr:
        p = R.control_rs(data[t["asset"]], t["i"], t["geo"], H4, t["hold"], 90)
        if p:
            pools.append(p)
            real.append(t["r"])
    if not real:
        return {"n": 0}
    rng = random.Random(seed)
    dist = sorted(sum(rng.choice(p) for p in pools) / len(pools) for _ in range(reps))
    m = sum(real) / len(real)
    return {"n": len(real), "r_real": round(m, 3), "acaso_mediana": round(dist[len(dist) // 2], 3),
            "acaso_p95": round(dist[int(0.95 * (len(dist) - 1))], 3),
            "percentil": round(100 * sum(1 for x in dist if x < m) / len(dist), 1)}


def report(tr, data):
    by = collections.defaultdict(list)
    for t in tr:
        by[t["exit"]].append(t)
    st = [t for t in tr if t["exit"] == "STOP"]
    return {"todas": stats(tr), "acaso": vs_random(tr, data),
            "saidas": {k: stats(v) for k, v in sorted(by.items())},
            "risco_medio_pct": round(100 * sum(t["risk"] for t in tr) / max(1, len(tr)), 2),
            "custo_medio_r": round(sum(2 * (PB.FEE_PCT + PB.SLIP_PCT) / 100 / t["risk"]
                                       for t in tr) / max(1, len(tr)), 3),
            "mfe_ate_tp1_pct": round(100 * sum(1 for t in tr if t["mfe"] >= t["tp1_r"]) / max(1, len(tr)), 1),
            "stops_por_duracao": {f"{a}-{b}h": stats([t for t in st if a <= t["dur_h"] < b])
                                  for a, b in ((0, 12), (12, 48), (48, 10 ** 6))},
            "por_hora": {h: stats([t for t in tr if t["hour"] == h]) for h in range(0, 24, 4)}}


def main(folder, key, tudo=False):
    data, _ = B.load_all(folder)
    btc = data["BTC"]
    above = AR.btc_above(btc)
    AR.CTX.update(btc=btc, bars=data, funding={}, oi={}, macro={}, ls={}, rank={})
    d0, ds, d1 = window(btc[-1]["t"] // DAY)
    t1 = (d1 if tudo else ds) * DAY
    fn = AR.NEW_SIGS[key]
    tr = [t for a, c4 in sorted(data.items()) for t in walk(a, c4, above, fn, d0 * DAY, t1)]
    return {"lutador": key, "janela": [d0, (d1 if tudo else ds) - 1], "reserva_incluida": tudo,
            **report(tr, data)}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2], "--tudo" in sys.argv), indent=1))
