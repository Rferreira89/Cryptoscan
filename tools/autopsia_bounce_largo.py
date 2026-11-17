"""Autopsia de BOUNCE_LARGO_X30V20 e BOUNCE_LARGO_X35V20 (mortos na arena a 2026-11-14 e 2026-11-17).

Reproduz, com o historico do ramo `history`, o combate da arena (mesma logica de
tools.arena_ringue.generic_trades, com as mesmas funcoes de sinal sig_bounce_largo) e regista por operacao: motivo
de saida, se o 1.o objetivo foi tocado, a maior subida a favor (MFE, em R) antes da saida, o tempo ate a saida, o
retorno do BTC nos 7 dias antes da entrada e o regime do BTC. Faz o mesmo nos 18 meses de desenho para separar o
que e do periodo recente do que e da regra. So velas fechadas (as funcoes de sinal recebem c4[:i+1]).

Uso: python -m tools.autopsia_bounce_largo <historico> [saida.json]
"""
import json
import sys
from collections import Counter, defaultdict

from engine import backtest as B, trade
from engine import paper_bounce as PB
from tools import arena_ringue as AR

H4, DAY = B.H4, B.DAY


def trades(asset, c4, above, t0, t1, fn):
    """Igual a arena_ringue.generic_trades (G0, uma posicao por moeda), com detalhe por operacao."""
    AR.CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if i < busy or t_sig < t0 or t_sig > t1 or not AR._known(t_sig, above):
            continue
        sig = fn(c4[:i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]
        if not (sig["stop"] < px < sig["tp"][0]):
            continue
        pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"], PB.FEE_PCT,
                                  PB.SLIP_PCT, breakeven=True)
        risk = px - sig["stop"]
        k, mfe, tp1 = i + 1, 0.0, False
        while not pos["closed"] and k < len(c4):
            x = c4[k]
            mfe = max(mfe, (x["h"] - px) / risk)
            tp1 = tp1 or x["h"] >= sig["tp"][0]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H4)
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append({"asset": asset, "t": pos["opened_at"], "r": pos["r"], "saida": pos["exit_reason"],
                    "tp1_tocado": tp1, "mfe_r": round(mfe, 2), "horas": (pos["closed_at"] - pos["opened_at"]) / 3600,
                    "stop_pct": round(100 * risk / px, 2), "tp1_r": round((sig["tp"][0] - px) / risk, 2)})
    return out


def resumo(trs, btc, reg):
    if not trs:
        return {"n": 0}
    bc = {x["t"]: x["c"] for x in btc}
    n = len(trs)
    rs = [t["r"] for t in trs]
    stops = [t for t in trs if t["saida"] == "STOP"]
    out = {"n": n, "r_medio": round(sum(rs) / n, 3), "acerto_pct": round(100 * sum(r > 0 for r in rs) / n, 1),
           "saidas": dict(Counter(t["saida"] for t in trs)),
           "tp1_tocado_pct": round(100 * sum(t["tp1_tocado"] for t in trs) / n, 1),
           "stops_com_mfe_ge_05R_pct": round(100 * sum(t["mfe_r"] >= 0.5 for t in stops) / max(1, len(stops)), 1),
           "stops_antes_24h_pct": round(100 * sum(t["horas"] <= 24 for t in stops) / max(1, len(stops)), 1),
           "stop_pct_mediano": sorted(t["stop_pct"] for t in trs)[n // 2],
           "tp1_r_mediano": sorted(t["tp1_r"] for t in trs)[n // 2],
           "dias_distintos": len({t["t"] // DAY for t in trs})}
    # por queda do BTC nos 7 dias antes da entrada e por regime do BTC
    grp, rg = defaultdict(list), defaultdict(list)
    for t in trs:
        e = t["t"] - H4                        # fecho da vela de sinal
        c0, c7 = bc.get(e - H4), bc.get(e - H4 - 7 * DAY)
        if c0 and c7:
            ch = c0 / c7 - 1
            grp["btc7d<-5%" if ch < -0.05 else ("btc7d -5..0%" if ch < 0 else "btc7d>=0")].append(t["r"])
        rg[reg.get((t["t"] - DAY) // DAY, "?")].append(t["r"])
    f = lambda d: {k: {"n": len(v), "r": round(sum(v) / len(v), 3)} for k, v in sorted(d.items())}
    out["por_btc_7d"], out["por_regime"] = f(grp), f(rg)
    # concentracao: operacoes por dia de entrada
    out["max_ops_mesmo_dia"] = max(Counter(t["t"] // DAY for t in trs).values())
    return out


def main(folder, out="backtest/autopsia_2026-11-17.json"):
    data, _ = B.load_all(folder)
    btc = data["BTC"]
    above, reg = AR.btc_above(btc), B.regimes(btc)
    now = btc[-1]["t"] + H4
    AR.CTX.update(btc=btc, bars=data, funding={}, oi={}, macro={}, ls={}, rank={})
    periodos = {"combate_90d": (now - 90 * DAY, now),
                "desenho_18m": (now - 730 * DAY, now - 182 * DAY),
                "reserva_6m": (now - 182 * DAY, now - 90 * DAY)}
    res = {"ultima_vela_btc": btc[-1]["t"], "moedas": len(data), "periodos": {k: list(v) for k, v in periodos.items()}}
    for key in ("BOUNCE_LARGO_X30V20", "BOUNCE_LARGO_X35V20"):
        fn = AR.FASE_AGRESSIVA_SIGS[key]
        res[key] = {}
        for nome, (a, b) in periodos.items():
            trs = []
            for asset, c4 in sorted(data.items()):
                trs += trades(asset, c4, above, a, b, fn)
            trs.sort(key=lambda t: t["t"])
            res[key][nome] = resumo(trs, btc, reg)
            if nome == "combate_90d":
                res[key][nome]["operacoes"] = trs
    with open(out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    for key in ("BOUNCE_LARGO_X30V20", "BOUNCE_LARGO_X35V20"):
        for nome, v in r[key].items():
            print(key, nome, json.dumps({a: b for a, b in v.items() if a != "operacoes"}, ensure_ascii=False))
