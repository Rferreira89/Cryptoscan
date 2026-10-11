"""Papel ao vivo do OVERSOLD BOUNCE no 4H (decisao do Rui, 2026-10-11).

ATENCAO: NAO validada (investigacao 2026-10-11: falha 4 de 7 criterios). O
gatilho foi o primeiro a bater o acaso nos momentos de entrada (percentil
99,5), mas a saida original so empatava. Corre so em papel, para juntar
dados NOVOS (fora de qualquer teste) antes de qualquer decisao. Nunca gera
ordens reais nem ocupa vagas das operacoes reais.

O mesmo gatilho e seguido em paralelo com quatro formas de sair (as da
hipotese 3 da fila do Rui, escritas antes de qualquer teste):
  G0  original: stop no minimo da queda (>= 1,25 ATR), 50% na media de 20
      velas, resto no maximo de 7 dias, stop na entrada depois do 1.o,
      saida ao fim de 3 dias  (configuracao X=25, H=3 da investigacao)
  V1  saida do sistema ao vivo: o plano de engine/risk.py (objetivos em
      niveis reais, minimo 1R) com o stop do gatilho; ate 30 dias
  V2  stop curto: fecho - 1,5 ATR; um objetivo a 2R; sem stop na entrada;
      saida ao fim de 3 dias
  V3  stop original; um objetivo a 2R; sem stop na entrada; 3 dias
So a G0 envia mensagens (marcadas PAPEL). As outras ficam so registadas.

Regras do gatilho (iguais a tools/research_bounce.py, X=25): BTC acima da
SMA200 diaria; RSI14 de 4H abaixo de 25 numa das ultimas 3 velas fechadas;
a ultima vela fechada fecha acima do maximo da anterior com o RSI a subir;
sem operacao se a media de 20 velas ficar a menos de 1% acima do fecho.
Entrada ao preco do scan logo a seguir ao fecho da vela (aproxima a
abertura seguinte). Stops e objetivos sao verificados vela a vela de 4H,
como na investigacao. Ate 4 posicoes por forma de sair, uma por moeda,
25% cada; com mais sinais do que vagas, primeiro o RSI mais baixo.
"""
from . import risk, trade

TF = 14400
DAY = 86400
X, LOW_BARS, HIGH_BARS, MIN_ATR, MIN_TP1 = 25, 6, 42, 1.25, 0.01
MAX_POS, FRAC = 4, 0.25
FEE_PCT, SLIP_PCT = 0.25, 0.1
GEOS = {"G0": {"hold": 3 * DAY, "name": "original"},
        "V1": {"hold": 30 * DAY, "name": "saída do sistema ao vivo"},
        "V2": {"hold": 3 * DAY, "name": "stop 1,5 ATR, objetivo 2R"},
        "V3": {"hold": 3 * DAY, "name": "stop original, objetivo 2R"}}
RECORD = "⚠️ Não validada: só papel, não é para executar."


# ---------- indicadores (iguais a tools/research_rlib.py) ----------

