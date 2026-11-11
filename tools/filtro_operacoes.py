"""Operacoes historicas de cada lutador com o que o filtro de rentabilidade
precisa (auditoria de rentabilidade, 2026-11-11; so investigacao).

Igual a tools/arena_ringue.generic_trades (mesma funcao de sinal, mesma saida
G0, mesmos custos de 0,25% + 0,1% por lado, so velas fechadas, uma posicao por
moeda), mas guarda tambem a hora de FECHO e a distancia do stop: o filtro so
pode usar operacoes ja fechadas no instante da decisao, e o custo em R de uma
operacao depende da distancia do stop.

Shorts: o SINAL vem do espelho (engine/short.mirror, sem o filtro do BTC, como
no ringue), mas a OPERACAO e simulada em preco real (side="SHORT", niveis
convertidos 1/x), como na afinacao H14: o R do espelho infla os shorts em
0,07R a 0,24R (Tartarugas). O juro do emprestimo entra no filtro.
Nao muda nada no ringue nem na producao.

Uso: python -m tools.filtro_operacoes <pasta_history> <saida.json> [LUTADOR ...]
"""
import json
import sys
import time

from engine import backtest as B
from engine import paper_bounce as PB
from engine import short as SH
from engine import trade
from tools import arena_ringue as R

DAY, H4 = 86400, 4 * 3600
INICIO = 1627776000            # 2021-08-01 (aquecimento da SMA200 diaria antes)
REPRESENTANTES = [             # um por ideia distinta (os clones do Bounce estao a 0,9+ de correlacao)
    "BOUNCE_X30", "BOUNCE_AMPLITUDE", "BOUNCE_ISOLADA", "BOUNCE_FLUXO", "BOUNCE_HORAS", "CAPITULACAO",
    "DIP_TREND", "REVERSAO_INTERVALO", "FIBO_RECUO", "VOLUME_ACUMULACAO", "MAIORES_RECUO",
    "MAIORES_TENDENCIA", "TURTLE", "TURTLE_FORTES", "SQUEEZE_BB", "BRK_ESPACO", "RETESTE", "MOMENTUM",
    "SHORT_TURTLE", "SHORT_X30"]


def trades(asset, c4, above, t0, fn, lado="LONG"):
    """Operacoes de um sinal numa moeda: entrada na abertura da vela seguinte."""
    R.CTX["asset"] = asset              # como generic_trades: alguns sinais leem a moeda (maiores, momento)
    out, busy = [], -1
    for i in range(250, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if i < busy or t_sig < t0 or not R._known(t_sig, above):
            continue
        sig = fn(c4[:i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]
        if not (sig["stop"] < px < sig["tp"][0]):
            continue
        pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"], PB.FEE_PCT,
                                  PB.SLIP_PCT, breakeven=True)
        k = i + 1
        while not pos["closed"] and k < len(c4):
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H4)
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append({"asset": asset, "lado": lado, "t": int(pos["opened_at"]), "t_fim": int(pos["closed_at"]),
                    "r": round(pos["r"], 4), "stop_pct": round(abs(1 - sig["stop"] / px) * 100, 4),
                    "saida": pos["exit_reason"]})
    return out


def _sim(plan, px, t_open, bars, i0, hold_s, side):
    pos = trade.open_position(dict(plan, max_hold_s=None), px, t_open, PB.FEE_PCT, PB.SLIP_PCT,
                              breakeven=True, side=side)
    k = i0
    d = 1 if side == "LONG" else -1
    while not pos["closed"] and k < len(bars):
        x = bars[k]
        trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
        if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= hold_s:
            trade._sell(pos, pos["remaining"], x["c"] * (1 - d * pos["slip"]))
            trade._finish(pos, "TIME", x["t"] + H4)
        k += 1
    return pos, k


def trades_short(asset, real, m4, t0, fn):
    """Sinal no espelho; a mesma operacao em preco real (uma posicao por moeda,
    ocupada enquanto a operacao real estiver aberta)."""
    R.CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(m4) - 1):
        t_sig = m4[i]["t"] + H4
        if i < busy or t_sig < t0:
            continue
        sig = fn(m4[:i + 1])
        if not sig:
            continue
        pm = m4[i + 1]["o"]
        if not (sig["stop"] < pm < sig["tp"][0]):
            continue
        px = real[i + 1]["o"]
        plan = dict(sig, stop=1 / sig["stop"], tp=[1 / x for x in sig["tp"]])
        pos, k = _sim(plan, px, real[i + 1]["t"], real, i + 1, sig["hold_s"], "SHORT")
        if not pos["closed"]:
            continue
        busy = k
        out.append({"asset": asset, "lado": "SHORT", "t": int(pos["opened_at"]), "t_fim": int(pos["closed_at"]),
                    "r": round(pos["r"], 4), "stop_pct": round(abs(plan["stop"] / px - 1) * 100, 4),
                    "saida": pos["exit_reason"]})
    return out


def recolher(pasta, nomes=None, t0=INICIO):
    bars, _ = B.load_all(pasta, min_bars=1500)
    btc = bars["BTC"]
    above = R.btc_above(btc)
    R.CTX.update(btc=btc, bars=bars, funding={}, oi={}, macro={}, ls={}, rank={})
    R.CTX.pop("_amp", None)
    mbars = None
    out = {}
    for k in nomes or REPRESENTANTES:
        s = time.time()
        trs = []
        if k in R.SHORT_SIGS:
            mbars = mbars or {a: SH.mirror(c) for a, c in bars.items()}
            for a, c4 in sorted(mbars.items()):
                trs += trades_short(a, bars[a], c4, t0, R.SHORT_SIGS[k])
        else:
            for a, c4 in sorted(bars.items()):
                trs += trades(a, c4, above, t0, R.NEW_SIGS[k])
        trs.sort(key=lambda t: t["t"])
        out[k] = trs
        print(k, len(trs), round(time.time() - s), flush=True)
    return {"inicio": t0, "fim": btc[-1]["t"] + H4, "moedas": len(bars), "ops": out}


if __name__ == "__main__":
    res = recolher(sys.argv[1], sys.argv[3:] or None)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(res, f)
