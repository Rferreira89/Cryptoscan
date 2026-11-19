"""Autopsia de RACIO_DISP (morto na arena a 2026-11-19 05:40 UTC, forma recente: 20 op., -0,219R).

Reproduz com o historico do ramo `history` o combate da arena (mesma logica de
tools.arena_ringue.generic_trades, com a funcao de sinal do ringue AR.NEW_SIGS["RACIO_DISP"]) e regista por
operacao: motivo de saida, se o objetivo foi tocado, a maior subida a favor (MFE, em R), o retorno da moeda, do BTC
e do racio moeda/BTC entre a entrada e a saida, o retorno do BTC nos 7 dias antes da entrada e o regime do BTC.
Pergunta principal: as perdas vem de o racio nao voltar a media (a entrada falha) ou de o racio voltar e o BTC
cair (a operacao compra a moeda em dolares sem cobrir o BTC, por isso fica exposta a beta do mercado)?
So velas fechadas (a funcao de sinal recebe c4[:i+1]).

Uso: python -m tools.autopsia_racio_disp <historico> [saida.json]
"""
import bisect
import json
import sys
from collections import Counter, defaultdict

from engine import backtest as B, trade
from engine import paper_bounce as PB
from tools import arena_ringue as AR

H4, DAY = B.H4, B.DAY


def _px(serie, ts, t):
    """Fecho da ultima vela de `serie` com fecho <= t (ts = tempos de abertura)."""
    k = bisect.bisect_right(ts, t - H4) - 1
    return serie[k]["c"] if k >= 0 else None


def trades(asset, c4, above, t0, t1, fn, btc):
    """Igual a arena_ringue.generic_trades (uma posicao por moeda), com detalhe por operacao."""
    AR.CTX["asset"] = asset
    bts = [x["t"] for x in btc]
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
        t_in, t_out = pos["opened_at"], pos["closed_at"]
        b0, b1 = _px(btc, bts, t_in), _px(btc, bts, t_out)
        # fecho da moeda na vela de saida (aproximacao do preco de saida para a decomposicao)
        c_out = c4[k - 1]["c"]
        moeda = c_out / px - 1
        btc_r = (b1 / b0 - 1) if b0 and b1 else None
        racio = ((1 + moeda) / (1 + btc_r) - 1) if btc_r is not None else None
        c7 = _px(btc, bts, t_sig - 7 * DAY)
        out.append({"asset": asset, "t": t_in, "r": pos["r"], "saida": pos["exit_reason"],
                    "tp_tocado": tp1, "mfe_r": round(mfe, 2), "horas": (t_out - t_in) / 3600,
                    "stop_pct": round(100 * risk / px, 2), "tp_r": round((sig["tp"][0] - px) / risk, 2),
                    "moeda_pct": round(100 * moeda, 2),
                    "btc_pct": None if btc_r is None else round(100 * btc_r, 2),
                    "racio_pct": None if racio is None else round(100 * racio, 2),
                    "btc7d_pct": round(100 * (_px(btc, bts, t_sig) / c7 - 1), 2) if c7 else None})
    return out


def _m(v):
    return {"n": len(v), "r": round(sum(v) / len(v), 3)} if v else {"n": 0}


