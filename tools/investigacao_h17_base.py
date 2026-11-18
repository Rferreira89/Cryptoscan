"""(18/11, investigacao isolada; nada em producao) H17: (1) o RACIO_DISP ao vivo com as velas que o scanner tem;
(2) a regra-base R4 (racio moeda/BTC, sem filtro de dispersao) por ano, sem os ultimos 90 dias e com intervalo
bootstrap por dia. Nao muda sinais, criterios nem classificacao.
Uso: python -m tools.investigacao_h17_base <pasta_history> <saida.json>"""
import json
import random
import statistics
import sys
import time

from engine import backtest as B
from tools import arena_ringue as AR
from tools.afinacao_h09_racio import B_START, racio_var

DAY, H4 = AR.DAY, AR.H4


def vivo(bars, n_velas):
    """Quantos fechos recentes (ultimos 30) dariam percentil de dispersao com n_velas por moeda."""
    corte = {a: c[-n_velas:] for a, c in bars.items()}
    AR.CTX.update(bars=corte, btc=corte["BTC"])
    AR._DISP["chave"] = None
    fim = corte["BTC"][-1]["t"] + H4
    ok = sum(1 for k in range(30) if AR.percentil_dispersao(fim - k * H4) is not None)
    return {"velas": n_velas, "fechos_com_percentil_ultimos_30": ok}


def boot(trs, rng, reps=5000):
    por_dia = {}
    for t in trs:
        por_dia.setdefault(t["t"] // DAY, []).append(t["r"])
    dias = list(por_dia.values())
    if not dias:
        return None
    ms = []
    for _ in range(reps):
        amostra = [r for _ in dias for r in rng.choice(dias)]
        ms.append(statistics.mean(amostra))
    ms.sort()
    return {"ic90": [round(ms[int(.05 * reps)], 4), round(ms[int(.95 * reps)], 4)],
            "p_r_menor_igual_0": round(sum(1 for m in ms if m <= 0) / reps, 4)}


def main(folder, dest):
    bars, _ = B.load_all(folder, min_bars=1500)
    out = {"vivo": [vivo(bars, n) for n in (300, 500, 569, 570, 600, 1100)]}
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    AR._DISP["chave"] = None
    end = max(x["t"] for x in btc) + H4
    above = AR.btc_above(btc)
    fn = racio_var(120, 2.5, 2.0, 3, 35)
    trs = sorted((t for a in sorted(bars) if a != "BTC"
                  for _, t in AR.generic_trades(a, bars[a], above, B_START, "R4", fn)), key=lambda t: t["t"])
    rng = random.Random(17)
    def res(v):
        return {"n": len(v), "r_medio": round(statistics.mean([t["r"] for t in v]), 4) if v else None,
                **(boot(v, rng) or {})}
    anos = {}
    for t in trs:
        anos.setdefault(time.gmtime(t["t"]).tm_year, []).append(t)
    out["R4"] = {"tudo": res(trs),
                 "sem_ultimos_90d": res([t for t in trs if t["t"] < end - 90 * DAY]),
                 "ultimos_90d": res([t for t in trs if t["t"] >= end - 90 * DAY]),
                 "por_ano": {y: res(v) for y, v in sorted(anos.items())}}
    print(json.dumps(out, indent=1))
    with open(dest, "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
