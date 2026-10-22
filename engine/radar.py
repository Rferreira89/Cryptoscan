"""Radar de quebras (22/10, pedido do Rui: "ha alguma oportunidade a chegar?").

Mostra as moedas mais perto do gatilho dos lutadores de rompimento, com as
mesmas contas do sinal (tools/arena_ringue.sig_turtle):
  - Ramiro (SHORT_TURTLE): fecho de 4H abaixo do minimo dos 20 dias completos
    antes do ultimo, vindo de cima;
  - Teodoro (TURTLE_FORTES, so papel e so na subida): fecho acima do maximo de 20 dias.
So informa: nao gera sinais nem mexe em dinheiro.
"""
from . import backtest as B

DAY, H4 = 86400, 14400
MAX = 10


def niveis(c4):
    """(minimo, maximo) de 20 dias como no sinal, ou None."""
    if not c4 or len(c4) < 150:
        return None
    d = [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]
    if len(d) < 25:
        return None
    w = d[-21:-1]
    return min(x["l"] for x in w), max(x["h"] for x in w)


def calcular(rows, c4s, now, fase=None):
    out = {"quebras": [], "rompimentos": [], "proximo_fecho": None}
    for r in rows or []:
        a, c4, px = r.get("asset"), (c4s or {}).get(r.get("asset")), r.get("price")
        if a == "BTC" or not px or not c4:
            continue
        nv = niveis(c4)
        if not nv:
            continue
        lo, hi = nv
        ult = c4[-1]["c"]
        fecho = c4[-1]["t"] + 2 * H4
        out["proximo_fecho"] = max(out["proximo_fecho"] or 0, fecho)
        ok_venue = not (r.get("excluded_for") or [])
        d_lo = (px / lo - 1) * 100
        if d_lo < 8:
            estado = ("já quebrou antes (sem sinal)" if ult < lo else
                      "abaixo do mínimo: sinal se fechar assim" if px < lo else "a aproximar-se")
            out["quebras"].append({"asset": a, "preco": px, "nivel": lo, "dist_pct": round(d_lo, 2),
                                   "estado": estado, "fecho": fecho, "ok": ok_venue})
        d_hi = (hi / px - 1) * 100
        if d_hi < 8:
            estado = ("já rompeu antes (sem sinal)" if ult > hi else
                      "acima do máximo: sinal se fechar assim" if px > hi else "a aproximar-se")
            out["rompimentos"].append({"asset": a, "preco": px, "nivel": hi, "dist_pct": round(d_hi, 2),
                                       "estado": estado, "fecho": fecho, "ok": ok_venue,
                                       "ativo": fase == "subida"})
    rank = lambda x: (x["estado"].startswith("já"), x["dist_pct"])
    out["quebras"] = sorted(out["quebras"], key=rank)[:MAX]
    out["rompimentos"] = sorted(out["rompimentos"], key=rank)[:MAX]
    return out
