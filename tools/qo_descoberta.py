"""(17/11) Descoberta autonoma de hipoteses no Quick Opportunities (30 min, X-Perps da OKX, LONG e SHORT).

Gera uma grelha FIXA de 40 variantes (escrita aqui antes de correr), avalia todas com o mesmo metodo e corrige para
o numero total de hipoteses (Holm). Nao escolhe parametros a olhar para o teste. Rejeita, guarda e compara;
NUNCA aprova nada para producao (o maximo e "CANDIDATA A PAPEL", e o papel/real exige decisao do Rui).

Familias (cada uma em LONG e SHORT):
  rompimento   fecho alem do extremo de L velas com volume >= V x mediana de 20     L {10,20,40} x V {1.5,2.5}
  momentum     retorno de k velas >= x (continua no mesmo sentido)                  k {2,4} x x {1.5%,2.5%,4%}
  exaustao     o mesmo movimento, aposta na reversao (sentido contrario)            k {2,4} x x {1.5%,2.5%,4%}
  compressao   ATR14/ATR100 < c e fecho alem do extremo de 10 velas                  c {0.5,0.7}
Saida igual para todas: stop 1,5 ATR14, alvo 3 ATR14, 8 velas (4 h); entrada na abertura seguinte; custos 0,06% +
0,05% por lado (os de tools/qo_edge). Uma posicao de cada vez por moeda/variante.
Teste contra o acaso: Welch entre as operacoes reais do periodo de teste e um conjunto de entradas ao acaso
(5 por operacao, mesma moeda, mesmo periodo, mesmo lado, mesma geometria). Holm sobre TODAS as variantes.
Redundancia: entre candidatas, correlacao diaria das R > 0,7 -> fica a de maior media no teste.

Uso: python -m tools.qo_descoberta <series.json.gz> <saida.json>
"""
import gzip
import json
import math
import random
import sys
import time

from engine import quick_opportunities as QO
from tools import qo_edge as E

GRELHA = ([("rompimento", {"L": L, "V": V}) for L in (10, 20, 40) for V in (1.5, 2.5)]
          + [("momentum", {"k": k, "x": x}) for k in (2, 4) for x in (0.015, 0.025, 0.04)]
          + [("exaustao", {"k": k, "x": x}) for k in (2, 4) for x in (0.015, 0.025, 0.04)]
          + [("compressao", {"c": c}) for c in (0.5, 0.7)])
LADOS = ("LONG", "SHORT")
POR_OP_ACASO = 5


def _atr_serie(cs, p):
    out = [None] * len(cs)
    tr = [0.0] + [max(cs[i]["h"] - cs[i]["l"], abs(cs[i]["h"] - cs[i - 1]["c"]), abs(cs[i]["l"] - cs[i - 1]["c"]))
                  for i in range(1, len(cs))]
    s = 0.0
    for i in range(1, len(cs)):
        s += tr[i]
        if i > p:
            s -= tr[i - p]
        if i >= p:
            out[i] = s / p
    return out


def preparar(cs):
    return {"c": cs, "a14": _atr_serie(cs, 14), "a100": _atr_serie(cs, 100)}


def dispara(P, i, fam, prm, lado):
    cs = P["c"]
    c = cs[i]["c"]
    if fam == "rompimento":
        L = prm["L"]
        if i < max(L, 20) + 1:
            return False
        vol = sorted(b["v"] for b in cs[i - 20:i])[10]
        if vol <= 0 or cs[i]["v"] < prm["V"] * vol:
            return False
        return c > max(b["h"] for b in cs[i - L:i]) if lado == "LONG" else c < min(b["l"] for b in cs[i - L:i])
    if fam in ("momentum", "exaustao"):
        k = prm["k"]
        if i < k or cs[i - k]["c"] <= 0:
            return False
        r = c / cs[i - k]["c"] - 1
        sobe = r >= prm["x"]
        desce = r <= -prm["x"]
        if fam == "momentum":
            return sobe if lado == "LONG" else desce
        return desce if lado == "LONG" else sobe
    if fam == "compressao":
        a, b = P["a14"][i - 1] if i else None, P["a100"][i - 1] if i else None
        if not a or not b or a / b >= prm["c"] or i < 11:
            return False
        return c > max(x["h"] for x in cs[i - 10:i]) if lado == "LONG" else c < min(x["l"] for x in cs[i - 10:i])
    return False


def plano(P, i, lado):
    atr = P["a14"][i]
    if not atr:
        return None
    e = P["c"][i]["c"]
    risk = 1.5 * atr
    return {"side": lado, "stop": e - risk if lado == "LONG" else e + risk,
            "target": e + 2 * risk if lado == "LONG" else e - 2 * risk}


def operacoes(prep, fam, prm, lado, corte):
    ops = []
    for a, P in prep.items():
        cs = P["c"]
        livre = -1
        for i in range(101, len(cs) - 1):
            if i < livre or not dispara(P, i, fam, prm, lado):
                continue
            pl = plano(P, i, lado)
            if not pl:
                continue
            r = QO.simulate_candidate(cs, i, pl, fee_pct=E.FEE, slippage_pct=E.SLIP)
            if r.get("status") != "CLOSED":
                continue
            ops.append({"a": a, "i": i, "t": cs[i]["t"], "r": r["net_r"], "per": "teste" if cs[i]["t"] >= corte else "desenho"})
            livre = i + QO.MAX_HOLD_BARS + 1
    return ops


