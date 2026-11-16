"""Motor experimental de oportunidades rapidas (apenas investigacao/paper).

Nao importa executores nem configuracao de producao. Recebe velas OHLCV
cronologicas e fechadas; nunca envia ordens. Sinais sao hipoteses, nao
indicacao de rentabilidade.
"""
from statistics import median

BAR_SECONDS = 1800
MIN_BARS = 60
MAX_HOLD_BARS = 8


def _ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = sum(values[:period]) / period
    for value in values[period:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


def _atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    tr = []
    for prev, cur in zip(candles[-period-1:-1], candles[-period:]):
        tr.append(max(cur["h"] - cur["l"],
                      abs(cur["h"] - prev["c"]),
                      abs(cur["l"] - prev["c"])))
    return sum(tr) / len(tr)


def classify_regime(candles):
    """Classifica contexto local usando apenas a janela recebida."""
    if len(candles) < 50:
        return "insufficient_data"
    closes = [float(c["c"]) for c in candles]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    if not e20 or not e50 or closes[-1] <= 0:
        return "insufficient_data"
    atr = _atr(candles)
    vol_pct = (atr / closes[-1] * 100) if atr else 0.0
    if vol_pct >= 3.0:
        return "high_volatility"
    if e20 > e50 * 1.002 and closes[-1] > e20:
        return "bullish"
    if e20 < e50 * 0.998 and closes[-1] < e20:
        return "bearish"
    return "range"


def detect_opportunities(candles, asset="UNKNOWN"):
    """Devolve candidatos LONG/SHORT no fecho da ultima vela.

    As regras sao deliberadamente transparentes e exploratorias. A pontuacao
    ordena candidatos, nao representa probabilidade nem edge estatistico.
    """
    if len(candles) < MIN_BARS:
        return []
    rows = candles[-max(MIN_BARS, 60):]
    close = float(rows[-1]["c"])
    atr = _atr(rows)
    if close <= 0 or not atr or atr <= 0:
        return []
    prior = rows[-21:-1]
    if len(prior) < 20:
        return []
    highs = [float(c["h"]) for c in prior]
    lows = [float(c["l"]) for c in prior]
    vols = [float(c["v"]) for c in rows[-21:-1]]
    vol_med = median(vols) if vols else 0
    current_vol = float(rows[-1]["v"])
    regime = classify_regime(rows)
    out = []

    def add(family, side, score, reason):
        entry = close
        risk = 1.5 * atr
        stop = entry - risk if side == "LONG" else entry + risk
        target = entry + 2.0 * risk if side == "LONG" else entry - 2.0 * risk
        out.append({
            "asset": asset, "family": family, "side": side,
            "signal_t": int(rows[-1]["t"]), "signal_close": entry,
            "stop": stop, "target": target, "risk_per_unit": risk,
            "max_hold_bars": MAX_HOLD_BARS, "regime": regime,
            "score": score, "reason": reason,
        })

    # Rompimento: volume confirma; avaliacao e feita no fecho, entrada na
    # abertura seguinte durante a simulacao.
    if close > max(highs) and vol_med > 0 and current_vol >= 1.5 * vol_med:
        add("volume_breakout", "LONG", 3, "fecho acima do maximo de 20 velas com volume")
    if close < min(lows) and vol_med > 0 and current_vol >= 1.5 * vol_med:
        add("volume_breakdown", "SHORT", 3, "fecho abaixo do minimo de 20 velas com volume")

    # Momentum: retorno direcional forte em 3 velas e atividade acima da mediana.
    ret3 = close / float(rows[-4]["c"]) - 1 if float(rows[-4]["c"]) else 0
    if vol_med > 0 and current_vol >= vol_med:
        if ret3 >= 0.025:
            add("momentum", "LONG", 2, "retorno positivo >=2.5% em 3 velas")
        elif ret3 <= -0.025:
            add("momentum", "SHORT", 2, "retorno negativo <=-2.5% em 3 velas")

    # Reversao simples: distancia ao extremo recente e vela de rejeicao.
    window = rows[-20:]
    lo, hi = min(float(c["l"]) for c in window), max(float(c["h"]) for c in window)
    candle = rows[-1]
    body = abs(float(candle["c"]) - float(candle["o"]))
    lower_wick = min(float(candle["o"]), float(candle["c"])) - float(candle["l"])
    upper_wick = float(candle["h"]) - max(float(candle["o"]), float(candle["c"]))
    if close <= lo * 1.01 and lower_wick > max(body, atr * 0.15):
        add("range_reversal", "LONG", 1, "rejeicao da zona inferior do range")
    if close >= hi * 0.99 and upper_wick > max(body, atr * 0.15):
        add("range_reversal", "SHORT", 1, "rejeicao da zona superior do range")
    return out


def simulate_candidate(candles, signal_index, candidate, fee_pct=0.1,
                       slippage_pct=0.05, funding_pct=0.0,
                       max_hold_bars=MAX_HOLD_BARS):
    """Simula entrada na vela seguinte; stop prevalece se stop e alvo tocarem
    na mesma vela. Custos percentuais sao cobrados sobre o nocional.
    """
    if signal_index < 0 or signal_index + 1 >= len(candles):
        return {"status": "NO_NEXT_BAR"}
    side = candidate["side"]
    if side not in ("LONG", "SHORT"):
        return {"status": "INVALID_SIDE"}
    direction = 1.0 if side == "LONG" else -1.0
    next_bar = candles[signal_index + 1]
    raw_entry = float(next_bar["o"])
    if raw_entry <= 0:
        return {"status": "INVALID_PRICE"}
    entry = raw_entry * (1 + slippage_pct / 100 * direction)
    stop, target = float(candidate["stop"]), float(candidate["target"])
    risk = abs(entry - stop)
    if risk <= 0:
        return {"status": "INVALID_RISK"}
    exit_price, reason, exit_index = None, None, None
    horizon_end = signal_index + max(1, min(max_hold_bars, MAX_HOLD_BARS))
    last_index = min(len(candles) - 1, horizon_end)
    for j in range(signal_index + 1, last_index + 1):
        bar = candles[j]
        if side == "LONG":
            stop_hit, target_hit = float(bar["l"]) <= stop, float(bar["h"]) >= target
        else:
            stop_hit, target_hit = float(bar["h"]) >= stop, float(bar["l"]) <= target
        if stop_hit:  # conservador: stop primeiro se ambos forem tocados
            exit_price, reason, exit_index = stop, "STOP", j
            break
        if target_hit:
            exit_price, reason, exit_index = target, "TARGET", j
            break
    if exit_price is None and last_index < horizon_end:
        return {"status": "OPEN_AT_END"}
    if exit_price is None:
        exit_index = last_index
        exit_price, reason = float(candles[last_index]["c"]), "TIME_EXIT"
    exit_fill = exit_price * (1 - slippage_pct / 100 * direction)
    gross = direction * (exit_fill - entry) / risk
    cost_pct = (2 * fee_pct) + max(0.0, funding_pct)  # slippage ja refletido nos fills
    costs_r = (entry * cost_pct / 100) / risk
    return {
        "status": "CLOSED", "side": side, "family": candidate.get("family"),
        "entry_index": signal_index + 1, "exit_index": exit_index,
        "entry": entry, "exit": exit_fill, "exit_reason": reason,
        "gross_r": gross, "costs_r": costs_r, "net_r": gross - costs_r,
        "bars_held": exit_index - signal_index,
        "entry_t": int(candles[signal_index + 1]["t"]),
        "exit_t": int(candles[exit_index]["t"]),
    }



def evaluate_trades(results, min_trades=100, bootstrap_samples=2000, seed=7):
    """Resumo descritivo e IC bootstrap da media de R liquido.

    O IC nao corrige data snooping/hipoteses multiplas; a aprovacao exige
    walk-forward, periodo intocado e correcao Holm fora desta funcao.
    """
    import random

    rows = [r for r in results if r.get("status") == "CLOSED"
            and isinstance(r.get("net_r"), (int, float))]
    values = [float(r["net_r"]) for r in rows]
    n = len(values)
    if not n:
        return {"trades": 0, "adequate_sample": False,
                "mean_net_r": None, "ci95_mean_net_r": None,
                "profit_factor": None, "win_rate": None, "max_drawdown_r": None}
    wins = sum(x > 0 for x in values)
    gross_win = sum(x for x in values if x > 0)
    gross_loss = abs(sum(x for x in values if x < 0))
    pf = (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win else None)
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    rng = random.Random(seed)
    means = []
    if bootstrap_samples > 0:
        for _ in range(bootstrap_samples):
            means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    ci = None
    if means:
        ci = [means[int(0.025 * (len(means) - 1))],
              means[int(0.975 * (len(means) - 1))]]
    return {
        "trades": n, "adequate_sample": n >= min_trades,
        "mean_net_r": sum(values) / n,
        "ci95_mean_net_r": ci,
        "profit_factor": pf,
        "win_rate": wins / n,
        "max_drawdown_r": drawdown,
        "positive_mean_ci": bool(ci and ci[0] > 0),
        "warning": "descritivo; nao substitui walk-forward nem correcao de hipoteses multiplas",
    }
