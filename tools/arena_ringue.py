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


def fetch(base, now, need=None):
    from tools import fetch_history as FH
    start = (now - ((need or NEED_BARS) + 12) * H4) * 1000
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
CTX = {"btc": None, "funding": {}, "asset": None, "oi": {}, "macro": {}, "ls": {}}


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


OI_DROP = -0.05             # OI caiu pelo menos 5% em 24h: alavancagem limpa


def sig_desalav(c4):
    """X30 depois de uma desalavancagem: o open interest (Binance, servidor
    europeu) caiu >= 5% nas ultimas 24h. Longs forcados a sair, vendedores
    esgotados. A Binance so da 30 dias de OI, por isso o combate e curto."""
    import bisect
    s0 = sig_x30(c4)
    oi = (CTX.get("oi") or {}).get(CTX.get("asset")) or []
    if not s0 or len(oi) < 7:
        return None
    t = c4[-1]["t"] + H4
    k = bisect.bisect_right([x[0] for x in oi], t) - 1
    if k < 6 or t - oi[k][0] > H4 or not oi[k - 6][1]:
        return None
    chg = oi[k][1] / oi[k - 6][1] - 1
    if chg > OI_DROP:
        return None
    return dict(s0, gatilho=f"sobrevenda a virar depois de o open interest cair {chg:.0%} em 24h (alavancagem limpa)")


# ---------- macroeconomia (servidor europeu, Yahoo Finance 1H) ----------
MACRO_MAX_GAP = 4 * DAY        # fim de semana / feriado: ultimo valor conhecido


def macro_at(name, t):
    """Ultimo valor de name conhecido ate t (ou None se nao houver ou for velho)."""
    import bisect
    s = (CTX.get("macro") or {}).get(name) or []
    k = bisect.bisect_right([x[0] for x in s], t) - 1
    if k < 0 or t - s[k][0] > MACRO_MAX_GAP:
        return None
    return s[k][1]


def macro_chg(name, t, secs):
    a, b = macro_at(name, t), macro_at(name, t - secs)
    return None if a is None or not b else a / b - 1


def macro_state(t):
    """'favoravel', 'medo' ou 'neutro' no momento t (None sem dados).
    medo: VIX >= 25, ou S&P 500 a cair >= 2% em 24h, ou dolar a subir
    >= 1.5% em 5 dias. favoravel: VIX < 20, S&P 500 >= -0.5% em 24h e dolar
    <= +0.5% em 5 dias."""
    vix, sp = macro_at("VIX", t), macro_chg("SP", t, DAY)
    dxy = macro_chg("DXY", t, 5 * DAY)
    if vix is None or sp is None or dxy is None:
        return None
    if vix >= 25 or sp <= -0.02 or dxy >= 0.015:
        return "medo"
    if vix < 20 and sp >= -0.005 and dxy <= 0.005:
        return "favoravel"
    return "neutro"


def sig_macro(c4):
    """X30 so com a macroeconomia favoravel (bolsa americana estavel, dolar
    calmo, VIX baixo)."""
    s0 = sig_x30(c4)
    if not s0 or macro_state(c4[-1]["t"] + H4) != "favoravel":
        return None
    return dict(s0, gatilho=s0["gatilho"] + "; macroeconomia favorável (bolsa estável, dólar calmo, VIX baixo)")


def sig_medo(c4):
    """X30 depois de medo macro (VIX alto, bolsa a cair ou dolar a disparar):
    compra o exagero. Hipotese contraria a da sig_macro; o ringue decide."""
    s0 = sig_x30(c4)
    if not s0 or macro_state(c4[-1]["t"] + H4) != "medo":
        return None
    return dict(s0, gatilho=s0["gatilho"] + "; depois de medo na macroeconomia")


def absorcao(c4):
    """(ok, texto): o preco fez um minimo mais baixo nas ultimas 3 velas mas a
    parte de compradores agressivos subiu (vendas a ser absorvidas)."""
    if len(c4) < 12:
        return False, "sem velas suficientes"
    sh = [x["tb"] / x["v"] if x.get("tb") and x.get("v") else None for x in c4[-4:]]
    if None in sh:
        return False, "sem dados de compradores agressivos"
    lower = min(x["l"] for x in c4[-3:]) < min(x["l"] for x in c4[-9:-3])
    rising = sh[-1] >= 0.5 and sh[-1] - sum(sh[:3]) / 3 >= 0.05
    txt = (f"compradores agressivos {sh[-1]:.0%} (antes {sum(sh[:3]) / 3:.0%})"
           + (" com mínimo mais baixo" if lower else " sem mínimo mais baixo"))
    return lower and rising, txt


