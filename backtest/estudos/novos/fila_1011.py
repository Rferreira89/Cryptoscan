"""H57, H58, H59 (dados novos; REGISTADAS 2026-11-10T06:30Z, antes de qualquer avaliacao). Fila de 10/11
(backtest/fila_hipoteses.md). Regras fixas desde o registo: uma mudanca e uma hipotese nova com data nova.
So le dados via tools/recolha_dados.py -> dados_para_avaliar(pasta, REGISTADA_EM).

H57 LONG "squeeze de shorts" (subida ou lateral): moeda com fecho acima da media de 10 dias, financiamento do X-Perp
    negativo em D e D-1 (shorts a pagar) e OI global a subir dois dias seguidos (D>D-1>D-2). Razao: posicionamento
    vendedor apertado numa moeda que sobe obriga os shorts a comprar. Contrario da H44 (excesso de longs).
H58 LONG "desalavancagem do mercado todo" (capitulacao): mediana do dia (c/o-1) do universo <= -6%, OI global somado do
    universo D/D-1-1 <= -8% e financiamento medio <= 0 -> long nas 5 moedas de maior volume. Razao: liquidacoes forcadas
    esgotam os vendedores; distingue o panico de desalavancagem (que a H40 nao distingue) do panico de noticias.
    Diferente da H53 (recuo moderado de UMA moeda em mercado a subir).
H59 SHORT "subida sem dinheiro novo" (descida): subida de 3 dias >= +10% com OI global de 3 dias <= -5% e financiamento
    > 0 -> short. Razao: subida feita de shorts a fechar (OI a cair), nao de compradores novos; em descida nao tem
    combustivel.
Comum: universo volume_usd >= 10 M e oi_xperp >= 250 mil; regime pela mediana do retorno de 10 dias do universo
(>= -2% subida/lateral; <= -2% descida; >= 30 moedas); entrada taker na abertura de D+1 (+0,05% deslize, 0,05% taxa
por lado); stop a 1,5 x amplitude diaria media de 10 dias; saida no fecho de D+3; financiamento real do X-Perp
(fund_xperp_24h) somado por dia em posicao; no maximo 5 posicoes por hipotese; uma por moeda.
Referencia simples: mesmas datas, moedas elegiveis ao acaso, mesma direcao (media de 200 sorteios).
CRITERIO (so com >= 30 operacoes): R medio >= +0,10; R sem as 5% melhores > 0; R medio > referencia; as duas metades
no tempo positivas (walk-forward simples: a 2.a metade e fora da 1.a); p de reamostragem por dias corrigido por Holm
entre as tres hipoteses < 0,05. Se chumbar, fica registado e a familia fecha."""
import datetime
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
import recolha_dados as R  # noqa: E402

REGISTADA_EM = "2026-11-10T06:30:00Z"
MINIMO = 30
VOL_MIN, OI_XPERP_MIN = 10e6, 250e3
JANELA = 10
TAXA, DESLIZE = 0.0005, 0.0005
STOP_X, DIAS, MAX_POS = 1.5, 3, 5


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


def regime(por, dias, i):
    if i < JANELA:
        return None
    d, d0 = dias[i], dias[i - JANELA]
    rets = [_f(s[d]["c"]) / _f(s[d0]["c"]) - 1 for s in por.values() if d in s and d0 in s and _f(s[d0]["c"])]
    if len(rets) < 30:
        return None
    m = statistics.median(rets)
    return "descida" if m <= -0.02 else "subida_lateral"


def amplitude(s, dias, i):
    a = [(_f(s[d]["h"]) - _f(s[d]["l"])) / _f(s[d]["c"]) for d in dias[max(0, i - 9): i + 1] if d in s and _f(s[d]["c"])]
    return sum(a) / len(a) if len(a) >= 5 else None


def _ok(s, dias, i, k):
    return all(dias[i - j] in s for j in range(k + 1)) if i >= k else False


