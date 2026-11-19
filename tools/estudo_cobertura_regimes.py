"""(19/11, ordem do Rui, ponto 2) Cobertura da Bybit UE por regime: hipoteses NOVAS pre-registadas (parametros
escritos antes de correr, sem afinar) e o classificador de regime do proprio sistema.

So investigacao (backtest em preco real): nao gera sinais nem ordens.

Hipoteses (4H; entrada na abertura da vela seguinte; uma posicao por moeda):
  B1 SHORT pullback em tendencia descendente: moeda com fecho diario < SMA50 < SMA200 (dias fechados); a vela de 4H
     toca a EMA20(4H) por baixo (maximo >= EMA20) e fecha abaixo dela e abaixo da abertura -> short. Stop: maximo das
     6 ultimas velas + 0,25 ATR(4H, 14). Objetivo 2R. Prazo 5 dias.
  B2 SHORT perda de suporte com reteste: fecho de 4H abaixo do minimo dos 20 dias completos (nivel N); nas 12 velas
     seguintes o preco volta a tocar N (maximo >= N) e fecha abaixo de N -> short. Stop: maximo dessa vela + 0,25 ATR.
     Objetivo 2R. Prazo 5 dias.
  U1 LONG pullback em tendencia ascendente (espelho de B1): fecho diario > SMA50 > SMA200; a vela toca a EMA20 por
     cima (minimo <= EMA20), fecha acima dela e acima da abertura -> long. Stop: minimo das 6 velas - 0,25 ATR.
     Objetivo 2R. Prazo 5 dias.
  L1 reversao nos extremos de um intervalo: |fecho/SMA50 - 1| < 5% (sem tendencia); a vela de 4H passa o maximo
     (minimo) dos 20 dias completos e fecha de novo dentro, com pavio maior do que o corpo -> short (long). Stop: o
     extremo da vela + 0,25 ATR. Objetivo: o meio do intervalo de 20 dias (se der < 1R, nao entra). Prazo 3 dias.
Custos da Bybit UE medidos a 19/11: comissao 0,25% por lado (maker = taker), deslize 0,07% por lado, juro do
emprestimo por moeda (tabela publica do motor; 0,03%/dia quando falta) para os shorts. Stop: conta o salto de
abertura; mesma vela com stop e objetivo conta o stop.
Universos: 'executavel' = moedas com emprestimo na Bybit UE (shorts) / listadas no scan (longs); 'largo' = todas as
moedas do historico, incluindo deslistadas (sem vies de sobrevivencia).
Validacao: dois periodos fixos (A: ate 2024-06-30; B: depois), regime do BTC do proprio motor
(engine.arena.market_regime) no dia do sinal, IC 90% por bootstrap em blocos de DIA, referencia ao acaso (mesma
moeda, mesmo lado, mesma geometria de stop/objetivo/prazo, em velas sorteadas do mesmo regime).
Uso: python3 -m tools.estudo_cobertura_regimes <pasta_4h> <saida.json> [juros.json]"""
import bisect
import json
import random
import sys
import time

from engine import arena, backtest as B

H4, DAY = 14400, 86400
FEE, SLIP = 0.0025, 0.0007
JURO_FALTA = 0.0003
CORTE = 1719705600                 # 2024-06-30
EXECUTAVEL_SHORT = {"AAVE", "ADA", "AERO", "APT", "ARB", "ASTER", "AVAX", "AVNT", "BNB", "BONK", "BTC", "CRV", "DOGE",
                    "DOT", "ENA", "ETH", "HBAR", "HYPE", "LINK", "LTC", "MNT", "ONDO", "PEPE", "POPCAT", "RENDER", "S",
                    "SEI", "SHIB", "SOL", "SUI", "TRUMP", "TRX", "UNI", "VIRTUAL", "WIF", "WLD", "XLM", "XRP", "ZORA"}


