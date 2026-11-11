"""(2026-11-11, Fase 1) Verificacao de sobrevivencia da H46: corre o MESMO codigo do estudo pre-registado
(backtest/estudos/h46_recuo_tendencia.py, sinal, entrada, stop, objetivo, saida e custos) sobre TODAS as moedas de 4H de
uma pasta, incluindo as retiradas da bolsa (history-delistadas). O estudo original so via as moedas com funding (as
vivas). Acrescenta a cada operacao o ativo e a distancia do stop (2 x ATR42 / entrada, em %). So investigacao.
Precisa de numpy (como o estudo). Uso: python3 tools/h46_todas_moedas.py <pasta_4h> <saida.json>"""
import gzip, glob, os, sys, json, numpy as np
H4, DAY = 14400, 86400
pasta, saida = sys.argv[1], sys.argv[2]
def load(f):
    r = [l.split(",") for l in gzip.open(f, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6 and z[0][0].isdigit()])
dados = {}
for p in sorted(glob.glob(f"{pasta}/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    x = load(p)
    if len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    dados[a] = dict(t=t, o=o, h=h, l=l, c=c, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)])
src = open("backtest/estudos/h46_recuo_tendencia.py").read()
corpo = src.split("CUT2 = 1698796800")[1].split("    cand.sort()")[0]
corpo = corpo.replace("cand.append((int(d[\"t\"][k]), int(d[\"t\"][j]) + H4, R, int(d[\"t\"][i])))",
                      "cand.append((int(d[\"t\"][k]), int(d[\"t\"][j]) + H4, R, int(d[\"t\"][i]), a, float(2 * d['atr'][i] / e * 100)))")
assert "a, float(2" in corpo
corpo = corpo.replace("for L in (30, 35):\n    cand = []", "TODOS = {}\nfor L in (30, 35):\n    cand = []; TODOS[L] = cand")
g = {"np": np, "dados": dados, "H4": H4, "DAY": DAY}
exec(corpo, g)
ops = [{"ambiente": "BACKTEST", "estrategia": f"H46 (RSI<{L})", "t_entrada": x[0], "t_saida": x[1], "R": x[2], "ativo": x[4],
        "stop_pct": x[5], "nota": "h46 todas as moedas da pasta"} for L, cs in g["TODOS"].items() for x in cs]
json.dump({"operacoes": ops, "moedas": sorted(dados)}, open(saida, "w"))
print(len(dados), "moedas", {L: len(c) for L, c in g["TODOS"].items()})
