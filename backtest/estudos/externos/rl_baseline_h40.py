"""(11/11) Avaliacao da ideia do FinRL (aprendizagem por reforco) sem instalar o FinRL: um agente tabular minimo
(Q-learning de um passo, o caso "bandido contextual" que e o que esta decisao e) decide ENTRAR ou NAO em cada sinal da
H40, aprendendo so com o passado, num walk-forward. Investigacao isolada: nao toca em ordens, papel ou estrategias.

Porque nao o FinRL em si: precisa de ray, stable-baselines3/torch, elegantrl (git), wrds, alpaca e yfinance; o ambiente
virtual com o vectorbt ja ocupa ~0,7 GB. Se um agente minimo, com o mesmo problema e os mesmos dados, nao bate as
referencias simples, um agente profundo com mais parametros e ainda mais exposto ao sobreajustamento com 1 071
operacoes em ~257 dias.

Estado: (queda do BTC em 24 h em 4 faixas) x (BTC acima/abaixo da media de ~50 dias) x (sinais nesse dia: 1, 2-5, >5).
Recompensa: R da operacao (custos de futuros OKX ja incluidos). Exploracao epsilon 0,1 no treino; avaliacao gulosa.
Referencias no mesmo periodo fora da amostra: todas as operacoes; a regra registada (BTC <= -3%); nenhuma (0R);
BTC comprado e mantido (retorno no periodo, em %, nao em R: so como contexto).
Uso: python3 backtest/estudos/externos/rl_baseline_h40.py <bt_ops_ativo.json> <saida.json>"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from backtest.quant import robustez as Rb, estatistica as E  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from optuna_h40_wf import caracteristicas, DIA  # noqa: E402


def estado(o, n_dia):
    q = o["btc24"]
    fq = 0 if q > 0 else 1 if q > -0.03 else 2 if q > -0.06 else 3
    return (fq, o["btc_acima_ma"], 0 if n_dia <= 1 else 1 if n_dia <= 5 else 2)


def treinar(ops, epocas=30, alfa=0.1, eps=0.1, semente=7):
    rnd = random.Random(semente)
    Q = {}
    cont = {}
    for o in ops:
        cont[int(o["t_entrada"] // DIA)] = cont.get(int(o["t_entrada"] // DIA), 0) + 1
    for _ in range(epocas):
        for o in rnd.sample(ops, len(ops)):
            s = estado(o, cont[int(o["t_entrada"] // DIA)])
            q = Q.setdefault(s, [0.0, 0.0])                     # [nao entrar, entrar]
            a = rnd.randrange(2) if rnd.random() < eps else (1 if q[1] > q[0] else 0)
            r = o["R"] if a == 1 else 0.0
            q[a] += alfa * (r - q[a])
    return Q


def agir(Q, ops):
    cont = {}
    for o in ops:
        cont[int(o["t_entrada"] // DIA)] = cont.get(int(o["t_entrada"] // DIA), 0) + 1
    out = []
    for o in ops:
        q = Q.get(estado(o, cont[int(o["t_entrada"] // DIA)]))
        if q and q[1] > q[0]:
            out.append(o)
    return out


def correr(bt):
    btc = bt["btc_4h"]
    todos = caracteristicas([o for o in bt["operacoes"] if o["estrategia"] == "H40 (todos os sinais)"], btc)
    t0, t1 = min(o["t_entrada"] for o in todos), max(o["t_entrada"] for o in todos)
    a = t0 + 365 * DIA
    rl, tudo, reg, btc_ret = [], [], [], []
    while a < t1:
        b = a + 90 * DIA
        treino = [o for o in todos if a - 365 * DIA <= o["t_entrada"] and o["t_saida"] < a]
        teste = [o for o in todos if a <= o["t_entrada"] < b]
        rl += agir(treinar(treino), teste)
        tudo += teste
        reg += [o for o in teste if o["btc24"] <= -0.03]
        pa = [p for t, p in btc if a <= t < b]
        if pa:
            btc_ret.append(pa[-1] / pa[0] - 1)
        a = b

    def res(xs):
        if not xs:
            return {"n": 0}
        m, t, p, n = Rb.teste_media(Rb.por_dia(xs))
        return {"n": len(xs), "dias": n, "media_r": round(E.media([o["R"] for o in xs]), 4), "soma_r": round(sum(o["R"] for o in xs), 2),
                "p_diario": None if p is None else round(p, 4)}
    tot = 1.0
    for r in btc_ret:
        tot *= 1 + r
    return {"agente_tabular": res(rl), "todas": res(tudo), "regra_registada": res(reg), "nenhuma": {"n": 0, "soma_r": 0.0},
            "btc_comprado_e_mantido_pct": round(100 * (tot - 1), 1), "janelas": len(btc_ret)}


if __name__ == "__main__":
    r = correr(json.load(open(sys.argv[1])))
    json.dump(r, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(r, indent=1))
