"""(11/11) Evidencia historica para o Global Opportunity Hunter: IC de postos (Spearman) transversal entre cada
caracteristica de velas e o retorno dos 3 dias SEGUINTES, com velas de 4H do ramo history (2021-2026).

Sem fuga de informacao: as caracteristicas usam a MESMA funcao da sombra (tools/cacador_global.caracteristicas_velas)
so com velas ate a vela k (fechada); o alvo comeca na abertura da vela k+1 e acaba no fecho da k+18. Amostras de
3 em 3 dias (alvos sem sobreposicao: observacoes diarias independentes no tempo). Correcao de Holm entre as
caracteristicas; IC em cada metade do periodo. Enviesamento de sobrevivencia: o universo sao as moedas que hoje
estao no ramo history (sem as retiradas); fica assinalado.
Uso: python3 backtest/estudos/novos/cacador_ic_historico.py <dir_history> <saida.json>"""
import glob
import json
import os
import sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from backtest.quant import robustez as Rb, estatistica as E  # noqa: E402
from engine import oportunidades as OP  # noqa: E402
import cacador_global as CG  # noqa: E402

CARACTERISTICAS = {
    "ret_3d": lambda x: x.get("ret_3d"),
    "aceleracao_24h": lambda x: (x["ret_24h"] / x["atr_pct"]) if x.get("ret_24h") is not None and x.get("atr_pct") else None,
    "residual_btc_24h": lambda x: x.get("residual_btc_24h"),
    "vol_ratio": lambda x: x.get("vol_ratio"),
    "volume_z": lambda x: OP._z(x.get("log_volume"), x.get("log_volume_hist") or []),
    "queda_correlacao": lambda x: (x["corr_btc_60d"] - x["corr_btc_7d"]) if x.get("corr_btc_60d") is not None and x.get("corr_btc_7d") is not None else None,
}


def quintis(linhas, nome, minimo=10):
    """Retorno medio de 3 dias do quintil mais BAIXO menos o mais ALTO da caracteristica, por dia (antes de custos).
    Positivo = comprar os mais baixos e vender os mais altos teria ganho (o sinal do IC negativo)."""
    por = {}
    for l in linhas:
        if l.get(nome) is not None:
            por.setdefault(l["dia"], []).append((l[nome], l["ret_seguinte"]))
    sp = []
    for d in sorted(por):
        v = sorted(por[d])
        if len(v) >= minimo:
            q = max(1, len(v) // 5)
            sp.append(sum(r for _, r in v[:q]) / q - sum(r for _, r in v[-q:]) / q)
    if len(sp) < 3:
        return None
    m = sum(sp) / len(sp)
    return {"dias": len(sp), "spread_medio_pct": round(100 * m, 3),
            "t": round(m / (E.desvio(sp) / len(sp) ** 0.5), 2) if E.desvio(sp) else None,
            "custo_ida_volta_dois_lados_pct": 0.4, "liquido_estimado_pct": round(100 * m - 0.4, 3)}


def correr(hist, passo_dias=3):
    btc = CG.ler_velas(os.path.join(hist, "BTC.csv.gz"))
    btc_t = {x[0]: x[4] for x in btc}
    linhas = []
    for f in sorted(glob.glob(os.path.join(hist, "*.csv.gz"))):
        a = os.path.basename(f).split(".")[0]
        if a == "BTC":
            continue
        v = CG.ler_velas(f)
        for k in range(360, len(v) - 19):
            t = v[k][0]
            if (t + 14400) % (86400 * passo_dias) != 0:              # fecho da vela k alinhado aos dias de amostra
                continue
            x = CG.caracteristicas_velas(v, k, btc_t)
            if not x:
                continue
            alvo = v[k + 18][4] / v[k + 1][1] - 1                    # abertura de k+1 ate ao fecho de k+18
            ln = {"dia": (t + 14400) // 86400, "ativo": a, "ret_seguinte": alvo}
            for nome, fn in CARACTERISTICAS.items():
                try:
                    ln[nome] = fn(x)
                except (TypeError, ZeroDivisionError):
                    ln[nome] = None
            linhas.append(ln)
    res, pv = {}, {}
    for nome in CARACTERISTICAS:
        ics = OP.ic_diario(linhas, nome)
        r = OP.resumo_ic(ics)
        xs = [i for _, i in ics]
        _, _, p, _ = Rb.teste_media(xs, unilateral=False) if len(xs) > 3 else (None, None, None, None)
        r["p_bilateral"] = None if p is None else round(p, 5)
        r["quintis_baixo_menos_alto"] = quintis(linhas, nome)
        res[nome] = r
        if p is not None:
            pv[nome] = p
    holm = Rb.holm(pv)
    for nome in res:
        res[nome]["holm"] = holm.get(nome)
        res[nome]["fonte"] = f"historico 4H ({len({l['ativo'] for l in linhas})} moedas)"
    return {"linhas": len(linhas), "moedas": len({l["ativo"] for l in linhas}), "passo_dias": passo_dias,
            "caracteristicas": res,
            "nota": "IC transversal de postos contra o retorno de 3 dias seguinte; nao e uma estrategia; nao inclui custos"}


if __name__ == "__main__":
    r = correr(sys.argv[1])
    json.dump(r, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(r, indent=1))