def ema(xs, n):
    k, e, out = 2 / (n + 1), xs[0], []
    for x in xs:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def atr_serie(c, n=14):
    tr = [c[0]["h"] - c[0]["l"]] + [max(c[i]["h"], c[i - 1]["c"]) - min(c[i]["l"], c[i - 1]["c"]) for i in range(1, len(c))]
    out, s = [], 0.0
    for i, x in enumerate(tr):
        s += x
        if i >= n:
            s -= tr[i - n]
        out.append(s / min(i + 1, n))
    return out


class Diario:
    """Dias fechados ate ao fecho de uma vela de 4H (sem olhar para a frente)."""

    def __init__(self, c4):
        self.d = B.daily(c4)
        self.t = [x["t"] for x in self.d]
        cs = [x["c"] for x in self.d]
        self.s50 = [sum(cs[max(0, i - 49):i + 1]) / min(i + 1, 50) for i in range(len(cs))]
        self.s200 = [sum(cs[max(0, i - 199):i + 1]) / min(i + 1, 200) for i in range(len(cs))]

    def ate(self, t_fecho):
        return bisect.bisect_right(self.t, t_fecho - DAY)          # numero de dias completos


def sinais(a, c, dd):
    """[(hip, i, lado, stop, alvo, prazo_s)] com a vela i fechada."""
    out = []
    cl = [x["c"] for x in c]
    e20 = ema(cl, 20)
    at = atr_serie(c)
    pend = []                                                     # quebras de suporte a espera do reteste (B2)
    for i in range(30, len(c) - 1):
        b = c[i]
        k = dd.ate(b["t"] + H4)
        if k < 210:
            continue
        dc, s50, s200 = dd.d[k - 1]["c"], dd.s50[k - 1], dd.s200[k - 1]
        w20 = dd.d[k - 20:k]
        lo20, hi20 = min(x["l"] for x in w20), max(x["h"] for x in w20)
        A = at[i]
        if not A:
            continue
        # B1 / U1
        if dc < s50 < s200 and b["h"] >= e20[i] > b["c"] and b["c"] < b["o"]:
            st = max(x["h"] for x in c[i - 5:i + 1]) + 0.25 * A
            out.append(("B1", i, -1, st, None, 5 * DAY))
        if dc > s50 > s200 and b["l"] <= e20[i] < b["c"] and b["c"] > b["o"]:
            st = min(x["l"] for x in c[i - 5:i + 1]) - 0.25 * A
            out.append(("U1", i, 1, st, None, 5 * DAY))
        # B2: quebra e reteste
        if b["c"] < lo20 <= c[i - 1]["c"]:
            pend.append((i, lo20))
        pend = [(j, n) for j, n in pend if i - j <= 12]
        for j, n in list(pend):
            if j < i and b["h"] >= n > b["c"]:
                out.append(("B2", i, -1, b["h"] + 0.25 * A, None, 5 * DAY))
                pend.remove((j, n))
                break
        # L1
        if abs(dc / s50 - 1) < 0.05:
            corpo = abs(b["c"] - b["o"])
            meio = (hi20 + lo20) / 2
            if b["h"] > hi20 and b["c"] < hi20 and (b["h"] - max(b["c"], b["o"])) > corpo:
                out.append(("L1", i, -1, b["h"] + 0.25 * A, meio, 3 * DAY))
            elif b["l"] < lo20 and b["c"] > lo20 and (min(b["c"], b["o"]) - b["l"]) > corpo:
                out.append(("L1", i, 1, b["l"] - 0.25 * A, meio, 3 * DAY))
    return out


