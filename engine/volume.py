"""Volume Engine + Order Flow (fluxo executado).

O delta vem do volume comprador agressor reportado nas velas (campo tb),
ou seja, de negocios executados - nao de ordens passivas no livro.
Anti-redundancia: OBV e CVD medem a mesma coisa (fluxo). Se ha CVD, o OBV
nao e calculado; o OBV so serve de recurso quando nao ha dados de agressor.
"""
from . import indicators as I

N = 20


def analyse(c):
    if len(c) < N + 15:
        return None
    vols = [x["v"] for x in c]
    base = sum(vols[-N - 1:-1]) / N
    last = c[-1]
    atr = I.atr(c)[-1]
    out = {"rvol": round(last["v"] / base, 2) if base > 0 else None,
           "flow_source": None, "buy_share": None, "flow_20": None,
           "divergence": None, "labels": []}
    rv = out["rvol"]
    if rv is not None:
        if rv >= 1.5:
            out["labels"].append("VOLUME_EXPANSION")
        elif rv <= 0.6:
            out["labels"].append("VOLUME_CONTRACTION")
        # muito volume e pouca deslocacao: possivel absorcao (a confirmar)
        if rv >= 1.5 and atr and (last["h"] - last["l"]) <= 0.7 * atr:
            out["labels"].append("POSSIBLE_ABSORPTION")

    win = c[-N:]
    tot = sum(x["v"] for x in win)
    has_tb = all(x.get("tb") is not None and 0 <= x["tb"] <= x["v"] * 1.0001
                 for x in win)
    if has_tb and tot > 0:
        out["flow_source"] = "CVD"
        if last["v"] > 0:
            out["buy_share"] = round(last["tb"] / last["v"], 3)
        # delta acumulado em N velas, normalizado pelo volume: [-1, 1]
        flow = sum(2 * x["tb"] - x["v"] for x in win) / tot
    elif tot > 0:
        out["flow_source"] = "OBV"
        obv = 0.0
        for a, b in zip(c[-N - 1:], c[-N:]):
            obv += b["v"] if b["c"] > a["c"] else -b["v"] if b["c"] < a["c"] else 0
        flow = obv / tot
    else:
        return out
    out["flow_20"] = round(flow, 3)
    move = c[-1]["c"] - c[-N]["c"]
    if atr and abs(move) > atr:
        thr = 0.03 if out["flow_source"] == "CVD" else 0.15
        if move > 0 and flow < -thr:
            out["divergence"] = "BEARISH"   # preco sobe com fluxo vendedor
        elif move < 0 and flow > thr:
            out["divergence"] = "BULLISH"   # preco desce com fluxo comprador
    return out
