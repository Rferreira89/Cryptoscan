"""Esqueleto de sinais — ATAQUE_1H (long/short) e SHORT_SOBRECOMPRA.
Pré-registo 2026-11-15. NÃO activar em SINAIS/PAPEL_ESTUDO antes de validação
no research (percentil >= 90 fora da amostra).

Uso futuro: importar em tools/arena_ringue e registar em NEW_SIGS / SHORT_SIGS
com os parâmetros da combinação vencedora.

Venues: Bybit e OKX — a função de sinal é a mesma; a execução fica no motor
por venue.
"""
from engine import paper_bounce as PB
from engine import backtest as B

H1 = 3600
H4 = B.H4
DAY = B.DAY
MIN_STOP_PCT = 0.012  # 1,2% — custos ~0,7% ida e volta


def _ema(series, n):
    if len(series) < n:
        return None
    k = 2 / (n + 1)
    e = series[0]
    for x in series[1:]:
        e = k * x + (1 - k) * e
    return e


def _rsi(closes, n=14):
    return PB.rsi(closes, n) if hasattr(PB, "rsi") else PB.rsi(closes)


def _atr(bars, n=14):
    return PB.atr(bars)


def _ema20_50_4h(c4):
    """(ema20, ema50) no fecho da última vela 4H, ou (None, None)."""
    if len(c4) < 60:
        return None, None
    c = [x["c"] for x in c4]
    return _ema(c[-60:], 20), _ema(c[-60:], 50)


def sig_ataque_1h_long(c1, c4=None, k_r=1.5, hold_h=12):
    """ATAQUE_1H long. c1 = velas 1H fechadas; c4 opcional para contexto.
    Devolve plano parcial (stop/tp em preço absolutos só com px de entrada no motor).
    """
    if not c1 or len(c1) < 30:
        return None
    if c4:
        e20, e50 = _ema20_50_4h(c4)
        if e20 is None or e50 is None or not (e20 > e50 and c4[-1]["c"] > e50):
            return None
    i = len(c1) - 1
    closes = [x["c"] for x in c1]
    rs = _rsi(closes)
    at = _atr(c1)
    if rs is None or at is None or at[i] is None or rs[i] is None:
        return None
    ema20 = _ema(closes[max(0, i - 40):i + 1], 20)
    if ema20 is None:
        return None
    b = c1[i]
    if not (b["l"] <= ema20 and b["c"] > ema20):
        return None
    if not (35 <= rs[i] <= 55):
        return None
    stop = min(x["l"] for x in c1[i - 2:i + 1]) - 0.2 * at[i]
    # distância mínima verificada no motor com px de entrada; aqui devolvemos stop
    if stop <= 0:
        return None
    return {
        "stop": stop,
        "tp_r": k_r,
        "partials": [100],
        "breakeven": False,
        "hold_s": hold_h * 3600,
        "side": "LONG",
        "min_stop_pct": MIN_STOP_PCT,
        "tf": "1h",
        "gatilho": f"ATAQUE_1H long k={k_r} H={hold_h}h",
    }


def sig_ataque_1h_short(c1, c4=None, k_r=1.5, hold_h=12):
    """ATAQUE_1H short — espelho do long."""
    if not c1 or len(c1) < 30:
        return None
    if c4:
        e20, e50 = _ema20_50_4h(c4)
        if e20 is None or e50 is None or not (e20 < e50 and c4[-1]["c"] < e50):
            return None
    i = len(c1) - 1
    closes = [x["c"] for x in c1]
    rs = _rsi(closes)
    at = _atr(c1)
    if rs is None or at is None or at[i] is None or rs[i] is None:
        return None
    ema20 = _ema(closes[max(0, i - 40):i + 1], 20)
    if ema20 is None:
        return None
    b = c1[i]
    if not (b["h"] >= ema20 and b["c"] < ema20):
        return None
    if not (45 <= rs[i] <= 65):
        return None
    stop = max(x["h"] for x in c1[i - 2:i + 1]) + 0.2 * at[i]
    return {
        "stop": stop,
        "tp_r": k_r,
        "partials": [100],
        "breakeven": False,
        "hold_s": hold_h * 3600,
        "side": "SHORT",
        "min_stop_pct": MIN_STOP_PCT,
        "tf": "1h",
        "gatilho": f"ATAQUE_1H short k={k_r} H={hold_h}h",
    }


def sig_short_sobrecompra(c4, x=70, v=2.0):
    """SHORT_SOBRECOMPRA 4H — esqueleto. Activar só após research >= p90."""
    if not c4 or len(c4) < 60:
        return None
    i = len(c4) - 1
    c = [x["c"] for x in c4]
    rs = _rsi(c)
    at = _atr(c4)
    if rs is None or at is None or at[i] is None:
        return None
    if min(rs[i - 2:i + 1]) is None or max(rs[i - 2:i + 1]) < x:
        return None
    if not (c[i] < c4[i - 1]["l"] and rs[i] < rs[i - 1]):
        return None
    vavg = sum(y["v"] for y in c4[i - 20:i]) / 20
    if vavg <= 0 or c4[i]["v"] < v * vavg:
        return None
    stop = max(x["h"] for x in c4[i - 5:i + 1]) + 0.1 * at[i]
    ma20 = sum(c[i - 19:i + 1]) / 20
    lo42 = min(x["l"] for x in c4[max(0, i - 41):i + 1])
    return {
        "stop": stop,
        "tp": [ma20, lo42] if lo42 < ma20 * 0.995 else [ma20],
        "partials": [50, 50] if lo42 < ma20 * 0.995 else [100],
        "breakeven": True,
        "hold_s": 5 * DAY,
        "side": "SHORT",
        "gatilho": f"SHORT_SOBRECOMPRA RSI>{x} vol>={v}x",
    }
