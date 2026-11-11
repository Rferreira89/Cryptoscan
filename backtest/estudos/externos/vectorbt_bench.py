"""(11/11) Avaliacao do vectorbt (investigacao isolada; so corre num ambiente virtual com vectorbt instalado).

Pergunta: para comparar milhares de configuracoes, o vectorbt da os MESMOS resultados do que um ciclo simples em
numpy e quanto mais rapido e? Grelha de referencia (nao e uma estrategia nova, nao vai a papel nem a real):
  entrada na abertura da vela seguinte a uma queda de 3 dias (18 velas de 4H) <= -X; saida no fecho H velas
  depois; sem sobreposicao por ativo; custo 0,10% por lado; X em 15 valores (-6% a -20%), H em {6, 12, 18}.
Mede: tempo das duas implementacoes, igualdade do numero de operacoes e do retorno medio por configuracao.
Uso: <venv>/bin/python backtest/estudos/externos/vectorbt_bench.py <dir_history> <saida.json>"""
import glob
import gzip
import json
import os
import sys
import time

import numpy as np

CUSTO = 0.001


def carregar(hist, minimo=2000):
    out = {}
    for f in sorted(glob.glob(os.path.join(hist, "*.csv.gz"))):
        a = os.path.basename(f).split(".")[0]
        x = np.loadtxt(gzip.open(f, "rt"), delimiter=",", usecols=(0, 1, 4))
        if len(x) >= minimo:
            out[a] = x
    return out


def grelha():
    return [(x, h) for x in np.linspace(-0.06, -0.20, 15) for h in (6, 12, 18)]


def ciclo_numpy(dados, x, h):
    rets = []
    for a, d in dados.items():
        o, c = d[:, 1], d[:, 2]
        queda = np.full(len(c), np.nan)
        queda[18:] = c[18:] / c[:-18] - 1
        livre = -1
        sinais = np.nonzero(queda <= x)[0]
        for i in sinais:
            k = i + 1
            j = k + h - 1
            if k <= livre or j >= len(c):
                continue
            rets.append(c[j] * (1 - CUSTO) / (o[k] * (1 + CUSTO)) - 1)
            livre = j
    return len(rets), float(np.mean(rets)) if rets else None


def com_vectorbt(dados, combos):
    import pandas as pd
    import vectorbt as vbt
    out = {}
    # um DataFrame por ativo alinhado no tempo (colunas = ativos)
    idx = sorted({int(t) for d in dados.values() for t in d[:, 0]})
    pos = {t: i for i, t in enumerate(idx)}
    O = np.full((len(idx), len(dados)), np.nan)
    C = np.full((len(idx), len(dados)), np.nan)
    for j, d in enumerate(dados.values()):
        r = [pos[int(t)] for t in d[:, 0]]
        O[r, j], C[r, j] = d[:, 1], d[:, 2]
    O, C = pd.DataFrame(O), pd.DataFrame(C)
    queda = C / C.shift(18) - 1
    for x, h in combos:
        sinal = (queda <= x).shift(1, fill_value=False).astype(bool)          # entra na vela seguinte
        # saida por tempo: o vectorbt 1.2 (aberto) nao tem saida por numero de velas em from_signals (td_stop nao
        # existe nesta versao, medido); aproximacao: sinais de saida deslocados h-1 velas (pode fechar mais cedo
        # quando um sinal ignorado durante uma posicao gera uma saida; a diferenca fica medida abaixo).
        saida = sinal.shift(h - 1, fill_value=False).astype(bool)
        pf = vbt.Portfolio.from_signals(C, entries=sinal, exits=saida, price=O.where(~saida, C), fees=CUSTO, freq="4h")
        tr = pf.trades.records_readable
        out[(round(x, 4), h)] = (len(tr), float(tr["Return"].mean()) if len(tr) else None)
    return out


if __name__ == "__main__":
    dados = carregar(sys.argv[1])
    combos = grelha()
    t = time.time()
    ref = {(round(x, 4), h): ciclo_numpy(dados, x, h) for x, h in combos}
    t_np = time.time() - t
    t = time.time()
    try:
        vb = com_vectorbt(dados, combos)
        erro = None
    except Exception as e:
        vb, erro = {}, f"{type(e).__name__}: {str(e)[:200]}"
    t_vb = time.time() - t
    iguais = sum(1 for k in ref if k in vb and ref[k][0] == vb[k][0])
    dif = [abs((ref[k][1] or 0) - (vb[k][1] or 0)) for k in ref if k in vb and ref[k][1] is not None and vb[k][1] is not None]
    r = {"ativos": len(dados), "configuracoes": len(combos), "tempo_numpy_s": round(t_np, 2), "tempo_vectorbt_s": round(t_vb, 2),
         "configuracoes_mesmo_n": iguais, "maior_diferenca_media": max(dif) if dif else None, "erro_vectorbt": erro,
         "exemplos": {f"{k[0]}|{k[1]}": {"numpy": ref[k], "vectorbt": vb.get(k)} for k in list(ref)[:6]}}
    json.dump(r, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(r, indent=1))
