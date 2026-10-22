"""Auditoria S/R, Fibonacci, Key Levels e Canais (22/10). PRE-REGISTO, escrito antes de correr.

Existentes (regras ja no CryptoScan, sem afinar): BRK_ESPACO (rompimento de nivel com volume),
RETESTE (rompimento + reteste), FIBO_RECUO (recuo 50-61,8% em tendencia), REVERSAO_INTERVALO
(reversao no fundo de intervalo lateral), TURTLE (key level: maximo de 20 dias), SHORT_TURTLE
(key level: minimo de 20 dias, short), e os shorts espelho de BRK/RETESTE/FIBO/INTERVALO.
Novas (4 hipoteses, parametros fixos da literatura, sem otimizar):
  FALSO_ROMP     vela de 4H fura o minimo de 20 dias e fecha acima dele (recuperacao do nivel);
                 entra na abertura seguinte; stop 0,2 ATR abaixo do minimo da vela; 2R; max 5 dias.
  FALSO_ROMP_S   espelho (fura o maximo de 20 dias e fecha abaixo) em short.
  CANAL_REJ      canal de regressao linear de 30 dias (fechos diarios, +-2 desvios) com inclinacao
                 diaria menor que 0,5% (canal lateral ou suave); toque na banda de baixo nas ultimas
                 2 velas de 4H e fecho acima do maximo da vela anterior; objetivo = linha do meio;
                 stop 0,5 ATR abaixo do minimo de 3 velas; max 7 dias.
  CANAL_REJ_S    espelho em short.
Robustez do unico vencedor conhecido (SHORT_TURTLE): custos x2 e janelas de 15 e 30 dias.
Dados: 25 moedas com mais volume (/hist, 4H, 2021-2026), liquidez >= 5 M USD/dia na data.
Custos: 0,25% + 0,10% por lado (+ juro do emprestimo 20%/ano nos shorts). Compras so com o BTC
acima da media de 200 dias (como ao vivo); shorts sem esse filtro.
Periodos: A = 2021-06 a 2024-05 (desenho), B = 2024-06 a 2026-10 (fora da amostra).
Criterio APTA (o do H10): numa fase, nos DOIS periodos, R liquido por operacao >= +0,10,
R por dia > 0 e >= 15 dias distintos.
"""
import gzip, glob, os, sys, json, statistics
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import arena_ringue as AR
from engine import backtest as B, short as SH, trade
import engine.paper_bounce as PB

DAY, H4 = 86400, 14400
A0, A1 = 1622505600, 1717113600
B0, B1 = 1717200000, 1792022400
LIQ, APR = 5e6, 0.20


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


BTC = load("/tmp/claude-0/hist/BTC.csv.gz")
ABOVE = AR.btc_above(BTC)
ALWAYS = {k: True for k in ABOVE}
RMAP = AR.regime_by_day(BTC)


def _daily_closed(c4):
    return [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]


def sig_falso(c4):
    if len(c4) < 200:
        return None
    d = _daily_closed(c4)
    if len(d) < 25:
        return None
    lo = min(x["l"] for x in d[-21:-1])
    b = c4[-1]
    if not (b["l"] < lo < b["c"]):
        return None
    at = PB.atr(c4[-100:])[-1]
    if not at:
        return None
    e, stop = b["c"], b["l"] - 0.2 * at
    r = e - stop
    if r <= 0:
        return None
    return {"stop": stop, "tp": [e + 2 * r], "partials": [100], "breakeven": False, "hold_s": 5 * DAY, "atr": at}


def sig_canal(c4):
    if len(c4) < 250:
        return None
    d = _daily_closed(c4)
    if len(d) < 35:
        return None
    y = [x["c"] for x in d[-30:]]
    n = len(y); xm = (n - 1) / 2; ym = sum(y) / n
    sxx = sum((i - xm) ** 2 for i in range(n))
    slope = sum((i - xm) * (v - ym) for i, v in enumerate(y)) / sxx
    icp = ym - slope * xm
    res = [v - (icp + slope * i) for i, v in enumerate(y)]
    sd = (sum(e * e for e in res) / n) ** 0.5
    if not sd or abs(slope / ym) > 0.005:
        return None
    # projeta a linha para o dia atual (n)
    mid = icp + slope * n
    lower = mid - 2 * sd
    b, p = c4[-1], c4[-2]
    if not (min(b["l"], p["l"]) <= lower and b["c"] > p["h"] and b["c"] < mid):
        return None
    at = PB.atr(c4[-100:])[-1]
    if not at:
        return None
    e, stop = b["c"], min(x["l"] for x in c4[-3:]) - 0.5 * at
    if stop <= 0 or e - stop <= 0 or mid <= e * 1.005:
        return None
    return {"stop": stop, "tp": [mid], "partials": [100], "breakeven": False, "hold_s": 7 * DAY, "atr": at}