def h57(por, dias, i):
    if regime(por, dias, i) != "subida_lateral":
        return []
    out = []
    for m, s in por.items():
        if not _ok(s, dias, i, JANELA) or not elegivel(s[dias[i]]):
            continue
        c = [_f(s[dias[i - j]]["c"]) for j in range(JANELA)]
        oi = [_f(s[dias[i - j]]["oi_usd_global"]) for j in range(3)]
        fu = [_f(s[dias[i - j]]["fund_xperp_24h"]) for j in range(2)]
        if None in c + oi + fu:
            continue
        if c[0] > sum(c) / len(c) and fu[0] < 0 and fu[1] < 0 and oi[0] > oi[1] > oi[2]:
            out.append((-(oi[0] / oi[2]), m))
    return [m for _, m in sorted(out)]


def h58(por, dias, i):
    if not i:
        return []
    d, dp = dias[i], dias[i - 1]
    univ = [(m, s) for m, s in por.items() if d in s and dp in s and elegivel(s[d])]
    if len(univ) < 30:
        return []
    quedas = [_f(s[d]["c"]) / _f(s[d]["o"]) - 1 for _, s in univ if _f(s[d]["o"])]
    oi_d = sum(_f(s[d]["oi_usd_global"]) or 0 for _, s in univ)
    oi_p = sum(_f(s[dp]["oi_usd_global"]) or 0 for _, s in univ)
    fund = [_f(s[d]["fund_xperp_24h"]) for _, s in univ if _f(s[d]["fund_xperp_24h"]) is not None]
    if not (quedas and oi_p and fund):
        return []
    if statistics.median(quedas) <= -0.06 and oi_d / oi_p - 1 <= -0.08 and statistics.mean(fund) <= 0:
        return [m for m, s in sorted(univ, key=lambda x: -(_f(x[1][d]["volume_usd"]) or 0))]
    return []


def h59(por, dias, i):
    if regime(por, dias, i) != "descida":
        return []
    out = []
    for m, s in por.items():
        if not _ok(s, dias, i, 3) or not elegivel(s[dias[i]]):
            continue
        c0, c3 = _f(s[dias[i]]["c"]), _f(s[dias[i - 3]]["c"])
        o0, o3 = _f(s[dias[i]]["oi_usd_global"]), _f(s[dias[i - 3]]["oi_usd_global"])
        fu = _f(s[dias[i]]["fund_xperp_24h"])
        if None in (c0, c3, o0, o3, fu) or not c3 or not o3:
            continue
        if c0 / c3 - 1 >= 0.10 and o0 / o3 - 1 <= -0.05 and fu > 0:
            out.append((-(c0 / c3), m))
    return [m for _, m in sorted(out)]


HIPOTESES = {"H57": (h57, "LONG"), "H58": (h58, "LONG"), "H59": (h59, "SHORT")}


def operacao(s, dias, i, lado):
    if i + DIAS >= len(dias) or any(dias[i + k] not in s for k in range(1, DIAS + 1)):
        return None
    amp = amplitude(s, dias, i)
    o1 = _f(s[dias[i + 1]]["o"])
    if not amp or not o1:
        return None
    sg = 1 if lado == "LONG" else -1
    e = o1 * (1 + sg * DESLIZE)
    dist = STOP_X * amp
    stop = e * (1 - sg * dist)
    fund, saida, motivo, kf = 0.0, None, "tempo", DIAS
    for k in range(1, DIAS + 1):
        r = s[dias[i + k]]
        f = _f(r["fund_xperp_24h"])
        if f is None:
            return None                                     # financiamento em falta: operacao nao avaliavel
        fund += f
        if (lado == "LONG" and _f(r["l"]) <= stop) or (lado == "SHORT" and _f(r["h"]) >= stop):
            saida = min(stop, _f(r["o"])) if lado == "LONG" else max(stop, _f(r["o"]))
            motivo, kf = "stop", k
            break
    if saida is None:
        saida = _f(s[dias[i + DIAS]]["c"])
    saida *= (1 - sg * DESLIZE)
    pnl = sg * (saida / e - 1) - 2 * TAXA - sg * fund     # long paga financiamento positivo; short recebe
    return {"entrada_dia": dias[i + 1], "saida_dia": dias[i + kf], "motivo": motivo, "R": pnl / dist}