def simular(c, i, lado, stop, alvo, prazo, juro_dia):
    if i + 1 >= len(c):
        return None
    e = c[i + 1]["o"] * (1 + lado * SLIP)
    dist = lado * (e - stop)
    if dist <= 0:
        return None
    if alvo is None:
        alvo = e + lado * 2 * dist
    elif lado * (alvo - e) < dist:                                  # L1: objetivo a menos de 1R, nao entra
        return None
    risco = dist + FEE * (e + stop)
    t0, mae, mfe = c[i + 1]["t"], 0.0, 0.0
    for j in range(i + 1, len(c)):
        b = c[j]
        tf = b["t"] + H4
        dias = (tf - t0) / DAY
        custo_j = (juro_dia * dias * e) if lado < 0 else 0.0
        mae = min(mae, (lado * ((b["l"] if lado > 0 else b["h"]) - e)) / risco)
        mfe = max(mfe, (lado * ((b["h"] if lado > 0 else b["l"]) - e)) / risco)
        hit_stop = (b["l"] <= stop) if lado > 0 else (b["h"] >= stop)
        hit_alvo = (b["h"] >= alvo) if lado > 0 else (b["l"] <= alvo)
        if hit_stop:
            px = (min(stop, b["o"]) if lado > 0 else max(stop, b["o"])) * (1 - lado * SLIP)
            mot = "stop"
        elif hit_alvo:
            px, mot = alvo, "objetivo"
        elif tf - t0 >= prazo:
            px, mot = b["c"] * (1 - lado * SLIP), "tempo"
        else:
            continue
        r = (lado * (px - e) - FEE * (e + px) - custo_j) / risco
        return {"r": r, "motivo": mot, "dur_s": tf - t0, "mae": mae, "mfe": mfe,
                "custo_r": (FEE * (e + px) + custo_j + SLIP * (e + px)) / risco}
    return None


def boot(por_dia, n=1500, seed=19):
    dias = [v for v in por_dia.values() if v]
    if len(dias) < 8:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(n):
        xs = [x for _ in dias for x in dias[rng.randrange(len(dias))]]
        ms.append(sum(xs) / len(xs))
    ms.sort()
    return [round(ms[int(0.05 * n)], 3), round(ms[int(0.95 * n)], 3)]


