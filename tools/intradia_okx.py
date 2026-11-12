"""(12/11, OK do Rui 07:29) Investigacao intradiaria LONG e SHORT na OKX com velas de 1h (ramo okx-1h).

So investigacao: le ficheiros, nao tem chaves, nao envia ordens.
Regras FIXAS, escritas antes de ver os resultados (nao se afinam depois):
  - entrada na abertura da vela seguinte ao sinal; stop a 2 x ATR(14) de 1h; objetivo 2R; saida ao fim de 24 h;
    o stop conta primeiro quando a mesma vela toca stop e objetivo (conservador);
  - uma posicao de cada vez por moeda e por estrategia;
  - custos dos X-Perps: 0,05% de comissao + 0,05% de deslize por lado, e financiamento de 0,01%/8 h pago pelos
    dois lados (conservador: o real varia por contrato e pode ser recebido);
  - familias (LONG e o espelho SHORT):
      MOMENTO      fecho acima do maximo de 24 h (abaixo do minimo) com volume >= 2x a media de 24 h;
      RECUO        tendencia (MME50 > MME200 e preco acima da MME200; espelho) e RSI(14) < 30 (> 70);
      REVERSAO     retorno de 6 h <= -6% (>= +6%) e a ultima vela fecha a favor da inversao;
      COMPRESSAO   largura das Bandas de Bollinger(20) no decil mais baixo das ultimas 500 velas e fecho fora da banda;
      FALSO_ROMPIMENTO  maxima acima do maximo de 24 h e fecho de volta abaixo dele -> SHORT (espelho -> LONG);
  - periodos por tempo: TREINO 1.a metade, VALIDACAO 3.o quarto, FORA ultimo quarto (de todas as velas);
  - acontecimento independente = dia UTC de entrada; criterio igual ao de tools/descoberta_long (os tres periodos
    positivos por dia com >= 15 dias, IC90 inferior > 0 em VALIDACAO+FORA e Holm < 0,05).
Limitacao assumida: so moedas que ainda tem X-Perp hoje (sem as retiradas): o vies de sobrevivencia FAVORECE os
LONG; um LONG que nao passa aqui tambem nao passaria com elas.
Uso: python -m tools.intradia_okx <pasta_okx_1h> <saida.json> [--min-velas 2000]"""
import gzip
import json
import math
import os
import random
import sys

from tools import descoberta_long as D

H = 3600
CUSTO_LADO = 0.001
FUNDING_8H = 0.0001
HOLD = 24
FAMILIAS = ("MOMENTO", "RECUO", "REVERSAO", "COMPRESSAO", "FALSO_ROMPIMENTO")


def carregar(p):
    out = []
    for l in gzip.open(p, "rt").read().split():
        z = l.split(",")
        if len(z) >= 6:
            out.append({"t": int(z[0]), "o": float(z[1]), "h": float(z[2]), "l": float(z[3]), "c": float(z[4]), "v": float(z[5])})
    out.sort(key=lambda x: x["t"])
    # so velas consecutivas de 1h (buracos partem a serie: os indicadores nao atravessam um buraco)
    return out


def mme(xs, n):
    k, out, m = 2 / (n + 1), [], None
    for x in xs:
        m = x if m is None else m + k * (x - m)
        out.append(m)
    return out


def indicadores(c):
    cl = [x["c"] for x in c]
    tr = [c[0]["h"] - c[0]["l"]] + [max(c[i]["h"], cl[i - 1]) - min(c[i]["l"], cl[i - 1]) for i in range(1, len(c))]
    atr, a = [], None
    for x in tr:
        a = x if a is None else a + (x - a) / 14
        atr.append(a)
    g = l_ = None
    rsi = []
    for i in range(len(cl)):
        d = cl[i] - cl[i - 1] if i else 0.0
        up, dn = max(d, 0), max(-d, 0)
        g = up if g is None else g + (up - g) / 14
        l_ = dn if l_ is None else l_ + (dn - l_) / 14
        rsi.append(100.0 if l_ == 0 else 100 - 100 / (1 + g / l_))
    e50, e200 = mme(cl, 50), mme(cl, 200)
    larg = []
    for i in range(len(cl)):
        if i < 19:
            larg.append(None)
            continue
        w = cl[i - 19:i + 1]
        m = sum(w) / 20
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
        larg.append((4 * sd / m if m else None, m + 2 * sd, m - 2 * sd))
    return {"atr": atr, "rsi": rsi, "e50": e50, "e200": e200, "bb": larg}


