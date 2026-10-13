"""Ringue continuo da arena (decisao do Rui, 2026-10-13: "os lutadores nao
estao a morrer").

Problema: ao vivo cada estrategia da 1 a 3 operacoes por semana. Com a
regra de morte a pedir 10 a 20 operacoes, ninguem morria antes de meses.

Solucao: de hora a hora (workflow arena.yml, no GitHub Actions, sem custo
de agentes) cada lutador combate nos ULTIMOS 90 DIAS de mercado, em TODAS
as moedas listadas na Bybit UE, com as MESMAS funcoes do sistema ao vivo
(engine/backtest.candidates e simulate, engine/paper_bounce.signal e plans)
e os mesmos custos. Cada operacao tem controlos ao acaso com a mesma
geometria (engine/arena.control_rs). O resultado ("forma recente") e
escrito em forma.json no ramo `arena` e o scanner junta-o a arena.

Lutadores e regras de selecao (iguais ao que o sistema ao vivo faria):
  PULLBACK, BREAKOUT, LIQUIDITY_SWEEP, RANGE: setups READY com plano,
      confluencia >= min_score e BTC acima da media de 200 dias
  REJEITADOS (Oscar): os mesmos setups com confluencia ABAIXO do minimo,
      ou seja, o que os filtros deitam fora
  BOUNCE_G0/V1/V2/V3: o gatilho e as quatro saidas do papel do Bounce
  TREND_DAILY: tendencia diaria das grandes moedas (sem geometria fixa:
      julgada so pelo R medio)
  BOUNCE_1H: o mesmo gatilho do Bounce em velas de 1H (day trade, nao
      scalp), regra escrita antes de testar (2026-10-13): RSI14 de 1H abaixo
      de 25 numa das ultimas 3 velas, fecho acima do maximo da anterior com
      o RSI a subir, BTC acima da media de 200 dias; stop no minimo das
      ultimas 6 velas (>= 1,25 ATR); 50% na media de 20 velas, resto no
      maximo das 42 velas anteriores; stop na entrada depois do 1.o objetivo;
      saida ao fim de 24 horas

LUTADORES NOVOS de 2026-10-13 (regras escritas ANTES de testar; o Rui pediu
mais oportunidades sem perder rigor). Todos so de compra, BTC acima da media
de 200 dias, entrada na abertura seguinte, stop na entrada depois do 1.o
objetivo, saida ao fim de 3 dias, objetivos como o Bounce G0 (50% na media
de 20 velas, resto no maximo das 42 velas anteriores), stop >= 1,25 ATR:
  BOUNCE_X30: o gatilho do Bounce com RSI abaixo de 30 (em vez de 25)
  DIP_TREND:  recuo numa tendencia forte: no diario fecho > SMA50 > SMA200;
              RSI 4H abaixo de 35 numa das ultimas 3 velas; ultima vela fecha
              acima do maximo da anterior com o RSI a subir
  CAPITULACAO: vela de 4H com volume >= 3x a media de 20, pavio inferior
              >= 50% da amplitude, fecho no terco superior, depois de uma
              queda >= 8% desde o maximo das 18 velas anteriores; stop no
              minimo dessa vela menos 0,1 ATR

LUTADORES DE 2026-10-13 (2.a ronda, pedidos pelo Rui; regras escritas antes de
testar). Todos usam o gatilho do BOUNCE_X30 e as mesmas saidas, com UM filtro
cada, para medir se o filtro acrescenta valor:
  BOUNCE_FLUXO:   na vela do sinal, compradores agressivos >= 55% do volume
  BOUNCE_FORTE:   a moeda subiu mais do que o BTC nos 30 dias anteriores
  BOUNCE_SQUEEZE: funding do perpetuo (OKX) negativo na ultima liquidacao
                  antes do sinal (shorts a pagar: aperto provavel)
  BOUNCE_ISOLADA: o BTC nao caiu mais de 2% nas 24 horas antes do sinal (a
                  queda e da moeda, nao do mercado inteiro)

LUTADORES PARA REDUZIR PERDAS (2026-10-13, 3.a ronda; regras escritas antes de
testar). O mesmo gatilho do BOUNCE_X30, muda so a gestao ou o horario:
  BOUNCE_NOREACT: ao fim de 12 horas, sem objetivo atingido e com o preco na
                  entrada ou abaixo, sai ao fecho da vela
  BOUNCE_TRAIL:   depois do 1.o objetivo o stop acompanha o maximo a 1 risco
                  de distancia (nunca abaixo da entrada)
  BOUNCE_HORAS:   sem entradas ao fim de semana (UTC) nem das 00h as 06h UTC

SINAIS (decisao do Rui, 2026-10-13: "cada lutador que provar que e bom
merece um lugar"): para um lutador poder operar AO VIVO (papel e, se for o
campeao da arena, dinheiro real) precisa de uma funcao de sinal em SINAIS:
f(c4, px, cfg) -> plano para a ULTIMA vela fechada de 4H, ou None. O plano
tem stop, tp, partials, breakeven, hold_s e t_sig. O motor (engine/promo.py
e engine/paper_ring.py) usa esta tabela; os agentes acrescentam lutadores
novos aqui, com testes, sem mexer no motor.

Limites declarados: os 90 dias sao mercado ja visto por quem desenhou as
estrategias ate ao inicio da janela de reserva. Por decisao do Rui
(2026-10-13) o combate tambem qualifica: ver engine/promo.py (papel ao vivo
automatico; dinheiro real so para o campeao e so com codigo revisto).

Uso: python -m tools.arena_ringue <pasta_saida> [dias]
"""
import json
import os
import random
import sys
import time

