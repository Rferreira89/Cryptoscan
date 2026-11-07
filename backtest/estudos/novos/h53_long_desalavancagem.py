"""H53 (dados novos, registada 2026-11-07T23:39Z) - LONG no recuo diario feito por desalavancagem (contratos abertos
a cair), so em mercado a subir ou lateral.

Logica economica: num mercado que nao esta em descida, um dia de queda moderada em que o NUMERO de contratos abertos
cai (OI em USD a cair mais do que o preco) foi feito por longs a fechar ou a ser liquidados, nao por vendedores novos.
Essa venda e mecanica e esgota-se quando a alavancagem sai; sem shorts novos a empurrar, o preco tende a recuperar nos
dias seguintes. E o complemento da H52 (OI a subir na queda = shorts novos = continuacao). A parte de preco e um recuo
(familia de recuos ja chumbada nos dados antigos); o que se testa e se o OI, dado que o historico antigo nao tinha,
separa os recuos bons dos maus. Por isso o criterio inclui um grupo de controlo: as mesmas quedas com contratos a
subir ou estaveis. Se chumbar, fecha a familia "recuo com desalavancagem".

So le dados via tools/recolha_dados.py -> dados_para_avaliar(pasta, REGISTADA_EM). Regras fixas desde o registo;
nao mudar (uma mudanca e uma hipotese nova com data nova).
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
import recolha_dados as R  # noqa: E402

ID = "H53"
REGISTADA_EM = "2026-11-07T23:39:18Z"
MINIMO = 30
MINIMO_CONTROLO = 10

# universo e regime
VOL_MIN = 10e6          # volume_usd do dia do sinal
OI_XPERP_MIN = 250e3    # open interest do X-Perp da OKX EEA (negociavel e com liquidez minima)
JANELA_REGIME = 10      # retorno de 10 dias de cada moeda
REGIME_MIN = -0.02      # mediana do retorno de 10 dias do universo >= -2%  (a subir ou lateral)
REGIME_MIN_MOEDAS = 30
# sinal (vela diaria D fechada)
QUEDA_MAX = -0.03       # c/o - 1 <= -3%
QUEDA_MIN = -0.08       # c/o - 1 >= -8%  (fora os colapsos/noticias)
CONTRATOS = -0.05       # (oi_usd(D)/oi_usd(D-1)) / (c(D)/c(D-1)) - 1 <= -5%  (contratos abertos a cair)
CONTROLO = 0.0          # controlo: mesma queda e contratos >= 0%
# execucao
STOP = 0.06             # stop 6% abaixo da entrada
DIAS = 3                # saida no fecho de D+3 se o stop nao tocar
MAX_POS = 5             # no maximo 5 posicoes abertas; desempate pela maior queda dos contratos
RISCO = 0.01            # 1% do capital por operacao -> nocional = RISCO / STOP
TAXA = 0.0005           # taker OKX EEA por lado
DESLIZE = 0.0005        # por lado


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _series(rows):
    por = {}
    for r in rows:
        por.setdefault(r["moeda"], {})[r["data"]] = r
    return por


def regime_ok(por, dias, i):
    """Mediana do retorno de JANELA_REGIME dias das moedas com os dois fechos >= REGIME_MIN, no dia dias[i]."""
    if i < JANELA_REGIME:
        return False
    d, d0 = dias[i], dias[i - JANELA_REGIME]
    rets = []
    for s in por.values():
        if d in s and d0 in s:
            c, c0 = _f(s[d]["c"]), _f(s[d0]["c"])
            if c and c0:
                rets.append(c / c0 - 1)
    return len(rets) >= REGIME_MIN_MOEDAS and statistics.median(rets) >= REGIME_MIN


def candidatos(por, dias, i):
    """(variacao dos contratos, moeda) das moedas elegiveis com a queda do sinal no dia dias[i]."""
    if not i:
        return []
    d, dp = dias[i], dias[i - 1]
    out = []
    for m, s in por.items():
        r, rp = s.get(d), s.get(dp)
        if not r or not rp:
            continue
        o, c, cp = _f(r["o"]), _f(r["c"]), _f(rp["c"])
        oi, oip = _f(r["oi_usd_global"]), _f(rp["oi_usd_global"])
        vol, oix = _f(r["volume_usd"]) or 0, _f(r["oi_xperp"]) or 0
        if not (o and c and cp and oi and oip) or vol < VOL_MIN or oix < OI_XPERP_MIN:
            continue
        if QUEDA_MIN <= c / o - 1 <= QUEDA_MAX:
            out.append(((oi / oip) / (c / cp) - 1, m))
    return out


def sinais(por, dias, i):
    return [m for v, m in sorted(candidatos(por, dias, i)) if v <= CONTRATOS]


def controlo(por, dias, i):
    return [m for v, m in sorted(candidatos(por, dias, i)) if v >= CONTROLO]


def operacao(s, dias, i):
    """Long a abertura de D+1; stop 6% (saida ao pior de stop e abertura se houver salto); senao fecho de D+3."""
    if i + DIAS >= len(dias) or any(dias[i + k] not in s for k in range(1, DIAS + 1)):
        return None
    e = _f(s[dias[i + 1]]["o"]) * (1 + DESLIZE)
    stop = e * (1 - STOP)
    fund = 0.0
    saida, motivo, k_fim = None, "tempo", DIAS
    for k in range(1, DIAS + 1):
        r = s[dias[i + k]]
        fund += _f(r["fund_xperp_24h"]) or 0.0          # positivo: o long paga
        if _f(r["l"]) <= stop:
            saida, motivo, k_fim = min(stop, _f(r["o"])), "stop", k
            break
    if saida is None:
        saida = _f(s[dias[i + DIAS]]["c"])
    saida *= (1 - DESLIZE)
    pnl = (saida - e) / e - 2 * TAXA - fund
    return {"entrada_dia": dias[i + 1], "saida_dia": dias[i + k_fim], "motivo": motivo, "R": pnl / STOP}


def _correr(por, dias, escolher, max_pos):
    ops, aberta_ate = [], {}
    for i in range(len(dias)):
        if not regime_ok(por, dias, i):
            continue
        abertas = sum(1 for fim in aberta_ate.values() if fim > dias[i])
        for m in escolher(por, dias, i):
            if max_pos and abertas >= max_pos:
                break
            if aberta_ate.get(m, "") > dias[i]:
                continue
            op = operacao(por[m], dias, i)
            if op:
                op.update(moeda=m, sinal_dia=dias[i])
                ops.append(op)
                aberta_ate[m] = op["saida_dia"]
                abertas += 1
    return ops


def avaliar(pasta, registada_em=REGISTADA_EM):
    rows = R.dados_para_avaliar(pasta, registada_em)
    por = _series(rows)
    dias = sorted({r["data"] for r in rows})
    ops = _correr(por, dias, sinais, MAX_POS)
    ctl = _correr(por, dias, controlo, 0)          # controlo sem limite de posicoes
    n = len(ops)
    res = {"id": ID, "dias_de_dados": len(dias), "operacoes": n, "minimo": MINIMO,
           "controlo": len(ctl), "minimo_controlo": MINIMO_CONTROLO}
    if n < MINIMO or len(ctl) < MINIMO_CONTROLO:
        res["estado"] = f"a acumular: {n} de {MINIMO} (controlo {len(ctl)} de {MINIMO_CONTROLO})"
        return res
    rs = sorted(o["R"] for o in ops)
    sem_top = rs[:len(rs) - max(1, round(0.05 * n))]
    semanas = {__import__("datetime").date.fromisoformat(o["sinal_dia"]).isocalendar()[:2] for o in ops}
    res.update(R_medio=sum(rs) / n, R_sem_5pct_melhores=sum(sem_top) / len(sem_top),
               R_medio_controlo=sum(o["R"] for o in ctl) / len(ctl),
               semanas=len(semanas), dias_de_sinal=len({o["sinal_dia"] for o in ops}))
    passa = (res["R_medio"] >= 0.10 and res["R_sem_5pct_melhores"] > 0 and res["R_medio"] > res["R_medio_controlo"]
             and res["semanas"] >= 3 and res["dias_de_sinal"] >= 8)
    res["estado"] = "PASSA" if passa else "CHUMBA"
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(avaliar(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dados-novos"), ensure_ascii=False))