def decil(ind, i):
    """Decil mais baixo da largura das bandas nas 500 velas ANTES de i, recalculado de 24 em 24 velas (so passado)."""
    k = i - i % 24
    cache = ind.setdefault("_decil", {})
    if k not in cache:
        hist = sorted(b[0] for b in ind["bb"][max(0, k - 500):k] if b and b[0] is not None)
        cache[k] = hist[len(hist) // 10] if len(hist) >= 100 else None
    return cache[k]


def sinais(c, ind, i):
    """[(familia, lado)] com a vela i FECHADA (so dados ate i)."""
    if i < 500:
        return []
    out = []
    x, ant = c[i], c[i - 24:i]
    mx, mn = max(y["h"] for y in ant), min(y["l"] for y in ant)
    vm = sum(y["v"] for y in ant) / 24
    if vm > 0 and x["v"] >= 2 * vm:
        if x["c"] > mx:
            out.append(("MOMENTO", "LONG"))
        elif x["c"] < mn:
            out.append(("MOMENTO", "SHORT"))
    e50, e200, r = ind["e50"][i], ind["e200"][i], ind["rsi"][i]
    if e50 > e200 and x["c"] > e200 and r < 30:
        out.append(("RECUO", "LONG"))
    if e50 < e200 and x["c"] < e200 and r > 70:
        out.append(("RECUO", "SHORT"))
    r6 = x["c"] / c[i - 6]["c"] - 1
    if r6 <= -0.06 and x["c"] > x["o"]:
        out.append(("REVERSAO", "LONG"))
    if r6 >= 0.06 and x["c"] < x["o"]:
        out.append(("REVERSAO", "SHORT"))
    bb = ind["bb"][i]
    lim = decil(ind, i)
    if bb and bb[0] is not None and lim is not None and bb[0] <= lim:
        if x["c"] > bb[1]:
            out.append(("COMPRESSAO", "LONG"))
        elif x["c"] < bb[2]:
            out.append(("COMPRESSAO", "SHORT"))
    if x["h"] > mx and x["c"] < mx:
        out.append(("FALSO_ROMPIMENTO", "SHORT"))
    if x["l"] < mn and x["c"] > mn:
        out.append(("FALSO_ROMPIMENTO", "LONG"))
    return out


def simular(c, i, lado, atr):
    """Operacao com entrada na abertura de i+1. Devolve (R liquido, t_entrada, t_saida) ou None."""
    if i + 1 >= len(c) or atr <= 0:
        return None
    e = c[i + 1]["o"]
    s = 1 if lado == "LONG" else -1
    stop, alvo = e - s * 2 * atr, e + s * 4 * atr
    risco = abs(e - stop) / e
    if risco <= 0:
        return None
    sai, t_out = None, None
    for j in range(i + 1, min(i + 1 + HOLD, len(c))):
        b = c[j]
        if (s == 1 and b["l"] <= stop) or (s == -1 and b["h"] >= stop):
            sai, t_out = stop, b["t"] + H
            break
        if (s == 1 and b["h"] >= alvo) or (s == -1 and b["l"] <= alvo):
            sai, t_out = alvo, b["t"] + H
            break
    if sai is None:
        j = min(i + HOLD, len(c) - 1)
        if j <= i:
            return None
        sai, t_out = c[j]["c"], c[j]["t"] + H
    horas = (t_out - c[i + 1]["t"]) / H
    custo = 2 * CUSTO_LADO + FUNDING_8H * horas / 8
    r = (s * (sai / e - 1) - custo) / risco
    return r, c[i + 1]["t"], t_out


def operacoes(c, moeda):
    ind = indicadores(c)
    livre = {}
    out = []
    for i in range(500, len(c) - 1):
        if c[i]["t"] - c[i - 24]["t"] != 24 * H:
            continue                                         # buraco nas ultimas 24 h: nao se usa
        for fam, lado in sinais(c, ind, i):
            k = (fam, lado)
            if livre.get(k, 0) > c[i]["t"]:
                continue
            r = simular(c, i, lado, ind["atr"][i])
            if r is None:
                continue
            R, te, ts = r
            livre[k] = ts
            out.append({"k": f"{fam}_{lado}", "a": moeda, "t": te, "t_fim": ts, "r": R})
    return out


def avaliar(ops, t0, t1, reps=1000, seed=3):
    """Mesmo criterio da descoberta LONG, com os cortes deste periodo de dados."""
    rng = random.Random(seed)
    corte_v, corte_f = t0 + (t1 - t0) // 2, t0 + 3 * (t1 - t0) // 4
    linhas, ps = [], []
    for k in sorted({o["k"] for o in ops}):
        xs = [dict(o, R=o["r"]) for o in ops if o["k"] == k]
        tr = [o for o in xs if o["t"] < corte_v]
        va = [o for o in xs if corte_v <= o["t"] < corte_f]
        fo = [o for o in xs if o["t"] >= corte_f]
        R = {"treino": D.resumo(tr, "R", rng, reps), "validacao": D.resumo(va, "R", rng, reps),
             "fora": D.resumo(fo, "R", rng, reps), "validacao_mais_fora": D.resumo(va + fo, "R", rng, reps)}
        vf = R["validacao_mais_fora"]
        p = 1 - D.phi(vf["t_dia"]) if vf.get("t_dia") is not None else 1.0
        # (12/11) por dia E por operacao: com risco fixo por operacao (o caso real, ordem minima) um R por operacao
        # negativo perde dinheiro mesmo com R por dia positivo (os dias de muitos sinais perdem, os de poucos ganham)
        base = all(R[x].get("dias", 0) >= D.MIN_DIAS and (R[x].get("r_dia") or 0) > 0 and (R[x].get("r_op") or 0) > 0
                   for x in ("treino", "validacao", "fora")) and (vf.get("pf") or 0) > 1
        linhas.append({"estrategia": k, "lado": k.rsplit("_", 1)[1], "moedas": len({o["a"] for o in xs}), **R, "p": round(p, 5),
                       "_base": base})
        ps.append(p)
    for l, adj in zip(linhas, D.holm(ps) if ps else []):
        ic = (l["validacao_mais_fora"].get("ic90_dia") or [None])[0]
        l["p_holm"] = round(adj, 5)
        l["candidata"] = bool(l.pop("_base") and ic is not None and ic > 0 and adj < 0.05)
        l["classe"] = D.classe(l)
    return linhas, {"treino_ate": corte_v, "fora_desde": corte_f}


def correr(pasta, min_velas=2000):
    ops, usadas, t0, t1 = [], [], None, None
    for f in sorted(os.listdir(pasta)):
        if not f.endswith(".csv.gz"):
            continue
        c = carregar(os.path.join(pasta, f))
        if len(c) < min_velas:
            continue
        usadas.append(f[:-7])
        t0 = c[0]["t"] if t0 is None else min(t0, c[0]["t"])
        t1 = c[-1]["t"] if t1 is None else max(t1, c[-1]["t"])
        ops += operacoes(c, f[:-7])
    linhas, cortes = avaliar(ops, t0 or 0, t1 or 0) if ops else ([], {})
    return {"moedas": len(usadas), "operacoes": len(ops), "de": t0, "ate": t1, "cortes": cortes, "resultados": linhas,
            "aviso": "So investigacao; substituto a vista USDT para o preco do X-Perp; sem moedas retiradas."}


if __name__ == "__main__":
    a = sys.argv
    mv = int(a[a.index("--min-velas") + 1]) if "--min-velas" in a else 2000
    r = correr(a[1], mv)
    with open(a[2], "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print("moedas", r["moedas"], "operacoes", r["operacoes"])
    for l in r["resultados"]:
        vf = l["validacao_mais_fora"]
        print(f"{l['estrategia']:24s} T {l['treino'].get('r_dia')} ({l['treino'].get('dias')}) V {l['validacao'].get('r_dia')} "
              f"({l['validacao'].get('dias')}) F {l['fora'].get('r_dia')} ({l['fora'].get('dias')}) | V+F R/op {vf.get('r_op')} "
              f"R/dia {vf.get('r_dia')} {vf.get('ic90_dia')} pf {vf.get('pf')} dd {vf.get('max_dd_r')} holm {l['p_holm']} -> {l['classe']}")
