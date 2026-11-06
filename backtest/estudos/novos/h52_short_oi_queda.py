"""H52 (dados novos, registada 2026-11-06T23:39Z) - SHORT na queda diaria com open interest a subir, so em mercado
em descida.

Logica economica: numa queda diaria forte em que o open interest em USD SOBE (logo os contratos sobem ainda mais,
porque o preco caiu), entraram posicoes novas e a queda e conduzida por vendedores a abrir shorts, nao por longs a
fechar. Em mercado em descida isso tende a continuar alguns dias (pressao vendedora nova, nao capitulacao). A parte
de preco parece-se com as familias SHORT ja chumbadas; o que esta hipotese testa e se a confirmacao pelo OI (dado
que o historico antigo nao tinha) acrescenta vantagem. Se chumbar, fecha a familia "OI a confirmar a queda".

So le dados via tools/recolha_dados.py -> dados_para_avaliar(pasta, REGISTADA_EM). Regras fixas desde o registo;
nao mudar (uma mudanca e uma hipotese nova com data nova).
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
import recolha_dados as R  # noqa: E402

ID = "H52"
REGISTADA_EM = "2026-11-06T23:39:10Z"
MINIMO = 30

# universo e regime
VOL_MIN = 10e6          # volume_usd do dia do sinal
OI_XPERP_MIN = 250e3    # open interest do X-Perp da OKX EEA (negociavel e com liquidez minima)
JANELA_REGIME = 10      # retorno de 10 dias de cada moeda
REGIME_MAX = -0.03      # mediana do retorno de 10 dias do universo <= -3%  (mercado em descida)
REGIME_MIN_MOEDAS = 30
# sinal (vela diaria D fechada)
QUEDA = -0.04           # c/o - 1 <= -4%
OI_SUBIDA = 0.05        # oi_usd_global(D) / oi_usd_global(D-1) - 1 >= +5%
# execucao
STOP = 0.06             # stop 6% acima da entrada
DIAS = 3                # saida no fecho do 3.o dia (D+3) se o stop nao tocar
MAX_POS = 5             # no maximo 5 posicoes abertas; desempate pela maior subida do OI
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


def regime_descida(por, dias, i):
    """Mediana do retorno de JANELA_REGIME dias das moedas com os dois fechos, no dia dias[i]."""
    if i < JANELA_REGIME:
        return False
    d, d0 = dias[i], dias[i - JANELA_REGIME]
    rets = []
    for s in por.values():
        if d in s and d0 in s:
            c, c0 = _f(s[d]["c"]), _f(s[d0]["c"])
            if c and c0:
                rets.append(c / c0 - 1)
    return len(rets) >= REGIME_MIN_MOEDAS and statistics.median(rets) <= REGIME_MAX


def sinais(por, dias, i):
    d, dp = dias[i], dias[i - 1] if i else None
    out = []
    for m, s in por.items():
        r, rp = s.get(d), s.get(dp)
        if not r or not rp:
            continue
        o, c, oi, oip = _f(r["o"]), _f(r["c"]), _f(r["oi_usd_global"]), _f(rp["oi_usd_global"])
        vol, oix = _f(r["volume_usd"]) or 0, _f(r["oi_xperp"]) or 0
        if not (o and c and oi and oip) or vol < VOL_MIN or oix < OI_XPERP_MIN:
            continue
        if c / o - 1 <= QUEDA and oi / oip - 1 >= OI_SUBIDA:
            out.append((oi / oip - 1, m))
    return [m for _, m in sorted(out, reverse=True)]


def operacao(s, dias, i):
    """Short a abertura de D+1; stop 6% (saida ao pior de stop e abertura se houver salto); senao fecho de D+3."""
    if i + DIAS >= len(dias) or any(dias[i + k] not in s for k in range(1, DIAS + 1)):
        return None
    e = _f(s[dias[i + 1]]["o"]) * (1 - DESLIZE)
    stop = e * (1 + STOP)
    fund = 0.0
    saida, motivo, k_fim = None, "tempo", DIAS
    for k in range(1, DIAS + 1):
        r = s[dias[i + k]]
        fund += _f(r["fund_xperp_24h"]) or 0.0          # positivo: o short recebe
        if _f(r["h"]) >= stop:
            saida, motivo, k_fim = max(stop, _f(r["o"])), "stop", k
            break
    if saida is None:
        saida = _f(s[dias[i + DIAS]]["c"])
    saida *= (1 + DESLIZE)
    pnl = (e - saida) / e - 2 * TAXA + fund
    return {"entrada_dia": dias[i + 1], "saida_dia": dias[i + k_fim], "motivo": motivo, "R": pnl / STOP}


def avaliar(pasta, registada_em=REGISTADA_EM):
    rows = R.dados_para_avaliar(pasta, registada_em)
    por = _series(rows)
    dias = sorted({r["data"] for r in rows})
    ops, aberta_ate = [], {}
    for i in range(len(dias)):
        if not regime_descida(por, dias, i):
            continue
        abertas = sum(1 for fim in aberta_ate.values() if fim > dias[i])
        for m in sinais(por, dias, i):
            if abertas >= MAX_POS:
                break
            if aberta_ate.get(m, "") > dias[i]:
                continue
            op = operacao(por[m], dias, i)
            if op:
                op.update(moeda=m, sinal_dia=dias[i])
                ops.append(op)
                aberta_ate[m] = op["saida_dia"]
                abertas += 1
    n = len(ops)
    res = {"id": ID, "dias_de_dados": len(dias), "operacoes": n, "minimo": MINIMO}
    if n < MINIMO:
        res["estado"] = f"a acumular: {n} de {MINIMO}"
        return res
    rs = sorted(o["R"] for o in ops)
    sem_top = rs[:len(rs) - max(1, round(0.05 * n))]
    semanas = {__import__("datetime").date.fromisoformat(o["sinal_dia"]).isocalendar()[:2] for o in ops}
    res.update(R_medio=sum(rs) / n, R_sem_5pct_melhores=sum(sem_top) / len(sem_top),
               semanas=len(semanas), dias_de_sinal=len({o["sinal_dia"] for o in ops}))
    passa = res["R_medio"] >= 0.10 and res["R_sem_5pct_melhores"] > 0 and res["semanas"] >= 3 and res["dias_de_sinal"] >= 8
    res["estado"] = "PASSA" if passa else "CHUMBA"
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(avaliar(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dados-novos"), ensure_ascii=False))