def sig_absorcao(c4):
    """X30 com absorcao: novo minimo feito com compradores agressivos a
    crescer. Fluxo ao longo de varias velas (o Flavio so ve a ultima)."""
    s0 = sig_x30(c4)
    if not s0:
        return None
    ok, txt = absorcao(c4)
    return dict(s0, gatilho=f"sobrevenda a virar com absorção: {txt}") if ok else None


LSR_PCT = 25


def lsr_ok(asset, t):
    """(ok, texto): racio long/short das contas na Binance no quartil mais
    baixo do seu historico (mais gente a apostar na descida do que o normal)."""
    import bisect
    ls = (CTX.get("ls") or {}).get(asset) or []
    # o valor de cada periodo de 4H so se conhece no fim dele (sem look-ahead)
    k = bisect.bisect_right([x[0] + H4 for x in ls], t) - 1
    if k < 20 or t - (ls[k][0] + H4) > 2 * H4:
        return False, "sem rácio long/short da Binance"
    hist = [x[1] for x in ls[:k + 1]][-100:]
    v = ls[k][1]
    pct = 100 * sum(1 for h in hist if h < v) / len(hist)
    return pct <= LSR_PCT, f"rácio long/short {v:.2f} (percentil {pct:.0f}; preciso ≤ {LSR_PCT})"


def sig_lsr(c4):
    """X30 quando o rácio long/short da Binance esta no quartil baixo:
    vendedores a descoberto em excesso, combustivel para a subida."""
    s0 = sig_x30(c4)
    if not s0:
        return None
    ok, txt = lsr_ok(CTX.get("asset"), c4[-1]["t"] + H4)
    return dict(s0, gatilho=f"sobrevenda a virar com {txt}") if ok else None


# ---------- familias usadas pelos grandes gestores, alem da sobrevenda ----------
# (decisao do Rui, 2026-10-14: "quero todas as estrategias dos melhores
# traders do mundo"). Entram no ringue como os outros: so papel ate provar.

def _trend_plan(c4, stop, r_mult=(2, 5), hold=20 * DAY, trail=1.0, gat=""):
    """Plano de seguimento de tendencia: objetivos a 2R e 5R, metade em cada,
    stop para a entrada no TP1 e depois a seguir o preco (trail)."""
    e = c4[-1]["c"]
    if not 0 < stop < e * 0.995:
        return None
    r = e - stop
    return {"stop": stop, "tp": [e + r_mult[0] * r, e + r_mult[1] * r], "partials": [50, 50],
            "breakeven": True, "hold_s": hold, "trail_r": trail, "atr": PB.atr(c4[-100:])[-1],
            "gatilho": gat}


