"""SHORT_SOBRECOMPRA_X70V25 — research 2026-11-16: R medio +0.044, p99.1 -> PARA PAPEL.

Regista o sinal em arena_ringue.SINAIS e estende PAPEL_ESTUDO sem reescrever
o ficheiro grande. Chamado por engine/paper_ring.update.
"""
NAME = "SHORT_SOBRECOMPRA_X70V25"
X, V = 70, 2.5
_DONE = False


def _sig_m(m4):
    """Sinal no espelho (short_live converte para precos reais)."""
    from tools import arena_ringue as AR
    from tools import research_rlib as RL
    if len(m4) < 60:
        return None
    closes = [b["c"] for b in m4]
    rs = RL.rsi(closes)
    at = RL.atr(m4)
    i = len(m4) - 1
    if rs[i] is None or at[i] is None or rs[i - 1] is None:
        return None
    thr = 100 - X
    window_rs = [rs[j] for j in range(i - 2, i + 1) if rs[j] is not None]
    if not window_rs or min(window_rs) >= thr:
        return None
    if not (m4[i]["c"] > m4[i - 1]["h"] and rs[i] > rs[i - 1]):
        return None
    vavg = sum(m4[j]["v"] for j in range(i - 20, i)) / 20.0
    if vavg <= 0 or m4[i]["v"] < V * vavg:
        return None
    lo = min(m4[j]["l"] for j in range(i - 5, i + 1)) - 0.1 * at[i]
    stop = min(lo, m4[i]["c"] - 1.25 * at[i])
    if stop <= 0:
        return None
    ma20 = sum(closes[i - 19:i + 1]) / 20.0
    hi42 = max(m4[j]["h"] for j in range(max(0, i - 41), i + 1))
    hold = 5 * AR.DAY
    if ma20 > m4[i]["c"] * 1.01:
        two = hi42 > ma20 * 1.005
        return {"stop": stop, "tp": [ma20, hi42] if two else [ma20],
                "partials": [50, 50] if two else [100], "breakeven": True,
                "hold_s": hold, "atr": at[i], "rank": float(rs[i]),
                "gatilho": f"sobrecompra RSI>{X} vol {m4[i]['v']/vavg:.1f}x"}
    return {"stop": stop, "tp": [m4[i]["c"] + 2 * (m4[i]["c"] - stop)],
            "partials": [100], "breakeven": True, "hold_s": hold, "atr": at[i],
            "rank": float(rs[i]),
            "gatilho": f"sobrecompra RSI>{X} vol {m4[i]['v']/vavg:.1f}x"}


def ensure():
    """Regista NAME em SINAIS (short_live) e devolve metadados para papel."""
    global _DONE
    from tools import arena_ringue as AR
    if NAME not in AR.SINAIS:
        AR.SINAIS[NAME] = AR.short_live(_sig_m)
    _DONE = True
    return {
        "name": NAME,
        "papel_fase": None,
        "n_min": 25,
    }