def sma(xs, n):
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    g = sum(max(c[i] - c[i - 1], 0) for i in range(1, n + 1)) / n
    l = sum(max(c[i - 1] - c[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def atr(bars, n=14):
    out = [None] * len(bars)
    if len(bars) <= n:
        return out
    tr = [bars[0]["h"] - bars[0]["l"]] + [
        max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - bars[i - 1]["c"]),
            abs(bars[i]["l"] - bars[i - 1]["c"])) for i in range(1, len(bars))]
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(bars)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def signal(c4):
    """Sinal na ULTIMA vela fechada de c4 (so velas fechadas), ou None."""
    i = len(c4) - 1
    if i < HIGH_BARS + 1:
        return None
    c = [x["c"] for x in c4]
    rs, at, ma = rsi(c), atr(c4), sma(c, 20)
    if rs[i - 2] is None or at[i] is None or ma[i] is None:
        return None
    lowest = min(rs[i - 2:i + 1])
    if lowest >= X or not (c[i] > c4[i - 1]["h"] and rs[i] > rs[i - 1]):
        return None
    tp1 = ma[i]
    if tp1 < c[i] * (1 + MIN_TP1):
        return None
    stop = min(min(x["l"] for x in c4[i - LOW_BARS + 1:i + 1]) - 0.1 * at[i],
               c[i] - MIN_ATR * at[i])
    if stop <= 0:
        return None
    tp2 = max(x["h"] for x in c4[i - HIGH_BARS:i])
    two = tp2 >= tp1 * 1.005
    return {"t": c4[i]["t"] + TF, "close": c[i], "atr": at[i], "rsi": lowest,
            "stop": stop, "tp": [tp1, tp2] if two else [tp1],
            "partials": [50, 50] if two else [100]}


def plans(sig, px, a4=None, a1=None, cfg=None):
    """{geometria: plano} validos ao preco de entrada px."""
    out = {}
    if px <= sig["stop"] or px >= sig["tp"][0]:
        return out
    out["G0"] = {"stop": sig["stop"], "tp": list(sig["tp"]),
                 "partials": list(sig["partials"]), "breakeven": True}
    out["V3"] = {"stop": sig["stop"], "tp": [px + 2 * (px - sig["stop"])],
                 "partials": [100], "breakeven": False}
    s2 = sig["close"] - 1.5 * sig["atr"]
    if 0 < s2 < px:
        out["V2"] = {"stop": s2, "tp": [px + 2 * (px - s2)],
                     "partials": [100], "breakeven": False}
    if a4 and a1 and cfg:
        try:
            p, _ = risk.plan({"strategy": "OVERSOLD_BOUNCE", "entry": [px, px],
                              "stop": sig["stop"]}, a4, a1,
                             dict(cfg, swing_leverage=1.0))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            p = None
        if p:
            out["V1"] = {"stop": p["stop"], "tp": list(p["tp"]),
                         "partials": list(p["partials"]), "breakeven": True}
    return out


def _book(st, g):
    return st["geo"].setdefault(g, {"equity": 1.0, "open": {}, "closed": []})


def _close(st, g, a, pos, ev, now):
    b = _book(st, g)
    b["equity"] *= 1 + FRAC * (pos["realized_pct"] if "realized_pct" in pos
                               else 0)
    rec = {"asset": a, "opened_at": pos["opened_at"],
           "closed_at": pos.get("closed_at") or now, "r": round(pos["r"], 3),
           "reason": pos["exit_reason"], "entry": pos["entry"],
           "stop": pos["stop0"], "tp": list(pos["tps"]),
           "partials": list(pos["partials"]),
           "breakeven": pos.get("breakeven", True)}
    b["closed"] = (b["closed"] + [rec])[-300:]
    del b["open"][a]
    if g == "G0":
        ev.append({"t": now, "event": "BOUNCE_PAPER_SELL",
                   "id": f"bounce-{a}-{pos['opened_at']}", "asset": a,
                   "reason": pos["exit_reason"], "r": rec["r"], "real": False})


def _step_open(st, bars, ev, now):
    for g in list(st["geo"]):
        b = _book(st, g)
        for a in list(b["open"]):
            pos, c4 = b["open"][a], bars.get(a)
            if not c4:
                continue
            for x in c4:
                if x["t"] < pos["next_t"] or pos["closed"]:
                    continue
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
                if not pos["closed"] and \
                        x["t"] + TF - pos["opened_at"] >= GEOS[g]["hold"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                    trade._finish(pos, "TIME", x["t"] + TF)
                pos["next_t"] = x["t"] + TF
            if pos["closed"]:
                pos["realized_pct"] = pos["r"] * pos["risk_unit"] / pos["entry"]
                _close(st, g, a, pos, ev, now)


def update(state, rows, bars, market_ok, now, cfg=None, dead=()):
    """rows: linhas elegiveis do scan (com 'price' e 'analysis').
    bars: {ativo: velas de 4H fechadas}. Devolve (resumo, eventos)."""
    st = state.setdefault("paper_bounce", {"geo": {}, "last": {}})
    st.setdefault("geo", {})
    st.setdefault("last", {})
    ev = []
    _step_open(st, bars, ev, now)
    cands = []
    for r in rows:
        a, c4 = r["asset"], bars.get(r["asset"])
        if not c4:
            continue
        t_last = c4[-1]["t"]
        if st["last"].get(a) == t_last:          # esta vela ja foi vista
            continue
        st["last"][a] = t_last
        if not market_ok:
            continue
        sig = signal(c4)
        if sig and now - sig["t"] <= TF:         # so a vela que acabou de fechar
            cands.append((sig["rsi"], a, sig, r))
    for _, a, sig, r in sorted(cands, key=lambda x: x[0]):
        an = r.get("analysis") or {}
        for g, p in plans(sig, r["price"], an.get("4h"), an.get("1d"),
                          cfg).items():
            b = _book(st, g)
            if "BOUNCE_" + g in dead:             # morta na arena: nao abre
                continue
            if a in b["open"] or len(b["open"]) >= MAX_POS:
                continue
            pos = trade.open_position(p, r["price"], sig["t"], FEE_PCT,
                                      SLIP_PCT, breakeven=p["breakeven"])
            pos["next_t"] = sig["t"]
            b["open"][a] = pos
            if g == "G0":
                ev.append({"t": now, "event": "BOUNCE_PAPER_BUY",
                           "id": f"bounce-{a}-{sig['t']}", "asset": a,
                           "pair": f"{a}/USDC", "price": r["price"],
                           "stop": p["stop"], "tp": p["tp"],
                           "rsi": round(sig["rsi"], 1), "real": False})
    return summary(st), ev


def summary(st):
    out = {}
    for g, meta in GEOS.items():
        b = st.get("geo", {}).get(g) or {"equity": 1.0, "open": {}, "closed": []}
        rs = [c["r"] for c in b["closed"]]
        out[g] = {"name": meta["name"], "n": len(rs),
                  "wins": sum(1 for x in rs if x > 0),
                  "total_r": round(sum(rs), 2),
                  "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
                  "equity_pct": round((b["equity"] - 1) * 100, 2),
                  "open": sorted(b["open"])}
    return out