def sig_turtle(c4):
    """Tartarugas (Richard Dennis): rompimento do maximo de 20 dias, stop a
    2 N (N = ATR diario de 20 dias), objetivos 2R/5R e stop que segue."""
    d = [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]
    if len(d) < 25:
        return None
    hi20 = max(x["h"] for x in d[-21:-1])
    prev = c4[-2]["c"]
    if not (c4[-1]["c"] > hi20 >= prev):
        return None
    tr = [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"]) for k in range(len(d) - 20, len(d))]
    n = sum(tr) / 20
    return _trend_plan(c4, c4[-1]["c"] - 2 * n, gat=f"rompimento do máximo de 20 dias ({hi20:.6g})")


def sig_squeeze_bb(c4):
    """Compressao de volatilidade (Bollinger squeeze): bandas no aperto mais
    estreito de 20 dias e fecho acima da banda superior com volume."""
    if len(c4) < 140:
        return None
    c = [x["c"] for x in c4[-140:]]

    def width(k):
        w = c[k - 19:k + 1]
        m = sum(w) / 20
        sd = (sum((x - m) ** 2 for x in w) / 20) ** 0.5
        return m, sd, 4 * sd / m if m else 0
    m, sd, wnow = width(len(c) - 1)
    ws = [width(k)[2] for k in range(len(c) - 121, len(c) - 1)]
    _, _, wprev = width(len(c) - 2)
    vavg = sum(x["v"] for x in c4[-21:-1]) / 20
    if not (wprev <= sorted(ws)[len(ws) // 10] and c[-1] > m + 2 * sd and c4[-1]["v"] > 1.5 * vavg):
        return None
    return _trend_plan(c4, m - 0.5 * sd, r_mult=(1.5, 3), hold=5 * DAY,
                       gat="volatilidade comprimida a soltar-se para cima, com volume")


MOM_TOP = 5


def momentum_rank(bars, t):
    """[moedas] por retorno de 30 dias ate t (velas de 4H fechadas), melhor primeiro."""
    import bisect
    out = []
    for a, c4 in bars.items():
        k = bisect.bisect_right([x["t"] + H4 for x in c4], t) - 1
        if k >= 180:
            out.append((c4[k]["c"] / c4[k - 180]["c"] - 1, a))
    return [a for _, a in sorted(out, reverse=True)]


def sig_momentum(c4):
    """Momentum entre moedas (rotacao semanal, usado por fundos quant): a
    segunda-feira as 00h UTC compra as 5 moedas com melhor retorno a 30 dias,
    se esse retorno for positivo e maior do que o do BTC; fica 7 dias."""
    t = c4[-1]["t"] + H4
    g = time.gmtime(t)
    if g.tm_wday != 0 or g.tm_hour != 0 or len(c4) < 181:
        return None
    rank = (CTX.get("rank") or {}).get(t)
    if rank is None:
        rank = momentum_rank(CTX.get("bars") or {}, t)
    a = CTX.get("asset")
    if a not in rank[:MOM_TOP]:
        return None
    mine = c4[-1]["c"] / c4[-181]["c"] - 1
    btc = _btc_ret(t, 180)
    if mine <= 0 or (btc is not None and mine <= btc):
        return None
    at = PB.atr(c4[-100:])[-1]
    e = c4[-1]["c"]
    return {"stop": e - 3 * at, "tp": [e + 6 * at], "partials": [100], "breakeven": False,
            "hold_s": 7 * DAY, "atr": at,
            "gatilho": f"entre as {MOM_TOP} moedas mais fortes a 30 dias ({mine:+.0%}, {rank.index(a) + 1}.ª)"}


# ---------- vendas a descoberto pela margem spot (decisao do Rui, 2026-10-14) ----------
# Cada short e o ESPELHO de uma compra (engine/short.py): as funcoes correm
# sobre as velas invertidas (1/preco). Um "minimo" no espelho e um maximo
# real; sobrevenda no espelho e sobrecompra real. Ganham quando o preco cai.

def _btc_ret_real(t, n):
    return _btc_ret(t, n)


def sig_short_squeeze(m4):
    """Short de sobrecompra com funding muito positivo (compradores a pagar,
    alavancados em excesso do lado comprador)."""
    import bisect
    s0 = sig_x30(m4)
    fr = (CTX.get("funding") or {}).get(CTX.get("asset")) or []
    if not s0 or not fr:
        return None
    t = m4[-1]["t"] + H4
    k = bisect.bisect_right([x[0] for x in fr], t) - 1
    if k < 0 or t - fr[k][0] > DAY or fr[k][1] < 0.0002:
        return None
    return dict(s0, gatilho=f"sobrecompra a virar com funding alto ({fr[k][1] * 100:.3f}%): compradores alavancados a pagar")


def sig_short_isolada(m4):
    """Short de uma subida so da propria moeda, com o BTC parado."""
    s0 = sig_x30(m4)
    if not s0:
        return None
    btc = _btc_ret_real(m4[-1]["t"] + H4, 6)
    if btc is None or btc > 0.02:
        return None
    return dict(s0, gatilho="subida exagerada da própria moeda, com o BTC parado")


def _shortify(fn, txt):
    def f(m4):
        s0 = fn(m4)
        return dict(s0, gatilho=txt(s0)) if s0 else None
    return f


SHORT_SIGS = {
    "SHORT_X30": _shortify(sig_x30, lambda s: "sobrecompra (RSI 4H acima de 70) a virar para baixo"),
    "SHORT_FLUXO": _shortify(sig_fluxo, lambda s: "sobrecompra a virar com vendedores agressivos"),
    "SHORT_TURTLE": _shortify(sig_turtle, lambda s: "quebra do mínimo de 20 dias (Tartarugas, em descida)"),
    "SHORT_SQUEEZE": sig_short_squeeze,
    "SHORT_ISOLADA": sig_short_isolada,
}


def short_live(fn):
    """Sinal de short ao vivo em precos REAIS a partir da funcao do espelho."""
    from engine import short as SH

    def f(c4, px, cfg=None):
        m4 = SH.mirror(c4)
        sig = fn(m4)
        if not sig:
            return None
        pm = 1 / px
        if not (sig["stop"] < pm < sig["tp"][0]):
            return None
        return dict(sig, side="SHORT", stop=1 / sig["stop"], tp=[1 / x for x in sig["tp"]],
                    t_sig=m4[-1]["t"] + H4)
    return f


# ---------- rompimento com espaco e reteste do nivel rompido (2026-10-14) ----------

def sig_breakout_espaco(c4):
    """Rompimento com confirmacao: fecho acima do maximo de 5 dias com volume
    1,5x, SEM entrada tardia (no maximo 1 ATR acima do nivel) e com espaco ate
    a proxima resistencia de pelo menos 2R. Stop de volta dentro do nivel."""
    if len(c4) < 200:
        return None
    at = PB.atr(c4[-100:])[-1]
    if not at:
        return None
    level = max(x["h"] for x in c4[-31:-1])
    b, prev = c4[-1], c4[-2]
    vavg = sum(x["v"] for x in c4[-21:-1]) / 20
    if not (b["c"] > level >= prev["c"] and b["v"] > 1.5 * vavg):
        return None
    if b["c"] - level > at:                        # entrada tardia: ja esticou
        return None
    e, stop = b["c"], level - 0.5 * at
    r = e - stop
    above = [x["h"] for x in c4[-181:-31] if x["h"] > e * 1.002]
    res = min(above) if above else None
    if res is not None and res - e < 2 * r:        # sem espaco ate a resistencia
        return None
    tp2 = res if res is not None and res > e + 2 * r else e + 4 * r
    return {"stop": stop, "tp": [e + 2 * r, tp2], "partials": [50, 50], "breakeven": True,
            "hold_s": 5 * DAY, "trail_r": 1.0, "atr": at,
            "gatilho": f"rompimento de {level:.6g} com volume, sem entrada tardia e com espaço até "
                       + (f"{res:.6g}" if res else "máximos")}


def sig_reteste(c4):
    """Reteste do nivel rompido: uma resistencia (maximo de 8 a 2 dias atras)
    foi rompida nas ultimas 12 velas; o preco volta a testa-la por cima e fecha
    em alta acima do maximo da vela anterior (confirmacao de retoma)."""
    if len(c4) < 120:
        return None
    at = PB.atr(c4[-100:])[-1]
    if not at:
        return None
    level = max(x["h"] for x in c4[-60:-12])
    broke = any(x["c"] > level * 1.01 for x in c4[-12:-1])
    b, prev = c4[-1], c4[-2]
    touched = min(x["l"] for x in c4[-3:]) <= level * 1.005
    if not (broke and touched and b["c"] > level and b["c"] > b["o"] and b["c"] > prev["h"]):
        return None
    e = b["c"]
    stop = min(level - 0.7 * at, min(x["l"] for x in c4[-3:]) - 0.1 * at)
    r = e - stop
    if r <= 0:
        return None
    hi = max(x["h"] for x in c4[-12:-1])
    tp1 = hi if hi > e + r else e + 1.5 * r
    return {"stop": stop, "tp": [tp1, e + 3 * r], "partials": [50, 50], "breakeven": True,
            "hold_s": 5 * DAY, "atr": at,
            "gatilho": f"reteste por cima do nível rompido {level:.6g} com vela de retoma"}


# ---------- reversao no intervalo (decisao do Rui, 2026-10-15) ----------
# Mean reversion SO com o mercado realmente lateral: forca de tendencia baixa
# (ADX 4H < 20), media de 50 velas plana e um intervalo claro (6% a 30% entre
# o maximo e o minimo de 60 velas). Compra no fundo do intervalo: toque na
# banda inferior de Bollinger e viragem (fecho acima do maximo da vela
# anterior com o RSI a subir). Objetivos: banda do meio, depois banda de cima
# (no maximo o topo do intervalo). Stop abaixo do fundo do intervalo.
def sig_intervalo(c4):
    from engine import indicators as I
    if len(c4) < 130:
        return None
    w = c4[-130:]
    c = [x["c"] for x in w]
    ad = I.adx(w)[-1]
    if ad is None or ad >= 20:
        return None
    s50 = [sum(c[k - 49:k + 1]) / 50 for k in (len(c) - 11, len(c) - 1)]
    if abs(s50[1] / s50[0] - 1) > 0.015:
        return None
    hi, lo = max(x["h"] for x in w[-60:]), min(x["l"] for x in w[-60:])
    if not (0.06 <= hi / lo - 1 <= 0.30):
        return None
    m = sum(c[-20:]) / 20
    sd = (sum((x - m) ** 2 for x in c[-20:]) / 20) ** 0.5
    lower, upper = m - 2 * sd, m + 2 * sd
    rs, at = PB.rsi(c), PB.atr(w)
    if rs[-1] is None or rs[-2] is None or at[-1] is None:
        return None
    toque = min(w[-2]["l"], w[-3]["l"]) <= lower
    virou = c[-1] > w[-2]["h"] and rs[-1] > rs[-2]
    fundo = c[-1] <= lo + (hi - lo) / 3
    if not (toque and virou and fundo):
        return None
    stop = min(lo, min(x["l"] for x in w[-10:])) - 0.3 * at[-1]
    if c[-1] - stop > 3 * at[-1] or stop <= 0:
        return None
    tp1, tp2 = m, min(upper, hi)
    if tp1 < c[-1] * 1.01:
        return None
    two = tp2 > tp1 * 1.005
    return {"stop": stop, "tp": [tp1, tp2] if two else [tp1], "partials": [50, 50] if two else [100],
            "breakeven": True, "hold_s": 3 * DAY, "atr": at[-1],
            "gatilho": f"mercado lateral (ADX {ad:.0f}): fundo do intervalo a virar na banda inferior"}


# ---------- estudo dos stops (decisao do Rui, 2026-10-15) ----------
# 14/10: SOL e XRP tocaram no stop no minimo de um pavio e voltaram a subir.
# Duas variantes do Xavier com o MESMO gatilho e os mesmos objetivos, so com
# o stop noutro sitio, combatem contra o original:
#   PAVIO: stop 0,6 ATR abaixo do minimo recente (em vez de 0,1 ATR);
#   LIQ:   stop abaixo do minimo de 30 velas (onde esta a liquidez), no
#          maximo 3 ATR abaixo da entrada (se for mais longe, nao entra).
# O risco em USDC fica igual (a posicao encolhe com o stop mais largo); so
# ganha lugar quem bater o original e o acaso no combate.
def _stop_var(fn, mode):
    def f(c4):
        e = fn(c4)
        if not e or not e.get("atr"):
            return e
        at, c = e["atr"], c4[-1]["c"]
        if mode == "pavio":
            stop = e["stop"] - 0.5 * at
        else:
            pool = min(x["l"] for x in c4[-30:])
            stop = min(e["stop"], pool - 0.2 * at)
            if c - stop > 3 * at:
                return None
        if stop <= 0:
            return None
        return dict(e, stop=stop, gatilho=e.get("gatilho", "") + (" · stop abaixo dos pavios" if mode == "pavio"
                                                                 else " · stop abaixo da liquidez"))
    return f


NEW_SIGS = {"BRK_ESPACO": sig_breakout_espaco, "RETESTE": sig_reteste,
            "TURTLE": sig_turtle, "SQUEEZE_BB": sig_squeeze_bb, "MOMENTUM": sig_momentum,
            "BOUNCE_ABSORCAO": sig_absorcao, "BOUNCE_LSR": sig_lsr,
            "BOUNCE_MACRO": sig_macro, "BOUNCE_MEDO": sig_medo,
            "BOUNCE_DESALAV": sig_desalav, "BOUNCE_NOREACT": sig_noreact, "BOUNCE_TRAIL": sig_trail, "BOUNCE_HORAS": sig_horas,
            "BOUNCE_X30": sig_x30, "DIP_TREND": sig_dip_trend, "CAPITULACAO": sig_capitulacao,
            "BOUNCE_FLUXO": sig_fluxo, "BOUNCE_FORTE": sig_forte,
            "BOUNCE_SQUEEZE": sig_squeeze, "BOUNCE_ISOLADA": sig_isolada,
            "BOUNCE_X30_PAVIO": _stop_var(sig_x30, "pavio"),
            "BOUNCE_X30_LIQ": _stop_var(sig_x30, "liq"),
            "REVERSAO_INTERVALO": sig_intervalo}


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


class _Sinais(dict):
    """Registo de sinais que tambem responde pelos lutadores que regressaram
    com nome novo (TURTLE_R2 usa a funcao de TURTLE)."""
    @staticmethod
    def _b(k):
        import re
        return re.sub(r"_R\d+$", "", k) if isinstance(k, str) else k

    def __contains__(self, k):
        return dict.__contains__(self, k) or dict.__contains__(self, self._b(k))

    def __missing__(self, k):
        b = self._b(k)
        if b != k and dict.__contains__(self, b):
            return dict.__getitem__(self, b)
        raise KeyError(k)

    def get(self, k, d=None):
        try:
            return self[k]
        except KeyError:
            return d


SINAIS = {"BOUNCE_G0": sinal_bounce("G0"), "BOUNCE_V2": sinal_bounce("V2"),
          "BOUNCE_V3": sinal_bounce("V3"),
          **{k: live_sig(fn) for k, fn in NEW_SIGS.items()},
          **{k: short_live(fn) for k, fn in SHORT_SIGS.items()}}
SINAIS = _Sinais(SINAIS)


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


def regime_by_day(btc4):
    """{dia: 'subida'|'queda'|'lateral'} com o regime do BTC no fecho de cada dia
    (mesmas regras de engine/arena.market_regime, so com dias passados)."""
    d = B.daily(btc4 or [])
    c = [x["c"] for x in d]
    out = {}
    for k in range(200, len(d)):
        s50, s200 = sum(c[k - 49:k + 1]) / 50, sum(c[k - 199:k + 1]) / 200
        r30 = c[k] / c[k - 30] - 1
        out[d[k]["t"] // DAY] = ("subida" if c[k] > s50 > s200 and r30 > 0.08 else
                                 "queda" if c[k] < s50 < s200 and r30 < -0.08 else "lateral")
    return out


def run(bars, cfg, now, days=DAYS, seed=7, bars1h=None, funding=None, oi=None,
        macro=None, ls=None, renascidos=None, regimes=False):
    t0 = now - days * DAY
    btc = bars.get("BTC")
    CTX.update(btc=btc, funding=funding or {}, oi=oi or {}, macro=macro or {}, ls=ls or {},
               bars=bars, rank={})
    # rotacao semanal: o ranking de cada segunda-feira 00h UTC, calculado uma vez
    for x in btc or []:
        t = x["t"] + H4
        g = time.gmtime(t)
        if g.tm_wday == 0 and g.tm_hour == 0 and t >= t0:
            CTX["rank"][t] = momentum_rank(bars, t)
    reg, above = B.regimes(btc), btc_above(btc)
    groups = {k: [] for k in LIVE + ("REJEITADOS", "BOUNCE_G0", "BOUNCE_V1",
                                     "BOUNCE_V2", "BOUNCE_V3", "TREND_DAILY",
                                     "BOUNCE_1H") + tuple(NEW_SIGS) + tuple(SHORT_SIGS)}
    from engine import short as SH
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    always = {k: True for k in above}             # shorts: sem filtro do BTC
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
            for key, fn in SHORT_SIGS.items():
                for k, t in generic_trades(a, mbars[a], always, t0, key, fn):
                    groups[k].append(dict(t, side="SHORT"))
            if (bars1h or {}).get(a):
                for k, t in bounce_1h_trades(a, bars1h[a], above, t0):
                    groups[k].append(t)
        except Exception as e:                       # uma moeda nao para o ringue
            print(f"{a}: {type(e).__name__}: {e}", file=sys.stderr)
    # lutadores que regressaram com nome novo: as operacoes da familia de
    # origem, mas so a partir do regresso (registo limpo)
    for nk, info in (renascidos or {}).items():
        groups[nk] = [t for t in groups.get(info.get("base"), [])
                      if t["t"] >= (info.get("desde") or 0)]
    if regimes:
        CTX["regmap"] = regime_by_day(btc)
    rng = random.Random(seed)
    out = {}
    for k, trs in groups.items():
        trs.sort(key=lambda t: t["t"])
        jb = mbars if arena.base_key(k).startswith("SHORT_") else bars   # acaso no espelho
        out[k] = judge(trs, jb, rng, bars1h) if trs else {
            "n": 0, "wins": 0, "avg_r": None, "total_r": 0, "ultimas": [],
            "acaso_mediana": None, "acaso_p95": None, "veredicto": "A COMPETIR"}
        if regimes and trs:                    # ringue longo: resultado por altura do mercado
            rmap = CTX.get("regmap") or {}
            out[k]["por_regime"] = {}
            for rg in ("subida", "lateral", "queda"):
                sub = [t for t in trs if rmap.get((t["t"] - DAY) // DAY) == rg]
                if sub:
                    out[k]["por_regime"][rg] = judge(sub, jb, rng, bars1h)
    return {"atualizado": int(now), "janela_dias": days,
            "desde": int(t0), "moedas": len(bars), "lutadores": out}


def main(dest, days=DAYS, state_path=None, longo=False):
    from engine import venue
    now = int(time.time())
    cfg = config.load()
    bars, bars1h, falhas = {}, {}, []
    need = 6 * (B.analysis.MIN_BARS + 15) + 6 * days
    listed = sorted(set(venue.fetch("USDC")) | {"BTC"})
    for base in listed:
        try:
            c = fetch(base, now, need)
        except Exception as e:
            falhas.append(f"{base}: {str(e)[:50]}")
            continue
        if len(c) >= need or (longo and len(c) >= NEED_BARS):
            bars[base] = c
            if longo:                        # o ringue longo nao corre o 1H (pesado)
                continue
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
    # Binance (servidor europeu) quando ha dados recentes; senao OKX
    from engine import europa
    eu = europa.load(europa.MAX_AGE_RING, now)
    funding, oi, ls, fonte = {}, {}, {}, {"binance": 0, "okx": 0}
    for base in bars:
        c = europa.coin(eu, base) or {}
        fr = [tuple(x) for x in c.get("funding") or []]
        if fr and fr[0][0] <= now - (days - 5) * DAY:
            funding[base] = fr
            fonte["binance"] += 1
        else:
            fr = fetch_funding(base, now, days)
            if fr:
                funding[base] = fr
                fonte["okx"] += 1
        if c.get("oi"):
            oi[base] = [tuple(x) for x in c["oi"]]
        if c.get("ls"):
            ls[base] = [tuple(x) for x in c["ls"]]
    macro = {k: [tuple(x) for x in v] for k, v in ((eu or {}).get("macro") or {}).items()}
    renascidos = {}
    try:
        if state_path and os.path.exists(state_path):
            with open(state_path) as f:
                renascidos = ((json.load(f).get("arena") or {}).get("renascidos")) or {}
    except Exception as e:
        print("estado ilegível:", e, file=sys.stderr)
    res = run(bars, cfg, now, days, bars1h=bars1h, funding=funding, oi=oi, macro=macro, ls=ls,
              renascidos=renascidos, regimes=longo)
    res["macro_series"] = sorted(macro)
    res["funding_moedas"] = len(funding)
    res["funding_fonte"] = fonte
    res["oi_moedas"] = len(oi)
    res["segundos"] = round(time.time() - t)
    res["falhas"] = falhas[:20]
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "longo.json" if longo else "forma.json"), "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res["lutadores"].items():
        print(f"{k:16s} n={v['n']:4d} R={v['avg_r']} acaso={v['acaso_mediana']}"
              f"/{v['acaso_p95']} -> {v['veredicto']}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else DAYS,
         sys.argv[3] if len(sys.argv) > 3 else None,
         longo=len(sys.argv) > 4 and sys.argv[4] == "longo")
