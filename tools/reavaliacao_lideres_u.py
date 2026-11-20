"""Fila do Rui, hipotese 6 (2026-11-20): os lideres da arena contra o acaso
incondicional.

As regras nao mudam: as operacoes sao as do ringue (AR.generic_trades, com as
funcoes exatas da arena). So muda o juiz, com as funcoes da afinacao H18:
  S  atual (arena.control_rs, +-90 velas a volta do sinal)
  F  so para a frente (i+1 .. i+90)
  U  incondicional (qualquer vela da moeda dentro da janela avaliada)
Pre-registo em backtest/investigacao.md (2026-11-20, tarde).

Uso: python -m tools.reavaliacao_lideres_u <pasta_history> <saida.json>
"""
import json
import sys

from engine import backtest as B
from tools import afinacao_h18_controlo as H18
from tools import arena_ringue as AR

DAY, H4 = AR.DAY, AR.H4
RES_DIAS = 182
DES_DIAS = 548
NMIN = 20
# chave: (funcao, usa o filtro do BTC acima da SMA200)
LIDERES = {
    "BOUNCE_AMPLITUDE": (AR.sig_amplitude, True),
    "CAP_MERCADO_V2_N5K2": (AR.sig_cap_mercado_v2(5, 2.0), False),
    "BOUNCE_ALVO": (AR.sig_bounce_alvo(30, 2.0, 1.0), True),
}
INFORMATIVOS = {"CAP_MERCADO_V2_N5K2_COM_FILTRO": (AR.sig_cap_mercado_v2(5, 2.0), True)}


def janelas(end):
    r0 = end - RES_DIAS * DAY
    return {"reserva": (r0, end), "desenho": (r0 - DES_DIAS * DAY, r0),
            "antigo": (H18.B_START, H18.B_END)}


def operacoes(fn, filtro, bars, above, t0):
    """Operacoes do ringue (so velas fechadas: generic_trades passa c4[:i+1])."""
    flt = above if filtro else {k: True for k in above}
    out = []
    for a in sorted(bars):
        if a == "BTC":
            continue
        out += [t for _, t in AR.generic_trades(a, bars[a], flt, t0, "X", H18.cauda(fn))]
    return sorted(out, key=lambda t: t["t"])


def decide(j, nmin=NMIN):
    if j.get("n", 0) < nmin:
        return "AMOSTRA INSUFICIENTE"
    if j.get("acaso_p95") is None:
        return "SEM CONTROLO"
    return "MANTEM" if j["avg_r"] > 0 and j["avg_r"] > j["acaso_p95"] else "PERDE"


def main(folder, dest):
    bars, _ = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    AR.CTX.pop("_amp", None)
    end = max(x["t"] for x in btc) + H4
    above = AR.btc_above(btc)
    jan = janelas(end)
    res = {"moedas": len(bars), "fim": end, "janelas": jan, "lideres": {}}
    for key, (fn, filtro) in {**LIDERES, **INFORMATIVOS}.items():
        trs = operacoes(fn, filtro, bars, above, H18.B_START)
        r = res["lideres"][key] = {"filtro_btc": filtro}
        for w, (w0, w1) in jan.items():
            sub = [t for t in trs if w0 <= t["t"] < w1]
            r[w] = {m: H18.julgar(sub, bars, m, w0, w1) for m in "SFU"}
            if sub:
                r[w]["acerto"] = round(sum(t["r"] > 0 for t in sub) / len(sub), 3)
            print(key, w, json.dumps(r[w]), flush=True)
        r["veredicto"] = {m: decide(r["reserva"][m]) for m in "SFU"}
        print(key, "veredicto", r["veredicto"], flush=True)
    json.dump(res, open(dest, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
