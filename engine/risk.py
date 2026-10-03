"""Risk Engine: stop, objetivos, R:R liquido de comissoes e dimensao.

O stop vem da estrutura (definido pela estrategia) e e validado contra a
volatilidade: nem tao curto que seja ruido, nem tao largo que o R:R seja
artificial. Nunca se aumenta o risco por o score ser elevado.
"""
import math

from .strategies import px_str

MAX_LEVERAGE = 6.0              # teto absoluto (decisao do utilizador)
MMR = 0.05                      # margem de manutencao assumida

MIN_STOP_ATR, MAX_STOP_ATR = 0.8, 4.0


def _levels_above(a4, a1):
    lv = []
    for a in (a4, a1):
        lq = a.get("liquidity") or {}
        lv += lq.get("pools_above", [])
        if lq.get("fvg_above"):
            lv.append(lq["fvg_above"][0])
        if a.get("swing_high"):
            lv.append(a["swing_high"])
    return sorted(set(lv))


def leverage_for(stop_frac, cfg):
    """Alavancagem a usar e maximo seguro para uma distancia de stop.

    Maximo seguro: a liquidacao estimada (1/L menos margem de manutencao)
    fica a pelo menos 2.5 vezes a distancia do stop. Teto absoluto de 6x.
    """
    max_safe = max(1.0, min(MAX_LEVERAGE, math.floor(2 / (2.5 * stop_frac + MMR)) / 2))
    use = max(1.0, min(cfg.get("swing_leverage", 1.0), max_safe))
    return {"use": use, "max_safe": max_safe, "needed": 1.0}


def sizing(stop_pct, stop_frac, entry, cfg, short=False):
    """Dimensao, alavancagem, valores em USDC e esquema de saidas.
    Devolve (dict, None) ou (None, motivo)."""
    lev = leverage_for(stop_frac, cfg)
    # com alavancagem L a posicao e o risco sao L vezes maiores; o capital
    # proprio em jogo (colateral) fica dentro do teto por posicao
    size_pct = min(cfg["risk_pct"] * lev["use"] / stop_pct * 100,
                   cfg["max_position_pct"] * lev["use"])

    def lev_fields():
        if lev["use"] <= 1:
            liq = None
        elif short:                      # short liquida com a subida
            liq = entry * (1 + 1 / lev["use"] - MMR)
        else:
            liq = entry * (1 - 1 / lev["use"] + MMR)
        return dict(lev, collateral_pct=round(size_pct / lev["use"], 1),
                    borrowed_pct=round(size_pct - size_pct / lev["use"], 1),
                    liquidation_est=liq)

    partials, usdc = [50, 30, 20], {}
    cap = cfg.get("capital_usdc")
    fixed = cfg.get("fixed_position_usdc")
    if cap and fixed:
        # posicao fixa: o risco e o que a distancia do stop ditar. Com um
        # stop largo a posicao encolhe ate o risco caber em max_risk_usdc
        # (decisao do utilizador, 2026-10-03), em vez de recusar o sinal.
        # margem propria fixa (fixed) vezes a alavancagem permitida pelo
        # stop; a posicao encolhe ate o risco caber em max_risk_usdc. Assim
        # a alavancagem real e tanto maior quanto mais apertado o stop, e
        # a perda no stop nunca passa do limite.
        max_risk = cfg.get("max_risk_usdc", float("inf"))
        pos = min(fixed * lev["use"], cap * lev["use"],
                  max_risk / (stop_pct / 100))
        eff = max(1.0, round(pos / fixed, 2))
        lev = dict(lev, use=min(lev["use"], eff))
        size_pct = pos / cap * 100
    if cap:
        pos_usdc = cap * size_pct / 100
        mn = cfg.get("min_order_usdc", 5.0)
        if 0.9 * mn <= pos_usdc < mn and not (
                fixed and mn * stop_pct / 100
                > cfg.get("max_risk_usdc", float("inf")) + 1e-9):
            # a centimos do minimo: arredonda para a ordem minima (o risco
            # sobe no maximo 10% do seu valor, p. ex. de 0.50% para 0.55%)
            size_pct = mn / cap * 100
            pos_usdc = mn
        if pos_usdc < mn:
            return None, (f"posição de {pos_usdc:.2f} USDC abaixo da ordem "
                          f"mínima de {mn:g} USDC com o capital atual")
        # saidas parciais so quando cada parte e executavel na corretora
        if 0.2 * pos_usdc >= mn:
            partials = [50, 30, 20]
        elif 0.5 * pos_usdc >= mn:
            partials = [50, 50, 0]
        else:
            partials = [0, 100, 0]
        usdc = {"position_usdc": round(pos_usdc, 2),
                "collateral_usdc": round(pos_usdc / lev["use"], 2),
                "borrowed_usdc": round(pos_usdc - pos_usdc / lev["use"], 2),
                "risk_usdc": round(pos_usdc * stop_pct / 100, 2)}
    return {"leverage": lev_fields(), "usdc": usdc, "size_pct": size_pct,
            "partials": partials}, None