def correr(por, dias, regra, lado, aleatorio=None):
    ops, ate = [], {}
    for i in range(len(dias)):
        esc = regra(por, dias, i)
        if aleatorio is not None and esc:
            pool = [m for m, s in por.items() if dias[i] in s and elegivel(s[dias[i]])]
            esc = aleatorio.sample(pool, min(len(esc), len(pool)))
        abertas = sum(1 for f in ate.values() if f > dias[i])
        for m in esc:
            if abertas >= MAX_POS:
                break
            if ate.get(m, "") > dias[i]:
                continue
            op = operacao(por[m], dias, i, lado)
            if op:
                op.update(moeda=m, sinal_dia=dias[i]); ops.append(op); ate[m] = op["saida_dia"]; abertas += 1
    return ops


def p_reamostragem(ops, n=2000, semente=11):
    """P(media <= 0) reamostrando DIAS de sinal inteiros (sinais do mesmo dia sao a mesma aposta)."""
    rs = random.Random(semente)
    bl = {}
    for o in ops:
        bl.setdefault(o["sinal_dia"], []).append(o["R"])
    blocos = list(bl.values())
    cont = 0
    for _ in range(n):
        amostra = [r for _ in blocos for r in rs.choice(blocos)]
        cont += statistics.mean(amostra) <= 0
    return cont / n


def holm(ps):
    """ps: {id: p}. Devolve {id: p ajustado de Holm}."""
    ordem = sorted(ps.items(), key=lambda x: x[1])
    m, out, maxi = len(ordem), {}, 0.0
    for k, (h, p) in enumerate(ordem):
        maxi = max(maxi, min(1.0, (m - k) * p))
        out[h] = maxi
    return out


def avaliar(pasta, registada_em=REGISTADA_EM):
    rows = R.dados_para_avaliar(pasta, registada_em)
    por = series(rows)
    dias = sorted({r["data"] for r in rows})
    res, ps = {}, {}
    for h, (regra, lado) in HIPOTESES.items():
        ops = correr(por, dias, regra, lado)
        n = len(ops)
        x = {"id": h, "lado": lado, "dias_de_dados": len(dias), "operacoes": n, "minimo": MINIMO}
        if n < MINIMO:
            x["estado"] = f"a acumular: {n} de {MINIMO}"
            res[h] = x
            continue
        rs_ = sorted(o["R"] for o in ops)
        sem_top = rs_[:len(rs_) - max(1, round(0.05 * n))]
        meio = sorted(o["sinal_dia"] for o in ops)[n // 2]
        a = [o["R"] for o in ops if o["sinal_dia"] < meio]; b = [o["R"] for o in ops if o["sinal_dia"] >= meio]
        ref = statistics.mean(statistics.mean([o["R"] for o in correr(por, dias, regra, lado, random.Random(k))] or [0])
                              for k in range(200))
        g, p_ = sum(r for r in rs_ if r > 0), -sum(r for r in rs_ if r < 0)
        eq = pico = queda = 0.0
        for o in sorted(ops, key=lambda o: o["saida_dia"]):
            eq += o["R"]; pico = max(pico, eq); queda = max(queda, pico - eq)
        x.update(R_medio=statistics.mean(rs_), R_sem_5pct=statistics.mean(sem_top), PF=g / p_ if p_ else None,
                 queda_R=queda, referencia=ref, metade1=statistics.mean(a) if a else None,
                 metade2=statistics.mean(b) if b else None,
                 semanas=len({datetime.date.fromisoformat(o["sinal_dia"]).isocalendar()[:2] for o in ops}))
        ps[h] = p_reamostragem(ops)
        res[h] = x
    for h, pa in holm(ps).items():
        x = res[h]
        x["p_holm"] = pa
        passa = (x["R_medio"] >= 0.10 and x["R_sem_5pct"] > 0 and x["R_medio"] > x["referencia"]
                 and (x["metade1"] or 0) > 0 and (x["metade2"] or 0) > 0 and pa < 0.05)
        x["estado"] = "PASSA (so papel; a decisao e do Rui)" if passa else "CHUMBA"
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(avaliar(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dados-novos"), ensure_ascii=False, default=str))
