"""H60 (dados novos, REGISTADA 2026-11-11T23:39:10Z, antes de qualquer avaliacao) - LONG na subida de 3 dias feita
SEM alavancagem nova (numero de contratos abertos estavel ou a cair, financiamento nao elevado), so em mercado a subir
ou lateral.

Logica economica: uma subida conduzida por alavancagem (contratos a crescer, financiamento alto) depende de longs
alavancados que sao liquidados ao primeiro recuo; uma subida em que o numero de contratos NAO cresce e o financiamento
fica no nivel base foi paga por compradores sem alavancagem (a vista) ou por shorts a fechar, e nao deixa combustivel
de liquidacao por baixo. Num mercado que nao esta em descida, essa subida "limpa" tende a continuar mais do que a
alavancada. A parte de preco e momento de 3 dias (familia de momento/quebras chumbada nos dados antigos); o que se
testa e se o OI e o financiamento - campos que o historico antigo nao tinha - separam as subidas que continuam das que
falham. Por isso o criterio exige bater um grupo de controlo (mesma subida com contratos a crescer >= +10%) e uma
referencia ao acaso. Diferente da H57 (essa exige financiamento NEGATIVO e OI a subir) e da H59 (SHORT em descida).
Se chumbar, fecha a familia "momento filtrado por alavancagem" no lado LONG.

So le dados via tools/recolha_dados.py -> dados_para_avaliar(pasta, REGISTADA_EM). Regras fixas desde o registo;
nao mudar (uma mudanca e uma hipotese nova com data nova).
"""
import datetime
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
import recolha_dados as R  # noqa: E402

ID = "H60"
REGISTADA_EM = "2026-11-11T23:39:10Z"
MINIMO = 30
MINIMO_CONTROLO = 10

VOL_MIN, OI_XPERP_MIN = 10e6, 250e3   # universo: volume_usd do dia >= 10 M e oi_xperp >= 250 mil USD
JANELA = 10                           # regime e amplitude: 10 dias
REGIME_MIN = -0.02                    # mediana do retorno de 10 dias do universo >= -2% (subida ou lateral)
REGIME_MIN_MOEDAS = 30
SUBIDA = 0.08                         # c(D)/c(D-3) - 1 >= +8%
CONTRATOS_MAX = 0.0                   # (oi(D)/oi(D-3)) / (c(D)/c(D-3)) - 1 <= 0  (contratos nao crescem)
FUND_MAX = 0.0003                     # fund_xperp_24h(D) <= 0,03%/24 h (nivel base 0,01%/8 h)
CONTROLO_MIN = 0.10                   # controlo: mesma subida com contratos >= +10% (sem filtro de financiamento)
TAXA, DESLIZE = 0.0005, 0.0005        # taker OKX EEA e deslize, por lado
STOP_X, DIAS, MAX_POS = 1.5, 3, 5     # stop 1,5 x amplitude media; saida fecho D+3; max 5 posicoes
N_REF = 200


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def series(rows):
    por = {}
    for r in rows:
        por.setdefault(r["moeda"], {})[r["data"]] = r
    return por


def elegivel(r):
    return (_f(r.get("volume_usd")) or 0) >= VOL_MIN and (_f(r.get("oi_xperp")) or 0) >= OI_XPERP_MIN


def regime_ok(por, dias, i):
    if i < JANELA:
        return False
    d, d0 = dias[i], dias[i - JANELA]
    rets = [_f(s[d]["c"]) / _f(s[d0]["c"]) - 1 for s in por.values()
            if d in s and d0 in s and _f(s[d0]["c"]) and _f(s[d]["c"])]
    return len(rets) >= REGIME_MIN_MOEDAS and statistics.median(rets) >= REGIME_MIN


def amplitude(s, dias, i):
    a = [(_f(s[d]["h"]) - _f(s[d]["l"])) / _f(s[d]["c"]) for d in dias[max(0, i - 9): i + 1] if d in s and _f(s[d]["c"])]
    return sum(a) / len(a) if len(a) >= 5 else None


def candidatos(por, dias, i):
    """(variacao dos contratos em 3 dias, financiamento, moeda) das moedas elegiveis com a subida do sinal."""
    if i < 3:
        return []
    d, d3 = dias[i], dias[i - 3]
    out = []
    for m, s in por.items():
        r, r3 = s.get(d), s.get(d3)
        if not r or not r3 or not elegivel(r):
            continue
        c, c3, oi, oi3 = _f(r["c"]), _f(r3["c"]), _f(r["oi_usd_global"]), _f(r3["oi_usd_global"])
        if not (c and c3 and oi and oi3):
            continue
        if c / c3 - 1 >= SUBIDA:
            out.append(((oi / oi3) / (c / c3) - 1, _f(r["fund_xperp_24h"]), m))
    return out


def sinais(por, dias, i):
    return [m for v, fu, m in sorted(candidatos(por, dias, i)) if v <= CONTRATOS_MAX and fu is not None and fu <= FUND_MAX]


def controlo(por, dias, i):
    return [m for v, fu, m in sorted(candidatos(por, dias, i)) if v >= CONTROLO_MIN]


