"""Shorts (venda a descoberto em margem spot) como ESPELHO das compras.

Um short no preco P e uma compra no preco invertido 1/P: um maximo passa a
minimo, uma quebra em baixa passa a quebra em alta. Assim as estrategias,
a estrutura, a liquidez e a confluencia sao exatamente as mesmas das
compras, sem uma segunda versao do codigo que pudesse divergir.

A analise corre sobre as velas invertidas; o plano e depois convertido
para precos reais e o risco, o R:R e a dimensao sao recalculados no espaco
real (o espelho so decide SE ha setup, nao quanto se arrisca).

Um short tem perda teoricamente ilimitada e paga juros pela moeda
emprestada. Nenhuma estrategia de short esta validada.
"""
from . import risk

SUFFIX = "_SHORT"
LABEL = {"PULLBACK": "retoma da descida depois de um ressalto",
         "BREAKOUT": "quebra em baixa com reteste",
         "LIQUIDITY_SWEEP": "sweep de topos com rejeição",
         "RANGE": "topo de range"}


def mirror(c):
    """Velas invertidas (1/preco). O volume comprador passa a vendedor."""
    return [{"t": x["t"], "o": 1 / x["o"], "h": 1 / x["l"], "l": 1 / x["h"],
             "c": 1 / x["c"], "v": x["v"],
             "tb": (x["v"] - x["tb"]) if x.get("tb") is not None else None}
            for x in c]


def real_plan(pm, cfg, lev_use=None):
    """Converte um plano do espelho num plano real de short.
    Devolve (plano, None) ou (None, motivo)."""
    fee = cfg["fee_pct"] / 100
    lo_m, hi_m = sorted(pm["entry_zone"])
    zone = [1 / hi_m, 1 / lo_m]                    # crescente, precos reais
    entry = zone[0]                                # pior preco para quem vende
    stop = 1 / pm["stop"]
    tp = [1 / x for x in pm["tp"]]                 # decrescente
    if not (stop > zone[1] and tp[0] < entry):
        return None, "plano de short incoerente"
    dist = stop - entry
    risk_unit = dist + fee * (entry + stop)
    net_r = lambda x: (entry - x - fee * (entry + x)) / risk_unit
    rr = net_r(tp[1])
    if net_r(tp[0]) < 1.0 - 1e-6 or rr < cfg["min_rr"] - 0.05:
        return None, f"POOR R:R no short: {rr:.2f}"
    stop_pct = risk_unit / entry * 100
    c = dict(cfg)
    if lev_use is not None:
        c["swing_leverage"] = lev_use
    sz, why = risk.sizing(stop_pct, dist / entry, entry, c, short=True)
    if sz is None:
        return None, why
    lev = sz["leverage"]
    lev["reason"] = (pm.get("leverage") or {}).get("reason")
    return {"side": "SHORT", "leverage": lev, **sz["usdc"],
            "entry_zone": zone, "entry_ref": entry, "stop": stop, "tp": tp,
            "tp_projected": pm.get("tp_projected", []),
            "rr": round(rr, 2), "rr_tp1": round(net_r(tp[0]), 2),
            "rr_tp3": round(net_r(tp[2]), 2),
            "stop_pct": round(stop_pct, 2), "stop_atr": pm.get("stop_atr"),
            "position_pct": round(sz["size_pct"], 1),
            "risk_pct": round(sz["size_pct"] * stop_pct / 100, 2),
            "partials": sz["partials"]}, None


def texts(base, state, zone, px_str):
    """Gatilho e contexto em precos reais (o espelho so tem os invertidos)."""
    what = LABEL.get(base, base)
    if state == "READY":
        return (f"vela de 4H confirmou: {what}",
                [f"espelho de descida da estratégia {base}: {what}"])
    return (f"confirmação por fecho de 4H abaixo de {px_str(zone[0])}, com "
            f"entrada entre {px_str(zone[0])} e {px_str(zone[1])}",
            [f"espelho de descida da estratégia {base}: {what}"])