def turtle_n(n):
    def f(c4):
        d = _daily_closed(c4)
        if len(d) < max(25, n + 5):
            return None
        hi = max(x["h"] for x in d[-(n + 1):-1])
        if not (c4[-1]["c"] > hi >= c4[-2]["c"]):
            return None
        tr = [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"]) for k in range(len(d) - 20, len(d))]
        return AR._trend_plan(c4, c4[-1]["c"] - 2 * sum(tr) / 20)
    return f


# (nome, funcao sobre velas longas, e short?, multiplicador de custos)
TESTES = [
    ("BRK_ESPACO", AR.NEW_SIGS["BRK_ESPACO"], False, 1), ("BRK_ESPACO_S", AR.NEW_SIGS["BRK_ESPACO"], True, 1),
    ("RETESTE", AR.NEW_SIGS["RETESTE"], False, 1), ("RETESTE_S", AR.NEW_SIGS["RETESTE"], True, 1),
    ("FIBO_RECUO", AR.NEW_SIGS["FIBO_RECUO"], False, 1), ("FIBO_RECUO_S", AR.NEW_SIGS["FIBO_RECUO"], True, 1),
    ("REVERSAO_INTERVALO", AR.NEW_SIGS["REVERSAO_INTERVALO"], False, 1), ("REVERSAO_INTERVALO_S", AR.NEW_SIGS["REVERSAO_INTERVALO"], True, 1),
    ("TURTLE", AR.sig_turtle, False, 1), ("SHORT_TURTLE", AR.sig_turtle, True, 1),
    ("FALSO_ROMP", sig_falso, False, 1), ("FALSO_ROMP_S", sig_falso, True, 1),
    ("CANAL_REJ", sig_canal, False, 1), ("CANAL_REJ_S", sig_canal, True, 1),
    ("SHORT_TURTLE_custos_x2", AR.sig_turtle, True, 2),
    ("SHORT_TURTLE_15d", turtle_n(15), True, 1), ("SHORT_TURTLE_30d", turtle_n(30), True, 1),
]


def liquidez(c4):
    dv = {}
    for x in c4:
        dv[x["t"] // DAY] = dv.get(x["t"] // DAY, 0) + x["v"] * x["c"]
    out, j = {}, []
    for d in sorted(dv):
        j.append(dv[d]); j = j[-30:]
        out[d] = statistics.median(j)
    return out


def corre(a):
    c4 = load(f"/tmp/claude-0/hist/{a}.csv.gz"); m4 = SH.mirror(c4); lq = liquidez(c4)
    out = []
    for nome, fn, short, mult in TESTES:
        bars = m4 if short else c4
        AR.CTX.update(btc=BTC, bars={"BTC": BTC, a: c4}, daily={a: B.daily(bars)}, asset=a, funding={}, rank={})
        filt = ALWAYS if short else ABOVE
        busy = -1
        for i in range(250, len(bars) - 1):
            t_sig = bars[i]["t"] + H4
            if i < busy or t_sig < A0 or not AR._known(t_sig, filt):
                continue
            try:
                sig = fn(bars[:i + 1])
            except Exception:
                sig = None
            if not sig:
                continue
            px = bars[i + 1]["o"]
            if not (sig["stop"] < px < sig["tp"][0]):
                continue
            pos = trade.open_position(dict(sig, max_hold_s=None), px, bars[i + 1]["t"], PB.FEE_PCT * mult, PB.SLIP_PCT * mult,
                                      breakeven=sig.get("breakeven", True))
            k, fim = i + 1, None
            while not pos["closed"] and k < len(bars):
                x = bars[k]
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"])); trade._finish(pos, "TIME", x["t"] + H4)
                fim = x["t"] + H4; k += 1
            if not pos["closed"]:
                continue
            busy = k
            d = pos["opened_at"] // DAY
            if lq.get(d - 1, 0) < LIQ:
                continue
            dias = (fim - pos["opened_at"]) / DAY
            r = pos["r"]
            if short:
                stop = abs(sig["stop"] / px - 1)
                r -= APR * dias / 365 / stop if stop else 0
            out.append({"k": nome, "a": a, "t": pos["opened_at"], "r": r, "dias": dias, "fase": RMAP.get(d - 1)})
    return out


if __name__ == "__main__":
    vol = {}
    for p in glob.glob("/tmp/claude-0/hist/*.csv.gz"):
        a = os.path.basename(p).split(".")[0]; c = load(p); vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
    moedas = sorted(vol, key=lambda a: -vol[a])[:25]
    with Pool(2) as pool:
        T = [t for r in pool.map(corre, moedas) for t in r]
    json.dump(T, open("/tmp/claude-0/estudo/sr_trades.json", "w"))
    print("moedas:", ", ".join(moedas))