def operacao(s, dias, i):
    """Long taker na abertura de D+1; stop 1,5 x amplitude (pior de stop e abertura se saltar); senao fecho de D+3."""
    if i + DIAS >= len(dias) or any(dias[i + k] not in s for k in range(1, DIAS + 1)):
        return None
    amp, o1 = amplitude(s, dias, i), _f(s[dias[i + 1]]["o"])
    if not amp or not o1:
        return None
    e = o1 * (1 + DESLIZE)
    dist = STOP_X * amp
    stop = e * (1 - dist)
    fund, saida, motivo, kf = 0.0, None, "tempo", DIAS
    for k in range(1, DIAS + 1):
        r = s[dias[i + k]]
        f = _f(r["fund_xperp_24h"])
        if f is None:
            return None                                  # financiamento em falta: operacao nao avaliavel
        fund += f                                        # positivo: o long paga
        if _f(r["l"]) <= stop:
            saida, motivo, kf = min(stop, _f(r["o"])), "stop", k
            break
    if saida is None:
        saida = _f(s[dias[i + DIAS]]["c"])
    saida *= (1 - DESLIZE)
    pnl = saida / e - 1 - 2 * TAXA - fund
    return {"entrada_dia": dias[i + 1], "saida_dia": dias[i + kf], "motivo": motivo, "R": pnl / dist}


def correr(por, dias, escolher, max_pos, aleatorio=None):
    ops, ate = [], {}
    for i in range(len(dias)):
        if not regime_ok(por, dias, i):
            continue
        esc = escolher(por, dias, i)
        if aleatorio is not None and esc:
            pool = [m for m, s in por.items() if dias[i] in s and elegivel(s[dias[i]])]
            esc = aleatorio.sample(pool, min(len(esc), len(pool)))
        abertas = sum(1 for f in ate.values() if f > dias[i])
        for m in esc:
            if max_pos and abertas >= max_pos:
                break
            if ate.get(m, "") > dias[i]:
                continue
            op = operacao(por[m], dias, i)
            if op:
                op.update(moeda=m, sinal_dia=dias[i]); ops.append(op); ate[m] = op["saida_dia"]; abertas += 1
    return ops


def p_reamostragem(ops, n=2000, semente=60):
    """P(media <= 0) reamostrando DIAS de sinal inteiros."""
    rs = random.Random(semente)
    bl = {}
    for o in ops:
        bl.setdefault(o["sinal_dia"], []).append(o["R"])
    blocos = list(bl.values())
    return sum(statistics.mean([r for _ in blocos for r in rs.choice(blocos)]) <= 0 for _ in range(n)) / n


def avaliar(pasta, registada_em=REGISTADA_EM):
    rows = R.dados_para_avaliar(pasta, registada_em)
    por = series(rows)
    dias = sorted({r["data"] for r in rows})
    ops = correr(por, dias, sinais, MAX_POS)
    ctl = correr(por, dias, controlo, 0)
    n = len(ops)
    res = {"id": ID, "lado": "LONG", "dias_de_dados": len(dias), "operacoes": n, "minimo": MINIMO,
           "controlo": len(ctl), "minimo_controlo": MINIMO_CONTROLO}
    if n < MINIMO or len(ctl) < MINIMO_CONTROLO:
        res["estado"] = f"a acumular: {n} de {MINIMO} (controlo {len(ctl)} de {MINIMO_CONTROLO})"
        return res
    rs_ = sorted(o["R"] for o in ops)
    sem_top = rs_[:len(rs_) - max(1, round(0.05 * n))]
    meio = sorted(o["sinal_dia"] for o in ops)[n // 2]
    a = [o["R"] for o in ops if o["sinal_dia"] < meio]
    b = [o["R"] for o in ops if o["sinal_dia"] >= meio]
    ref = statistics.mean(statistics.mean([o["R"] for o in correr(por, dias, sinais, MAX_POS, random.Random(k))] or [0])
                          for k in range(N_REF))
    res.update(R_medio=statistics.mean(rs_), R_sem_5pct=statistics.mean(sem_top),
               R_medio_controlo=statistics.mean(o["R"] for o in ctl), referencia=ref,
               metade1=statistics.mean(a) if a else None, metade2=statistics.mean(b) if b else None,
               semanas=len({datetime.date.fromisoformat(o["sinal_dia"]).isocalendar()[:2] for o in ops}),
               dias_de_sinal=len({o["sinal_dia"] for o in ops}), p=p_reamostragem(ops))
    passa = (res["R_medio"] >= 0.10 and res["R_sem_5pct"] > 0 and res["R_medio"] > res["R_medio_controlo"]
             and res["R_medio"] > ref and (res["metade1"] or 0) > 0 and (res["metade2"] or 0) > 0
             and res["semanas"] >= 3 and res["dias_de_sinal"] >= 8 and res["p"] < 0.05)
    res["estado"] = "PASSA (so papel; a decisao e do Rui)" if passa else "CHUMBA"
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(avaliar(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dados-novos"), ensure_ascii=False))