def resumo(trs, reg):
    if not trs:
        return {"n": 0}
    n = len(trs)
    rs = [t["r"] for t in trs]
    stops = [t for t in trs if t["saida"] == "STOP"]
    out = {"n": n, "r_medio": round(sum(rs) / n, 3), "acerto_pct": round(100 * sum(r > 0 for r in rs) / n, 1),
           "saidas": dict(Counter(t["saida"] for t in trs)),
           "tp_tocado_pct": round(100 * sum(t["tp_tocado"] for t in trs) / n, 1),
           "stops_antes_24h_pct": round(100 * sum(t["horas"] <= 24 for t in stops) / max(1, len(stops)), 1),
           "tp_r_mediano": sorted(t["tp_r"] for t in trs)[n // 2],
           "dias_distintos": len({t["t"] // DAY for t in trs}),
           "max_ops_mesmo_dia": max(Counter(t["t"] // DAY for t in trs).values())}
    # decomposicao: o racio subiu (a reversao aconteceu) ou nao; o BTC subiu ou caiu durante a operacao
    q = defaultdict(list)
    for t in trs:
        if t["racio_pct"] is None:
            continue
        q[("racio_sobe" if t["racio_pct"] > 0 else "racio_desce") + "/" +
          ("btc_sobe" if t["btc_pct"] > 0 else "btc_desce")].append(t["r"])
    out["racio_x_btc"] = {k: _m(v) for k, v in sorted(q.items())}
    ok = [t for t in trs if t["racio_pct"] is not None]
    for c in ("moeda_pct", "btc_pct", "racio_pct"):
        out["media_" + c] = round(sum(t[c] for t in ok) / max(1, len(ok)), 2)
    out["racio_sobe_pct"] = round(100 * sum(t["racio_pct"] > 0 for t in ok) / max(1, len(ok)), 1)
    perd = [t for t in trs if t["r"] < 0 and t["racio_pct"] is not None]
    out["perdedoras_com_racio_a_subir_pct"] = round(100 * sum(t["racio_pct"] > 0 for t in perd) / max(1, len(perd)), 1)
    out["perdedoras_btc_mediano_pct"] = sorted(t["btc_pct"] for t in perd)[len(perd) // 2] if perd else None
    out["ganhadoras_btc_mediano_pct"] = (sorted(t["btc_pct"] for t in trs if t["r"] > 0 and t["btc_pct"] is not None)
                                         or [None])[sum(1 for t in trs if t["r"] > 0 and t["btc_pct"] is not None) // 2]
    g, rg = defaultdict(list), defaultdict(list)
    for t in trs:
        ch = t["btc7d_pct"]
        if ch is not None:
            g["btc7d<-5%" if ch < -5 else ("btc7d -5..0%" if ch < 0 else "btc7d>=0")].append(t["r"])
        rg[reg.get((t["t"] - DAY) // DAY, "?")].append(t["r"])
    out["por_btc_7d"] = {k: _m(v) for k, v in sorted(g.items())}
    out["por_regime"] = {k: _m(v) for k, v in sorted(rg.items())}
    return out


def main(folder, out="backtest/autopsia_2026-11-19.json"):
    data, _ = B.load_all(folder, min_bars=1500)
    btc = data["BTC"]
    above, reg = AR.btc_above(btc), AR.regime_by_day(btc)
    now = btc[-1]["t"] + H4
    AR.CTX.update(btc=btc, bars=data, funding={}, oi={}, macro={}, ls={}, rank={}, daily={})
    periodos = {"combate_90d": (now - 90 * DAY, now),
                "desenho_18m": (now - 730 * DAY, now - 182 * DAY),
                "reserva_6m_sem_combate": (now - 182 * DAY, now - 90 * DAY),
                "antigo_2021_2024": (now - 1935 * DAY, now - 730 * DAY)}
    fn = AR.NEW_SIGS["RACIO_DISP"]
    res = {"ultima_vela_btc": btc[-1]["t"], "moedas": len(data), "periodos": {k: list(v) for k, v in periodos.items()}}
    for nome, (a, b) in periodos.items():
        trs = []
        for asset, c4 in sorted(data.items()):
            if asset == "BTC":
                continue
            trs += trades(asset, c4, above, a, b, fn, btc)
        trs.sort(key=lambda t: t["t"])
        res[nome] = resumo(trs, reg)
        if nome == "combate_90d":
            res[nome]["operacoes"] = trs
    with open(out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    for nome, v in r.items():
        if isinstance(v, dict) and "n" in v:
            print(nome, json.dumps({a: b for a, b in v.items() if a != "operacoes"}, ensure_ascii=False))