def acaso_r(prep, a, i0, i1, lado, rng):
    P = prep[a]
    for _ in range(20):
        i = rng.randrange(max(101, i0), max(102, i1))
        if i >= len(P["c"]) - 1:
            continue
        pl = plano(P, i, lado)
        if not pl:
            continue
        r = QO.simulate_candidate(P["c"], i, pl, fee_pct=E.FEE, slippage_pct=E.SLIP)
        if r.get("status") == "CLOSED":
            return r["net_r"]
    return None


def welch_p(xs, ys):
    """p unilateral de media(xs) > media(ys)."""
    if len(xs) < 2 or len(ys) < 2:
        return 1.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs) / (len(xs) - 1)
    vy = sum((y - my) ** 2 for y in ys) / (len(ys) - 1)
    se = math.sqrt(vx / len(xs) + vy / len(ys))
    if se <= 0:
        return 0.0 if mx > my else 1.0
    return 0.5 * math.erfc((mx - my) / se / math.sqrt(2))


def diario(ops):
    d = {}
    for o in ops:
        d[o["t"] // 86400] = d.get(o["t"] // 86400, 0.0) + o["r"]
    return d


def corr(d1, d2):
    ks = sorted(set(d1) | set(d2))
    if len(ks) < 10:
        return 0.0
    x = [d1.get(k, 0.0) for k in ks]
    y = [d2.get(k, 0.0) for k in ks]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else 0.0


def descobrir(series, corte, seed=7):
    rng = random.Random(seed)
    prep = {a: preparar(cs) for a, cs in series.items() if len(cs) > 150}
    cortes = {a: next((k for k, b in enumerate(P["c"]) if b["t"] >= corte), len(P["c"])) for a, P in prep.items()}
    res, guard = {}, {}
    for fam, prm in GRELHA:
        for lado in LADOS:
            nome = f"{fam} {' '.join(f'{k}={v}' for k, v in prm.items())} {lado}"
            ops = operacoes(prep, fam, prm, lado, corte)
            d = [o["r"] for o in ops if o["per"] == "desenho"]
            t = [o for o in ops if o["per"] == "teste"]
            tr = [o["r"] for o in t]
            ac = []
            for o in t:
                for _ in range(POR_OP_ACASO):
                    x = acaso_r(prep, o["a"], cortes[o["a"]], len(prep[o["a"]]["c"]), lado, rng)
                    if x is not None:
                        ac.append(x)
            meses = {}
            for o in t:
                meses.setdefault(time.strftime("%Y-%m", time.gmtime(o["t"])), []).append(o["r"])
            res[nome] = {"familia": fam, "lado": lado, "parametros": prm,
                         "n_desenho": len(d), "r_desenho": round(sum(d) / len(d), 4) if d else None,
                         "n_teste": len(tr), "r_teste": round(sum(tr) / len(tr), 4) if tr else None,
                         "r_acaso_teste": round(sum(ac) / len(ac), 4) if ac else None,
                         "p_contra_acaso": round(welch_p(tr, ac), 6),
                         "fracao_meses_positivos": (round(sum(1 for v in meses.values() if sum(v) > 0) / len(meses), 2)
                                                    if meses else None)}
            guard[nome] = diario(t)
    # Holm sobre todas as variantes
    ordem = sorted(res, key=lambda k: res[k]["p_contra_acaso"])
    m, acc = len(ordem), 0.0
    for j, k in enumerate(ordem):
        acc = max(acc, min(1.0, (m - j) * res[k]["p_contra_acaso"]))
        v = res[k]
        v["p_holm"] = round(acc, 6)
        ok = (v["n_teste"] >= E.MIN_OOS and (v["r_desenho"] or 0) > 0 and (v["r_teste"] or 0) > 0
              and v["p_holm"] < 0.05 and (v["fracao_meses_positivos"] or 0) >= 0.5)
        v["veredicto"] = ("CANDIDATA A PAPEL" if ok else "AMOSTRA INSUFICIENTE" if v["n_teste"] < E.MIN_OOS
                          else "REJEITADA (sem vantagem demonstrada)")
    # redundancia entre candidatas
    cands = sorted((k for k in res if res[k]["veredicto"] == "CANDIDATA A PAPEL"), key=lambda k: -res[k]["r_teste"])
    ficam = []
    for k in cands:
        par = next((f for f in ficam if corr(guard[k], guard[f]) > 0.7), None)
        if par:
            res[k]["veredicto"] = f"REDUNDANTE (correlacao > 0,7 com '{par}')"
        else:
            ficam.append(k)
    return res


def main(series_p, dest):
    with gzip.open(series_p, "rt") as f:
        S = json.load(f)
    series = S["series"]
    t0 = time.time()
    res = descobrir(series, S["corte"])
    out = {"variantes": len(res), "corte": S["corte"], "moedas": len(series), "segundos": round(time.time() - t0),
           "candidatas": [k for k, v in res.items() if v["veredicto"] == "CANDIDATA A PAPEL"], "resultados": res}
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    for k, v in sorted(r["resultados"].items(), key=lambda kv: kv[1]["p_holm"])[:15]:
        print(k, {q: v[q] for q in ("n_teste", "r_teste", "r_acaso_teste", "p_holm", "veredicto")})
