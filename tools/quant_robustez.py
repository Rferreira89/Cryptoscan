"""(11/11) Bateria de robustez por estrategia e por AMBIENTE (real, papel, sombra e backtest nunca se misturam).

Entradas: operacoes de backtest com ativo (tools/quant_backtests.py --com-ativo) e a pasta com as copias publicas
(okx.json, state.json, scan.json, okx_tfshort*.json, derivados.json) lidas por backtest/quant/dados.py.
Para cada estrategia e ambiente: media em R, media sem as 5% melhores, teste da media pela soma diaria (dependencia),
bootstrap por blocos de dias, estabilidade em 4 blocos de tempo, ativos, regimes do BTC (so com o passado), DSR.
Entre as configuracoes de BACKTEST: correcao de Holm dos p-valores e walk-forward entre variantes vizinhas
(escolha so com o passado) contra a variante registada fixa. Sensibilidade entre variantes vizinhas.
Saida: JSON + Markdown. So R; nunca dinheiro. Nada daqui liga ou desliga estrategias.
Uso: python3 tools/quant_robustez.py <bt_ops.json> <pasta_publica> <saida.json> <saida.md>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest.quant import dados as D, dsr as S, estatistica as E, robustez as Rb  # noqa: E402

FAMILIAS = {"H40": ("H40 (panico do mercado)", "H40 (todos os sinais)"), "H46": ("H46 (RSI<30)", "H46 (RSI<35)")}
REGISTADA = {"H40": "H40 (panico do mercado)", "H46": "H46 (RSI<30)"}


def _grupos(ops):
    g = {}
    for o in ops:
        g.setdefault((o["ambiente"], o["estrategia"]), []).append(o)
    return g


def correr(bt, pasta, n_tentativas=None):
    btc = bt.get("btc_4h") or []
    ao_vivo = D.carregar(pasta)
    ops = list(bt["operacoes"]) + ao_vivo["operacoes"]
    if n_tentativas is None:
        n_tentativas = S.contar_tentativas(ao_vivo.get("forma"))
    nt = n_tentativas.get("conservador") if isinstance(n_tentativas, dict) else n_tentativas
    res, pv = {}, {}
    for (amb, est), xs in sorted(_grupos(ops).items()):
        a = Rb.avaliar(xs, btc if amb == "BACKTEST" else None, n_boot=1000 if amb == "BACKTEST" else 2000)
        rs = [o["R"] for o in sorted(xs, key=lambda o: o["t_entrada"])]
        try:
            a["dsr"] = S.dsr(rs, nt) if nt else None
        except Exception as e:                                   # amostra pequena: o dsr recusa e diz porque
            a["dsr"] = {"erro": str(e)[:80]}
        res[f"{amb} | {est}"] = a
        if amb == "BACKTEST" and a["teste_diario"]["p_unilateral"] is not None:
            pv[est] = a["teste_diario"]["p_unilateral"]
    holm = Rb.holm(pv) if pv else {}
    wf, sens = {}, {}
    por_est = {o["estrategia"]: [] for o in bt["operacoes"]}
    for o in bt["operacoes"]:
        por_est[o["estrategia"]].append(o)
    for fam, nomes in FAMILIAS.items():
        cfg = {n: por_est[n] for n in nomes if n in por_est}
        if len(cfg) < 2:
            continue
        w = Rb.walk_forward(cfg, treino_dias=365, teste_dias=90)
        oos = [o["R"] for o in w["oos"]]
        inicio = w["passos"][0]["teste_de"] if w["passos"] else 0
        fixa = [o["R"] for o in cfg[REGISTADA[fam]] if o["t_entrada"] >= inicio]
        wf[fam] = {"passos": len(w["passos"]), "escolhas": {n: sum(1 for p in w["passos"] if p.get("escolhida") == n) for n in cfg},
                   "oos_n": len(oos), "oos_media_r": round(E.media(oos), 4) if oos else None,
                   "oos_teste_diario": Rb.teste_media(Rb.por_dia(w["oos"]))[2] if w["oos"] else None,
                   "registada_fixa_mesmo_periodo_media_r": round(E.media(fixa), 4) if fixa else None, "registada": REGISTADA[fam]}
        sens[fam] = Rb.sensibilidade({n: [o["R"] for o in v] for n, v in cfg.items()})
    return {"gerado": int(time.time()), "n_tentativas": n_tentativas, "resultados": res, "holm_backtest": holm,
            "walk_forward": wf, "sensibilidade": sens, "notas": ao_vivo["notas"]}


def _f(x, n=3):
    return "—" if x is None else (f"{x:+.{n}f}" if isinstance(x, (int, float)) else str(x))


def markdown(r):
    L = ["# Robustez por estratégia e ambiente", "",
         f"Gerado {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(r['gerado']))}. Ambientes nunca somados. Só R.", "",
         "| Ambiente · estratégia | Operações | Dias | R médio | Sem 5% melhores | p (diário, unilateral) | Bootstrap IC95 | P(média ≤ 0) | Blocos positivos | DSR |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in r["resultados"].items():
        b = a["bootstrap_diario"]
        ds = a.get("dsr") or {}
        L.append(f"| {k} | {a['n_operacoes']} | {a['n_dias']} | {_f(a['media_r'])} | {_f(a['media_r_sem_5pct_melhores'])} | "
                 f"{_f(a['teste_diario']['p_unilateral'], 4)} | {b['ic'] if b.get('ic') else '—'} | {_f(b.get('p_nao_positivo'), 3)} | "
                 f"{(a['estabilidade'] or {}).get('positivos', '—')}/4 | {_f(ds.get('dsr'), 3) if isinstance(ds, dict) else '—'} |")
    L += ["", "## Holm (configurações de backtest)", "", "| Configuração | p | p ajustado | Rejeita H0 (5%) |", "|---|---|---|---|"]
    for k, v in r["holm_backtest"].items():
        L.append(f"| {k} | {v['p']:.4g} | {v['p_ajustado']:.4g} | {'sim' if v['rejeita'] else 'não'} |")
    L += ["", "## Walk-forward entre variantes vizinhas (treino 365 d, teste 90 d)", ""]
    for fam, w in r["walk_forward"].items():
        L.append(f"- {fam}: {w['passos']} passos, escolhas {w['escolhas']}; fora da amostra {w['oos_n']} operações, "
                 f"R médio {_f(w['oos_media_r'])} (p diário {_f(w['oos_teste_diario'], 4)}); registada fixa no mesmo período "
                 f"{_f(w['registada_fixa_mesmo_periodo_media_r'])}.")
    L += ["", "## Sensibilidade", ""]
    for fam, s in r["sensibilidade"].items():
        L.append(f"- {fam}: médias {s['medias']}; muda de sinal: {s['muda_de_sinal']}; frágil: {s['fragil']}.")
    L += ["", "## Notas", ""] + [f"- {n}" for n in r["notas"]]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    bt = json.load(open(sys.argv[1]))
    r = correr(bt, sys.argv[2])
    json.dump(r, open(sys.argv[3], "w"), indent=1, default=str)
    open(sys.argv[4], "w").write(markdown(r))
    print(markdown(r))