def plan(setup, a4, a1, cfg):
    """Devolve (plano, None) ou (None, motivo)."""
    fee = cfg["fee_pct"] / 100
    atr = a4["atr"]
    lo, hi = sorted(setup["entry"])
    entry, stop = hi, setup["stop"]          # pior preco da zona: conservador
    if stop <= 0 or stop >= lo:
        return None, "stop inválido face a zona de entrada"
    dist = entry - stop
    if dist < MIN_STOP_ATR * atr:
        return None, f"stop demasiado curto ({dist / atr:.1f} ATR): ruído"
    if dist > MAX_STOP_ATR * atr:
        return None, f"stop demasiado largo ({dist / atr:.1f} ATR)"
    risk_unit = dist + fee * (entry + stop)   # perda por unidade com comissoes

    def net_r(tp):
        return (tp - entry - fee * (tp + entry)) / risk_unit

    levels = [x for x in (setup.get("targets") or _levels_above(a4, a1))
              if x > entry]
    if levels and net_r(levels[0]) < 1.0:
        return None, (f"POOR R:R: resistência em {px_str(levels[0])} a menos de "
                      "1R da entrada")
    tps, projected = [], []
    for need in (1.0, cfg["min_rr"], cfg["min_rr"] + 1.0):
        floor = tps[-1] if tps else entry
        cand = next((x for x in levels if net_r(x) >= need and x > floor), None)
        if cand is None:                     # sem nivel estrutural: projecao
            if tps:                          # sempre para la do TP anterior
                need = max(need, net_r(floor) + 1.0)
            cand = (need * risk_unit + entry * (1 + fee)) / (1 - fee)
            projected.append(len(tps) + 1)
        tps.append(cand)
    rr = net_r(tps[1])
    if rr < cfg["min_rr"] - 1e-9:
        return None, f"POOR R:R: {rr:.2f} abaixo do mínimo {cfg['min_rr']}"
    stop_pct = risk_unit / entry * 100
    sz, why = sizing(stop_pct, dist / entry, entry, cfg)
    if sz is None:
        return None, why
    leverage, usdc, size_pct, partials = (sz["leverage"], sz["usdc"],
                                          sz["size_pct"], sz["partials"])
    return {"leverage": leverage, **usdc,
            "entry_zone": [lo, hi], "entry_ref": entry, "stop": stop,
            "tp": tps, "tp_projected": projected,
            "rr": round(rr, 2), "rr_tp1": round(net_r(tps[0]), 2),
            "rr_tp3": round(net_r(tps[2]), 2),
            "stop_pct": round(stop_pct, 2), "stop_atr": round(dist / atr, 2),
            "position_pct": round(size_pct, 1),
            "risk_pct": round(size_pct * stop_pct / 100, 2),
            "partials": partials}, None
