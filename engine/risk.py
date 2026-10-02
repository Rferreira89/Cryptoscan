"""Risk Engine: stop, objetivos, R:R liquido de comissoes e dimensao.

O stop vem da estrutura (definido pela estrategia) e e validado contra a
volatilidade: nem tao curto que seja ruido, nem tao largo que o R:R seja
artificial. Nunca se aumenta o risco por o score ser elevado.
"""
from .strategies import px_str

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
    size_pct = min(cfg["risk_pct"] / stop_pct * 100, cfg["max_position_pct"])
    return {"entry_zone": [lo, hi], "entry_ref": entry, "stop": stop,
            "tp": tps, "tp_projected": projected,
            "rr": round(rr, 2), "rr_tp1": round(net_r(tps[0]), 2),
            "rr_tp3": round(net_r(tps[2]), 2),
            "stop_pct": round(stop_pct, 2), "stop_atr": round(dist / atr, 2),
            "position_pct": round(size_pct, 1),
            "risk_pct": round(size_pct * stop_pct / 100, 2),
            "partials": [50, 30, 20]}, None
