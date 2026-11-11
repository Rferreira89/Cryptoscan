"""(11/11) Avaliacao do Optuna (investigacao isolada; so corre num ambiente virtual com optuna instalado; o
CryptoScan nao passa a depender dele).

Pergunta: afinar o filtro da H40 com o Optuna, DENTRO de um walk-forward, melhora o resultado FORA da amostra em
relacao a regra registada (BTC a cair >= 3% nas 6 velas de 4H ate ao sinal)?

Populacao: as 1 071 operacoes de BACKTEST da H40 com todos os sinais (custos de futuros OKX, h38), com hora e ativo.
Parametros procurados (por passo, so com o treino):
  queda_btc   - limite da queda do BTC em 24 h ate ao sinal, de -10% a 0%;
  max_dia     - maximo de operacoes por dia (as primeiras pela hora), 1 a 20 (concentracao);
  btc_vs_ma   - exigir o BTC abaixo/acima da media de ~50 dias ou indiferente.
Objetivo multiobjetivo (NSGA-II): media da soma diaria de R e pior queda acumulada (em R) no treino; escolhe da
fronteira o ponto com melhor media penalizada pelo erro padrao. Treino 365 d, teste 90 d, deslizante.
Caracteristicas do BTC usam so velas FECHADAS antes da entrada (sem olhar para o futuro).
Saida: JSON com o fora da amostra afinado contra a regra registada no mesmo periodo e o numero de tentativas
(para o DSR).
Uso: python3 backtest/estudos/externos/optuna_h40_wf.py <bt_ops_ativo.json> <saida.json> [tentativas_por_passo]"""
import bisect
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from backtest.quant import robustez as Rb, estatistica as E  # noqa: E402

H4, DIA = 14400, 86400


def caracteristicas(ops, btc):
    ts = [x[0] for x in btc]
    cs = [x[1] for x in btc]
    out = []
    for o in ops:
        k = bisect.bisect_right(ts, o["t_entrada"] - H4) - 1          # ultima vela de 4H fechada antes da entrada
        if k < 300:
            continue
        ma = sum(cs[k - 299:k + 1]) / 300
        out.append({**o, "btc24": cs[k] / cs[k - 6] - 1, "btc_acima_ma": cs[k] > ma})
    return out


def filtrar(ops, p):
    sel, por_dia = [], {}
    for o in sorted(ops, key=lambda o: o["t_entrada"]):
        if o["btc24"] > p["queda_btc"]:
            continue
        if p["btc_vs_ma"] == "abaixo" and o["btc_acima_ma"]:
            continue
        if p["btc_vs_ma"] == "acima" and not o["btc_acima_ma"]:
            continue
        d = int(o["t_entrada"] // DIA)
        if por_dia.get(d, 0) >= p["max_dia"]:
            continue
        por_dia[d] = por_dia.get(d, 0) + 1
        sel.append(o)
    return sel


def objetivos(ops):
    dia = Rb.por_dia(ops)
    if len(dia) < 8:
        return -1.0, -50.0
    acum = pico = dd = 0.0
    for r in dia:
        acum += r
        pico = max(pico, acum)
        dd = min(dd, acum - pico)
    return E.media(dia), dd


def afinar(treino, n_trials, semente):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def obj(t):
        p = {"queda_btc": t.suggest_float("queda_btc", -0.10, 0.0), "max_dia": t.suggest_int("max_dia", 1, 20),
             "btc_vs_ma": t.suggest_categorical("btc_vs_ma", ["indiferente", "abaixo", "acima"])}
        return objetivos(filtrar(treino, p))
    est = optuna.create_study(directions=["maximize", "maximize"], sampler=optuna.samplers.NSGAIISampler(seed=semente))
    est.optimize(obj, n_trials=n_trials)
    melhor, nota = None, -1e9
    for t in est.best_trials:
        sel = filtrar(treino, t.params)
        dia = Rb.por_dia(sel)
        if len(dia) < 8:
            continue
        n = E.media(dia) - E.desvio(dia) / math.sqrt(len(dia))
        if n > nota:
            melhor, nota = t.params, n
    return melhor, len(est.trials)


def correr(bt, n_trials=60):
    btc = bt["btc_4h"]
    todos = caracteristicas([o for o in bt["operacoes"] if o["estrategia"] == "H40 (todos os sinais)"], btc)
    registada = {"queda_btc": -0.03, "max_dia": 10 ** 6, "btc_vs_ma": "indiferente"}
    t0, t1 = min(o["t_entrada"] for o in todos), max(o["t_entrada"] for o in todos)
    a, passos, oos_af, oos_reg, tentativas = t0 + 365 * DIA, [], [], [], 0
    while a < t1:
        b = a + 90 * DIA
        treino = [o for o in todos if a - 365 * DIA <= o["t_entrada"] and o["t_saida"] < a]
        teste = [o for o in todos if a <= o["t_entrada"] < b]
        p, n = afinar(treino, n_trials, semente=int(a) % 1000)
        tentativas += n
        af = filtrar(teste, p) if p else []
        rg = filtrar(teste, registada)
        oos_af += af
        oos_reg += rg
        passos.append({"teste_de": a, "parametros": p, "n_treino": len(treino), "oos_afinada_n": len(af),
                       "oos_afinada_media": round(E.media([o["R"] for o in af]), 4) if af else None,
                       "oos_registada_n": len(rg), "oos_registada_media": round(E.media([o["R"] for o in rg]), 4) if rg else None})
        a = b

    def res(xs):
        if not xs:
            return {"n": 0}
        m, t, p, n = Rb.teste_media(Rb.por_dia(xs))
        return {"n": len(xs), "dias": n, "media_r": round(E.media([o["R"] for o in xs]), 4),
                "media_diaria": None if m is None else round(m, 4), "p_diario": None if p is None else round(p, 4),
                "bootstrap": Rb.bootstrap_blocos(Rb.por_dia(xs), n_boot=1000)}
    return {"passos": passos, "tentativas_optuna": tentativas, "fora_da_amostra_afinada": res(oos_af),
            "fora_da_amostra_registada": res(oos_reg)}


if __name__ == "__main__":
    bt = json.load(open(sys.argv[1]))
    r = correr(bt, int(sys.argv[3]) if len(sys.argv) > 3 else 60)
    json.dump(r, open(sys.argv[2], "w"), indent=1)
    print(json.dumps({k: v for k, v in r.items() if k != "passos"}, indent=1))
    for p in r["passos"]:
        print(p)
