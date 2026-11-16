"""Oportunidades de acoes e metais preciosos para o motor central (papel).

Aproveita a lista de contratos nao-cripto da OKX (tools/okx_macro.contratos).
Gera sinais LONG e SHORT simples e classifica-os com opportunity_engine.
Nao envia ordens reais. Nao altera producao.

Regras (papel):
- LONG: fecho > SMA50 e SMA50 a subir.
- SHORT: fecho < SMA50 e SMA50 a descer.
- Score via opportunity_engine (regime + R/R + stop).
- So instrumentos que o contrato permita a direccao (X-Perp linear).
"""
import time

from . import opportunity_engine as OE
from . import regime_select


def _sma(xs, n):
    if len(xs) < n:
        return None
    return sum(xs[-n:]) / n


def sinais_macro(velas, fase=None):
    """Devolve lista de oportunidades (dict) para um instrumento.
    velas: lista de {t, c} diarias fechadas, mais recente no fim.
    """
    if not velas or len(velas) < 60:
        return []
    closes = [v["c"] for v in velas]
    m = _sma(closes, 50)
    m10 = _sma(closes[:-10], 50) if len(closes) > 60 else None
    if m is None or m10 is None:
        return []
    px = closes[-1]
    out = []
    # LONG
    if px > m and m > m10:
        stop = m * 0.98
        tp = px + 1.5 * (px - stop)
        sig = {"stop": stop, "tp": [tp], "side": "LONG", "t_sig": velas[-1]["t"]}
        sc, det = OE.score(sig, px, fase, "LONG")
        if regime_select.prefer(fase, "LONG") or sc >= 40:
            out.append({"side": "LONG", "price": px, "sig": sig, "score": sc, "detail": det})
    # SHORT
    if px < m and m < m10:
        stop = m * 1.02
        tp = px - 1.5 * (stop - px)
        sig = {"stop": stop, "tp": [tp], "side": "SHORT", "t_sig": velas[-1]["t"]}
        sc, det = OE.score(sig, px, fase, "SHORT")
        if regime_select.prefer(fase, "SHORT") or sc >= 40:
            out.append({"side": "SHORT", "price": px, "sig": sig, "score": sc, "detail": det})
    return out


def filtrar_elegiveis(contratos, xperps=None):
    """contratos: {base: instId} do okx_macro.
    xperps: set de bases com X-Perp vivo (negociaveis). None = todos informativos.
    Devolve {base: {inst, elegivel}}.
    """
    out = {}
    for base, inst in (contratos or {}).items():
        eleg = True if xperps is None else base in xperps
        out[base] = {"inst": inst, "elegivel": eleg}
    return out