def resumo(ops):
    if not ops:
        return {"n": 0}
    rs = [o["r"] for o in ops]
    pd = {}
    for o in ops:
        pd.setdefault(o["t"] // DAY, []).append(o["r"])
    g, p = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    eq = pico = dd = 0.0
    for o in sorted(ops, key=lambda o: o["t"]):
        eq += o["r"]
        pico = max(pico, eq)
        dd = min(dd, eq - pico)
    return {"n": len(rs), "dias_independentes": len(pd), "media_r": round(sum(rs) / len(rs), 3), "ic90": boot(pd),
            "pf": round(g / p, 2) if p else None, "acerto_pct": round(100 * sum(r > 0 for r in rs) / len(rs), 1),
            "drawdown_r": round(dd, 1), "custo_medio_r": round(sum(o["custo_r"] for o in ops) / len(ops), 3),
            "mae_media": round(sum(o["mae"] for o in ops) / len(ops), 2), "mfe_media": round(sum(o["mfe"] for o in ops) / len(ops), 2),
            "moedas": len({o["ativo"] for o in ops})}


def regimes_btc(btc4):
    d = B.daily(btc4)
    out = {}
    for k in range(200, len(d) + 1):
        out[d[k - 1]["t"] + DAY] = arena.market_regime(btc1d=d[:k])    # regime conhecido no fim do dia k-1
    return out


def estudo_regime(reg):
    """Mudancas do classificador: quantas, quanto duram, e o que o BTC fez a seguir (60 dias)."""
    ts = sorted(reg)
    seq = [(t, reg[t]) for t in ts]
    trocas, dur, ini = [], {}, seq[0]
    for (t0, r0), (t1, r1) in zip(seq, seq[1:]):
        if r1 != r0:
            trocas.append((t1, r0, r1))
            dur.setdefault(r0, []).append((t1 - ini[0]) / DAY)
            ini = (t1, r1)
    dias = {}
    for _, r in seq:
        dias[r] = dias.get(r, 0) + 1
    curtas = sum(1 for v in dur.values() for x in v if x < 7)
    return {"dias_por_regime": dias, "trocas": len(trocas), "trocas_em_menos_de_7_dias": curtas,
            "duracao_media_dias": {k: round(sum(v) / len(v), 1) for k, v in dur.items()},
            "ultimas_trocas": [(time.strftime("%Y-%m-%d", time.gmtime(t)), a, b) for t, a, b in trocas[-8:]]}


def correr(pasta, juros=None):
    data, _ = B.load_all(pasta, min_bars=1300)
    reg = regimes_btc(data["BTC"])
    regt = sorted(reg)

    def regime(t):
        k = bisect.bisect_right(regt, t) - 1
        return reg[regt[k]] if k >= 0 else None

    rng = random.Random(7)
    ops = []
    for a, c in data.items():
        dd = Diario(c)
        jd = float((juros or {}).get(a, JURO_FALTA * 100)) / 100
        ocupado = {}
        for hip, i, lado, st, alvo, prazo in sinais(a, c, dd):
            t_sig = c[i]["t"] + H4
            if t_sig < ocupado.get(hip, 0):
                continue
            s = simular(c, i, lado, st, alvo, prazo, jd)
            if not s:
                continue
            ocupado[hip] = c[i + 1]["t"] + s["dur_s"]
            rg = regime(t_sig)
            o = dict(s, hip=hip, ativo=a, t=t_sig, lado=lado, regime=rg, acaso=False,
                     executavel=(a in EXECUTAVEL_SHORT) if lado < 0 else True)
            ops.append(o)
            # acaso: mesma moeda, lado e geometria (distancia do stop em %, objetivo em R, prazo) numa vela sorteada
            # do mesmo regime
            for _ in range(20):
                j = rng.randrange(220, len(c) - 2)
                if regime(c[j]["t"] + H4) != rg:
                    continue
                e0 = c[i + 1]["o"]
                fr = abs(st / e0 - 1)
                ej = c[j + 1]["o"]
                st_j = ej * (1 - lado * fr)
                alvo_j = None if alvo is None else ej * (alvo / e0)
                s2 = simular(c, j, lado, st_j, alvo_j, prazo, jd)
                if s2:
                    ops.append(dict(s2, hip=hip, ativo=a, t=c[j]["t"] + H4, lado=lado, regime=rg, acaso=True,
                                    executavel=o["executavel"]))
                break
    out = {}
    for hip in ("B1", "B2", "U1", "L1"):
        for lado in (1, -1):
            for uni in ("executavel", "largo"):
                for rg in ("subida", "queda", "lateral", "todos"):
                    g = [o for o in ops if o["hip"] == hip and o["lado"] == lado and (uni == "largo" or o["executavel"])
                         and (rg == "todos" or o["regime"] == rg)]
                    if not g:
                        continue
                    k = f"{hip}|{'LONG' if lado > 0 else 'SHORT'}|{uni}|{rg}"
                    out[k] = {"A_ate_2024_06": resumo([o for o in g if not o["acaso"] and o["t"] < CORTE]),
                              "B_depois": resumo([o for o in g if not o["acaso"] and o["t"] >= CORTE]),
                              "tudo": resumo([o for o in g if not o["acaso"]]),
                              "acaso_tudo": resumo([o for o in g if o["acaso"]])}
    return {"regime": estudo_regime(reg), "resultados": out, "moedas": len(data)}


if __name__ == "__main__":
    juros = None
    if len(sys.argv) > 3:
        j = json.load(open(sys.argv[3]))
        juros = j.get("m", j)
    t0 = time.time()
    r = correr(sys.argv[1], juros)
    r["segundos"] = round(time.time() - t0, 1)
    r["custos"] = {"comissao_lado": FEE, "deslize_lado": SLIP, "juro_falta_dia": JURO_FALTA}
    with open(sys.argv[2], "w") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(r["moedas"], r["segundos"])