from engine import arena, backtest as B, config, paper_bounce as PB, paper_trend as PT
from engine import trade

DAYS = 90
H4, DAY, H1 = B.H4, B.DAY, 3600
HOLD_1H = DAY
NEED_BARS = 6 * (B.analysis.MIN_BARS + 15) + 6 * DAYS   # aquecer o diario
LIVE = ("PULLBACK", "BREAKOUT", "LIQUIDITY_SWEEP", "RANGE")
REPS = 200


def closed(rows, now):
    """Velas de 4H ja fechadas (a Binance devolve a vela em curso no fim)."""
    return [r for r in rows if r["t"] + H4 <= now]


def fetch(base, now):
    from tools import fetch_history as FH
    start = (now - (NEED_BARS + 12) * H4) * 1000
    raw = FH.history(base, "4h", start)
    rows = [{"t": r[0] // 1000, "o": float(r[1]), "h": float(r[2]),
             "l": float(r[3]), "c": float(r[4]), "v": float(r[5]),
             "tb": float(r[9])} for r in raw]
    return closed(rows, now)


def fetch_1h(base, now, days):
    from tools import fetch_history as FH
    start = (now - (days + 15) * DAY) * 1000
    raw = FH.history(base, "1h", start)
    rows = [{"t": r[0] // 1000, "o": float(r[1]), "h": float(r[2]),
             "l": float(r[3]), "c": float(r[4]), "v": float(r[5]),
             "tb": float(r[9])} for r in raw]
    return [r for r in rows if r["t"] + H1 <= now]


def btc_above(btc4):
    """{dia: BTC acima da SMA200 no fecho desse dia}."""
    d = B.daily(btc4)
    out = {}
    for k in range(199, len(d)):
        sma = sum(x["c"] for x in d[k - 199:k + 1]) / 200
        out[d[k]["t"] // DAY] = d[k]["c"] > sma
    return out


def _known(t, above):
    """Filtro de mercado conhecido no instante t (fecho do dia anterior)."""
    return above.get((t - DAY) // DAY)


# ---------- estrategias de 4H do sistema ao vivo ----------

def live_trades(asset, c4, reg, above, cfg, t0):
    out = []
    for cd in B.candidates(asset, c4, reg, cfg, start_t=t0):
        ok_mkt = _known(cd["t"], above)
        if not ok_mkt and cfg.get("require_btc_above_sma200"):
            continue
        res = B.simulate(cd, c4, cfg)
        if res["status"] != "CLOSED":
            continue
        k = cd["strategy"] if cd["score"] >= cfg["min_score"] else "REJEITADOS"
        p = cd["plan"]
        ref = p["entry_zone"][1]
        out.append((k, {"asset": asset, "t": res["entry_t"], "r": res["r"],
                        "geo": {"stop": p["stop"] / ref - 1,
                                "tp": [x / ref - 1 for x in p["tp"]],
                                "partials": list(p["partials"]),
                                "breakeven": True}}))
    return out


# ---------- Oversold Bounce (as quatro saidas do papel) ----------

def bounce_trades(asset, c4, above, cfg, t0):
    out, busy = [], {}
    for i in range(PB.HIGH_BARS + 30, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if t_sig < t0 or not _known(t_sig, above):
            continue
        sig = PB.signal(c4[max(0, i - 299):i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]                       # abertura seguinte
        a4 = a1 = None
        try:
            a4 = B._tf(c4[max(0, i + 1 - B.WINDOW):i + 1])
            d1 = [x for x in B.daily(c4[:i + 1]) if x["t"] + DAY <= t_sig]
            a1 = B._tf(d1[-B.WINDOW:])
            if not (a4.get("ok") and a1.get("ok")):
                a4 = a1 = None
        except Exception:
            a4 = a1 = None
        for g, p in PB.plans(sig, px, a4, a1, cfg).items():
            if busy.get(g, 0) > i:                # uma de cada vez por moeda
                continue
            pos = trade.open_position(p, px, c4[i + 1]["t"], PB.FEE_PCT,
                                      PB.SLIP_PCT, breakeven=p["breakeven"])
            k = i + 1
            while not pos["closed"] and k < len(c4):
                x = c4[k]
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= PB.GEOS[g]["hold"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                    trade._finish(pos, "TIME", x["t"] + H4)
                k += 1
            if not pos["closed"]:
                continue
            busy[g] = k
            out.append(("BOUNCE_" + g, {"asset": asset, "t": pos["opened_at"],
                                        "r": pos["r"], "hold": PB.GEOS[g]["hold"],
                                        "geo": {"stop": p["stop"] / px - 1,
                                                "tp": [x / px - 1 for x in p["tp"]],
                                                "partials": list(p["partials"]),
                                                "breakeven": p["breakeven"],
                                                "max_hold_s": PB.GEOS[g]["hold"]}}))
    return out


def bounce_1h_trades(asset, c1, above, t0):
    """Bounce em 1H (ver cabecalho). Entrada na abertura da vela seguinte."""
    out, busy = [], -1
    for i in range(PB.HIGH_BARS + 30, len(c1) - 1):
        t_sig = c1[i]["t"] + H1
        if i < busy or t_sig < t0 or not _known(t_sig, above):
            continue
        sig = PB.signal(c1[max(0, i - 299):i + 1])
        if not sig:
            continue
        px = c1[i + 1]["o"]
        p = PB.plans(sig, px).get("G0")
        if not p:
            continue
        pos = trade.open_position(p, px, c1[i + 1]["t"], PB.FEE_PCT,
                                  PB.SLIP_PCT, breakeven=True)
        k = i + 1
        while not pos["closed"] and k < len(c1):
            x = c1[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H1)
            if not pos["closed"] and x["t"] + H1 - pos["opened_at"] >= HOLD_1H:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H1)
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append(("BOUNCE_1H", {"asset": asset, "t": pos["opened_at"], "r": pos["r"],
                                  "tf": "1h", "geo": {"max_hold_s": HOLD_1H, "stop": p["stop"] / px - 1,
                                                      "tp": [x / px - 1 for x in p["tp"]],
                                                      "partials": list(p["partials"]),
                                                      "breakeven": True}}))
    return out


# ---------- lutadores novos (ver cabecalho) ----------

def _ind(c4):
    c = [x["c"] for x in c4]
    return c, PB.rsi(c), PB.atr(c4), PB.sma(c, 20)


def _exits(c4, i, stop, at):
    """Objetivos e stop no formato do Bounce G0 para a vela i."""
    c, ma = c4[i]["c"], PB.sma([x["c"] for x in c4[max(0, i - 25):i + 1]], 20)[-1]
    if ma is None or ma < c * 1.01:
        return None
    stop = min(stop, c - PB.MIN_ATR * at)
    if stop <= 0:
        return None
    tp2 = max(x["h"] for x in c4[max(0, i - PB.HIGH_BARS):i])
    two = tp2 >= ma * 1.005
    return {"stop": stop, "tp": [ma, tp2] if two else [ma],
            "partials": [50, 50] if two else [100], "breakeven": True,
            "hold_s": 3 * DAY}


def sig_x30(c4):
    i = len(c4) - 1
    c, rs, at, _ = _ind(c4[-300:])
    k = len(c) - 1
    if k < PB.HIGH_BARS + 1 or rs[k - 2] is None or at[k] is None:
        return None
    if min(rs[k - 2:k + 1]) >= 30 or not (c[k] > c4[i - 1]["h"] and rs[k] > rs[k - 1]):
        return None
    lo = min(x["l"] for x in c4[i - PB.LOW_BARS + 1:i + 1]) - 0.1 * at[k]
    e = _exits(c4, i, lo, at[k])
    return dict(e, atr=at[k], gatilho=f"RSI 4H abaixo de 30 a virar") if e else None


def sig_dip_trend(c4):
    i = len(c4) - 1
    d = [x for x in B.daily(c4[:i + 1]) if x["t"] + DAY <= c4[i]["t"] + H4]
    if len(d) < 200:
        return None
    dc = [x["c"] for x in d]
    s50, s200 = sum(dc[-50:]) / 50, sum(dc[-200:]) / 200
    if not (dc[-1] > s50 > s200):
        return None
    c, rs, at, _ = _ind(c4[-300:])
    k = len(c) - 1
    if rs[k - 2] is None or at[k] is None:
        return None
    if min(rs[k - 2:k + 1]) >= 35 or not (c[k] > c4[i - 1]["h"] and rs[k] > rs[k - 1]):
        return None
    lo = min(x["l"] for x in c4[i - PB.LOW_BARS + 1:i + 1]) - 0.1 * at[k]
    e = _exits(c4, i, lo, at[k])
    return dict(e, atr=at[k], gatilho="recuo numa tendência forte a virar") if e else None


def sig_capitulacao(c4):
    i = len(c4) - 1
    if i < 60:
        return None
    b = c4[i]
    rng_ = b["h"] - b["l"]
    vavg = sum(x["v"] for x in c4[i - 20:i]) / 20
    if rng_ <= 0 or vavg <= 0 or b["v"] < 3 * vavg:
        return None
    wick = min(b["o"], b["c"]) - b["l"]
    hi18 = max(x["h"] for x in c4[i - 18:i])
    if wick < 0.5 * rng_ or b["c"] < b["l"] + 2 / 3 * rng_ or b["l"] > hi18 * 0.92:
        return None
    at = PB.atr(c4[-100:])[-1]
    if not at:
        return None
    e = _exits(c4, i, b["l"] - 0.1 * at, at)
    return dict(e, atr=at, gatilho="vela de capitulação com volume e pavio") if e else None


# contexto partilhado pelos filtros: velas do BTC e funding (o combate e o
# motor ao vivo preenchem-no antes de chamar as funcoes de sinal)
CTX = {"btc": None, "funding": {}, "asset": None}


def _btc_ret(t_end, n):
    """Variacao do BTC nas n velas de 4H fechadas ate t_end (ou None)."""
    import bisect
    b = CTX.get("btc") or []
    if not b:
        return None
    k = bisect.bisect_right([x["t"] + H4 for x in b], t_end) - 1
    if k - n < 0:
        return None
    return b[k]["c"] / b[k - n]["c"] - 1


def sig_fluxo(c4):
    s0 = sig_x30(c4)
    b = c4[-1]
    if not s0 or not b.get("tb") or not b.get("v"):
        return None
    share = b["tb"] / b["v"]
    return dict(s0, gatilho=f"sobrevenda a virar com {share:.0%} de compradores agressivos") if share >= .55 else None


def sig_forte(c4):
    s0 = sig_x30(c4)
    if not s0 or len(c4) < 181:
        return None
    mine = c4[-1]["c"] / c4[-181]["c"] - 1
    btc = _btc_ret(c4[-1]["t"] + H4, 180)
    if btc is None or mine <= btc:
        return None
    return dict(s0, gatilho=f"queda numa moeda mais forte do que o BTC a 30 dias ({mine - btc:+.0%})")


def sig_squeeze(c4):
    import bisect
    s0 = sig_x30(c4)
    fr = (CTX.get("funding") or {}).get(CTX.get("asset")) or []
    if not s0 or not fr:
        return None
    t = c4[-1]["t"] + H4
    k = bisect.bisect_right([x[0] for x in fr], t) - 1
    if k < 0 or t - fr[k][0] > DAY or fr[k][1] >= 0:
        return None
    return dict(s0, gatilho=f"sobrevenda com funding negativo ({fr[k][1] * 100:.3f}%): shorts a pagar")


def sig_isolada(c4):
    s0 = sig_x30(c4)
    if not s0:
        return None
    btc = _btc_ret(c4[-1]["t"] + H4, 6)
    if btc is None or btc < -0.02:
        return None
    return dict(s0, gatilho="queda da própria moeda, com o BTC estável")


def sig_noreact(c4):
    s0 = sig_x30(c4)
    return dict(s0, no_react_s=12 * 3600, gatilho=s0["gatilho"] + "; sai se não reagir em 12h") if s0 else None


def sig_trail(c4):
    s0 = sig_x30(c4)
    return dict(s0, trail_r=1.0, gatilho=s0["gatilho"] + "; stop acompanha o lucro") if s0 else None


def sig_horas(c4):
    s0 = sig_x30(c4)
    if not s0:
        return None
    t = c4[-1]["t"] + H4                   # momento da entrada (fecho da vela)
    g = time.gmtime(t)
    if g.tm_wday >= 5 or g.tm_hour < 6:
        return None
    return s0


NEW_SIGS = {"BOUNCE_NOREACT": sig_noreact, "BOUNCE_TRAIL": sig_trail, "BOUNCE_HORAS": sig_horas,
            "BOUNCE_X30": sig_x30, "DIP_TREND": sig_dip_trend, "CAPITULACAO": sig_capitulacao,
            "BOUNCE_FLUXO": sig_fluxo, "BOUNCE_FORTE": sig_forte,
            "BOUNCE_SQUEEZE": sig_squeeze, "BOUNCE_ISOLADA": sig_isolada}


def fetch_funding(base, now, days):
    """[(t_s, taxa)] do perpetuo USDT da OKX nos ultimos dias ([] se nao houver)."""
    from engine import sources
    out, after = [], None
    while True:
        params = {"instId": f"{base}-USDT-SWAP", "limit": 100}
        if after:
            params["after"] = after
        try:
            d = sources._get("https://www.okx.com/api/v5/public/funding-rate-history", params)
        except Exception:
            break
        rows = d.get("data") or [] if isinstance(d, dict) else []
        if not rows:
            break
        out += [(int(r["fundingTime"]) // 1000, float(r["fundingRate"])) for r in rows]
        after = rows[-1]["fundingTime"]
        if out[-1][0] < now - (days + 5) * DAY or len(rows) < 100:
            break
        time.sleep(0.15)
    return sorted(set(out))


def generic_trades(asset, c4, above, t0, key, fn):
    """Corre uma funcao de sinal vela a vela (so passado) e simula G0."""
    CTX["asset"] = asset
    out, busy = [], -1
    for i in range(250, len(c4) - 1):
        t_sig = c4[i]["t"] + H4
        if i < busy or t_sig < t0 or not _known(t_sig, above):
            continue
        sig = fn(c4[:i + 1])
        if not sig:
            continue
        px = c4[i + 1]["o"]
        if not (sig["stop"] < px < sig["tp"][0]):
            continue
        pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"], PB.FEE_PCT,
                                  PB.SLIP_PCT, breakeven=True)
        k = i + 1
        while not pos["closed"] and k < len(c4):
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
            if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                trade._finish(pos, "TIME", x["t"] + H4)
            k += 1
        if not pos["closed"]:
            continue
        busy = k
        out.append((key, {"asset": asset, "t": pos["opened_at"], "r": pos["r"],
                          "geo": {"stop": sig["stop"] / px - 1,
                                  "tp": [x / px - 1 for x in sig["tp"]],
                                  "partials": list(sig["partials"]),
                                  "breakeven": True, "max_hold_s": sig["hold_s"],
                                  "no_react_s": sig.get("no_react_s"),
                                  "trail_r": sig.get("trail_r")}}))
    return out


def live_sig(fn):
    """Adapta uma funcao de sinal ao formato SINAIS (sinal na ultima vela)."""
    def f(c4, px, cfg=None):
        sig = fn(c4)
        if not sig or not (sig["stop"] < px < sig["tp"][0]):
            return None
        return dict(sig, t_sig=c4[-1]["t"] + H4)
    return f


# ---------- sinais ao vivo (para papel e dinheiro real) ----------

def sinal_bounce(g):
    """Sinal do Bounce com a saida g na ultima vela fechada de 4H."""
    def f(c4, px, cfg=None):
        if len(c4) < PB.HIGH_BARS + 2:
            return None
        sig = PB.signal(c4[-300:])
        if not sig:
            return None
        p = PB.plans(sig, px).get(g)
        if not p:
            return None
        return dict(p, hold_s=PB.GEOS[g]["hold"], t_sig=sig["t"],
                    atr=sig["atr"], gatilho=f"RSI 4H a {sig['rsi']:.0f} e fecho "
                    "acima do máximo da vela anterior (sobrevenda a virar)")
    return f


SINAIS = {"BOUNCE_G0": sinal_bounce("G0"), "BOUNCE_V2": sinal_bounce("V2"),
          "BOUNCE_V3": sinal_bounce("V3"),
          **{k: live_sig(fn) for k, fn in NEW_SIGS.items()}}


# ---------- tendencia diaria (grandes moedas) ----------

def trend_trades(asset, c4, above, cfg, t0):
    if asset not in PT.MAJORS21:
        return []
    d = B.daily(c4)
    fee, out, pos = cfg["fee_pct"] / 100, [], None
    for k in range(201, len(d)):
        day = d[k]
        if pos:
            if day["l"] <= pos["stop"]:
                ex = min(day["o"], pos["stop"]) * (1 - PT.SLIP)
            elif d[k - 1]["c"] < min(x["l"] for x in d[k - 1 - PT.M:k - 1]):
                ex = day["o"] * (1 - PT.SLIP)
            else:
                continue
            ru = pos["entry"] - pos["stop"] + fee * (pos["entry"] + pos["stop"])
            out.append(("TREND_DAILY", {"asset": asset, "t": pos["t"],
                                        "r": (ex - pos["entry"] - fee * (ex + pos["entry"])) / ru,
                                        "geo": None}))
            pos = None
            continue
        prev = d[k - 1]                            # dia fechado, decide hoje
        if day["t"] < t0 or not above.get(prev["t"] // DAY):
            continue
        sma = sum(x["c"] for x in d[k - 200:k]) / 200
        if prev["c"] > max(x["h"] for x in d[k - 1 - PT.N:k - 1]) and prev["c"] > sma:
            atr = PT._atr(d[:k])
            e = day["o"] * (1 + PT.SLIP)
            if atr > 0:
                pos = {"entry": e, "stop": e - PT.K_ATR * atr, "t": day["t"]}
    return out


# ---------- juntar tudo ----------

def judge(trs, bars, rng, bars1h=None):
    """Resumo de um lutador com o teste contra o acaso."""
    rs = [t["r"] for t in trs]
    lists = []
    for t in trs:
        src = (bars1h or {}) if t.get("tf") == "1h" else bars
        if t.get("geo") and src.get(t["asset"]):
            lists.append(arena.control_rs(src[t["asset"]], t["t"], t["geo"],
                                          "LONG", rng, reps=REPS))
    has_ctrl = bool(lists) and sum(1 for c in lists if c) >= max(1, len(rs) // 2)
    med, p95 = arena._dist(lists, rng) if has_ctrl else (None, None)
    mean = sum(rs) / len(rs)
    return {"n": len(rs), "wins": sum(1 for x in rs if x > 0),
            "avg_r": round(mean, 3), "total_r": round(sum(rs), 2),
            "ultimas": [round(x, 2) for x in rs[-10:]],
            "acaso_mediana": None if med is None else round(med, 3),
            "acaso_p95": None if p95 is None else round(p95, 3),
            "veredicto": arena.verdict(len(rs), mean, med, p95, has_ctrl)}


def run(bars, cfg, now, days=DAYS, seed=7, bars1h=None, funding=None):
    t0 = now - days * DAY
    btc = bars.get("BTC")
    CTX.update(btc=btc, funding=funding or {})
    reg, above = B.regimes(btc), btc_above(btc)
    groups = {k: [] for k in LIVE + ("REJEITADOS", "BOUNCE_G0", "BOUNCE_V1",
                                     "BOUNCE_V2", "BOUNCE_V3", "TREND_DAILY",
                                     "BOUNCE_1H") + tuple(NEW_SIGS)}
    for a, c4 in sorted(bars.items()):
        try:
            for k, t in live_trades(a, c4, reg, above, cfg, t0):
                groups.setdefault(k, []).append(t)
            for k, t in bounce_trades(a, c4, above, cfg, t0):
                groups[k].append(t)
            for k, t in trend_trades(a, c4, above, cfg, t0):
                groups[k].append(t)
            for key, fn in NEW_SIGS.items():
                for k, t in generic_trades(a, c4, above, t0, key, fn):
                    groups[k].append(t)
            if (bars1h or {}).get(a):
                for k, t in bounce_1h_trades(a, bars1h[a], above, t0):
                    groups[k].append(t)
        except Exception as e:                       # uma moeda nao para o ringue
            print(f"{a}: {type(e).__name__}: {e}", file=sys.stderr)
    rng = random.Random(seed)
    out = {}
    for k, trs in groups.items():
        trs.sort(key=lambda t: t["t"])
        out[k] = judge(trs, bars, rng, bars1h) if trs else {
            "n": 0, "wins": 0, "avg_r": None, "total_r": 0, "ultimas": [],
            "acaso_mediana": None, "acaso_p95": None, "veredicto": "A COMPETIR"}
    return {"atualizado": int(now), "janela_dias": days,
            "desde": int(t0), "moedas": len(bars), "lutadores": out}


def main(dest, days=DAYS):
    from engine import venue
    now = int(time.time())
    cfg = config.load()
    bars, bars1h, falhas = {}, {}, []
    listed = sorted(set(venue.fetch("USDC")) | {"BTC"})
    for base in listed:
        try:
            c = fetch(base, now)
        except Exception as e:
            falhas.append(f"{base}: {str(e)[:50]}")
            continue
        if len(c) >= NEED_BARS:
            bars[base] = c
            try:
                h1 = fetch_1h(base, now, days)
                if len(h1) >= 24 * days:
                    bars1h[base] = h1
            except Exception as e:
                falhas.append(f"{base} 1H: {str(e)[:40]}")
        time.sleep(0.1)
    if "BTC" not in bars:
        raise SystemExit("sem velas do BTC: ringue nao corre")
    t = time.time()
    funding = {}
    for base in bars:
        fr = fetch_funding(base, now, days)
        if fr:
            funding[base] = fr
    res = run(bars, cfg, now, days, bars1h=bars1h, funding=funding)
    res["funding_moedas"] = len(funding)
    res["segundos"] = round(time.time() - t)
    res["falhas"] = falhas[:20]
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "forma.json"), "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res["lutadores"].items():
        print(f"{k:16s} n={v['n']:4d} R={v['avg_r']} acaso={v['acaso_mediana']}"
              f"/{v['acaso_p95']} -> {v['veredicto']}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else DAYS)
