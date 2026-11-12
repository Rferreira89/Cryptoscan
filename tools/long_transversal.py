"""(12/11, ordem do Rui 09:06: "linha LONG permanente e independente") Motor LONG TRANSVERSAL: compara as moedas entre
si em cada dia (o ringue avalia cada moeda sozinha). Familias novas, com regras ESCRITAS ANTES de ver resultados:

  FORCA_RELATIVA   BTC acima da media de 200 dias; moeda acima da sua media de 50; as 3 de maior forca relativa a
                   20 dias face ao BTC (e > 0). Saida: 10 dias ou stop de 2 ATR14 diario.
  ROTACAO          so a segunda-feira; BTC acima da media de 200; entre as 50 mais liquidas, as 3 de maior subida a
                   7 dias. Saida: 7 dias ou stop de 2,5 ATR.
  ESTRUTURA_FLUXO  combinacao: forca relativa 20d no decil de cima E forca relativa 60d > 0 E volume 7d/30d >= 1,5
                   E fecho >= 90% do maximo de 60 dias E acima da media de 50. Sem filtro do BTC (a fase decide).
                   Saida: 15 dias ou stop de 2 ATR.
  RESILIENCIA      o BTC caiu >= 10% em 10 dias e fecha acima dos 3 fechos anteriores (inicio de recuperacao): as 3
                   moedas que melhor aguentaram a queda (forca relativa 10d > 0). Saida: 10 dias ou stop de 2 ATR.
  ACELERACAO       subida a 7 dias > 10% e > metade da de 20 dias, volume 7d/30d >= 2, BTC acima da media de 50.
                   Saida: 5 dias ou stop de 2 ATR.

Sem olhar para o futuro: sinal no fecho do dia d com dados ate d; entrada na abertura de d+1; stop pelo minimo do
dia (sai ao preco do stop, ou a abertura se abrir abaixo); saida por tempo no fecho. Uma operacao aberta por moeda e
familia. Liquidez por data (mediana 30 dias >= 5 M USD na vespera). Custos Bybit UE 0,35%/lado (comissao+deslize)
no R; a avaliacao (tools/descoberta_long.avaliar: periodos fixos, dias independentes, bootstrap, Holm, PF, R/op)
acrescenta a coluna OKX. Universo: todas as moedas com historia, incluindo as retiradas; a coluna bybit_ue usa so as
moedas com par USDC na Bybit UE (lista lida da conta publica), sem misturar a Bybit internacional.
Uso: python3 -m tools.long_transversal <pasta_4h> <saida.json> [--bybit lista.json]"""
import json
import os
import sys

from tools import descoberta_long as DL

DAY = 86400
CUSTO_BYBIT = 0.007                       # ida e volta, fracao do preco
FAMILIA = "transversal (entre moedas)"
ESTAVEIS = {"USDC", "FDUSD", "TUSD", "DAI", "USDP", "EUR", "BUSD", "USDE", "PYUSD", "USD1", "RLUSD"}


def diario(c4):
    d = {}
    for x in c4:
        k = x["t"] // DAY
        if k not in d:
            d[k] = {"t": k * DAY, "o": x["o"], "h": x["h"], "l": x["l"], "c": x["c"], "v": x["v"] * x["c"], "n": 1}
        else:
            y = d[k]
            y["h"], y["l"], y["c"] = max(y["h"], x["h"]), min(y["l"], x["l"]), x["c"]
            y["v"] += x["v"] * x["c"]
            y["n"] += 1
    return [d[k] for k in sorted(d) if d[k]["n"] >= 6]


def indicadores(dd):
    """{dia: {...}} so com dados ate esse dia."""
    out, c = {}, [x["c"] for x in dd]
    trs = []
    for i, x in enumerate(dd):
        pc = dd[i - 1]["c"] if i else x["o"]
        trs.append(max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc)))
        if i < 60:
            continue
        v7 = sum(y["v"] for y in dd[i - 6:i + 1]) / 7
        v30 = sum(y["v"] for y in dd[i - 29:i + 1]) / 30
        vols = sorted(y["v"] for y in dd[i - 29:i + 1])
        out[x["t"] // DAY] = {
            "i": i, "c": x["c"], "r7": c[i] / c[i - 7] - 1, "r10": c[i] / c[i - 10] - 1, "r20": c[i] / c[i - 20] - 1,
            "r60": c[i] / c[i - 60] - 1, "ma50": sum(c[i - 49:i + 1]) / 50, "atr": sum(trs[i - 13:i + 1]) / 14,
            "max60": max(y["h"] for y in dd[i - 59:i + 1]), "fluxo": v7 / v30 if v30 > 0 else 0.0,
            "liq": vols[len(vols) // 2],
            "ma200": sum(c[i - 199:i + 1]) / 200 if i >= 199 else None,
            "c3": max(c[i - 3:i]) if i >= 3 else None}
    return out


def sair(dd, i_ent, stop, h):
    """Entrada na abertura de dd[i_ent]; devolve (preco de saida, t_fim) por stop ou tempo."""
    for j in range(i_ent, min(len(dd), i_ent + h)):
        x = dd[j]
        if x["o"] <= stop:
            return x["o"], x["t"]
        if x["l"] <= stop:
            return stop, x["t"] + DAY // 2
    j = min(len(dd), i_ent + h) - 1
    return dd[j]["c"], dd[j]["t"] + DAY - 1


def sinais(dia, ind, btc):
    """{familia: [moedas]} para o fecho deste dia, so com dados passados. ind: {moeda: {dia: indicadores}}."""
    b = btc.get(dia)
    if not b:
        return {}
    viv = {a: v[dia] for a, v in ind.items() if dia in v and v[dia]["liq"] >= DL.LIQ}
    out = {}
    rs = {a: x["r20"] - b["r20"] for a, x in viv.items()}
    if b["ma200"] and b["c"] > b["ma200"]:
        fr = sorted((a for a, x in viv.items() if x["c"] > x["ma50"] and rs[a] > 0), key=lambda a: -rs[a])[:3]
        out["FORCA_RELATIVA"] = fr
        if dia % 7 == 4:                                   # 1970-01-01 foi quinta: dia % 7 == 4 e segunda
            top = sorted(viv, key=lambda a: -viv[a]["liq"])[:50]
            out["ROTACAO"] = sorted((a for a in top if viv[a]["r7"] > 0), key=lambda a: -viv[a]["r7"])[:3]
    if len(viv) >= 10:
        corte = sorted(rs.values())[int(0.9 * len(rs))]
        out["ESTRUTURA_FLUXO"] = [a for a, x in viv.items() if rs[a] >= corte and x["r60"] - b["r60"] > 0
                                  and x["fluxo"] >= 1.5 and x["c"] >= 0.9 * x["max60"] and x["c"] > x["ma50"]]
    if b["r10"] <= -0.10 and b["c3"] and b["c"] > b["c3"]:
        rs10 = {a: x["r10"] - b["r10"] for a, x in viv.items()}
        out["RESILIENCIA"] = sorted((a for a in viv if rs10[a] > 0), key=lambda a: -rs10[a])[:3]
    if b["c"] > b["ma50"]:
        out["ACELERACAO"] = [a for a, x in viv.items() if x["r7"] > 0.10 and x["r7"] > 0.5 * x["r20"] and x["fluxo"] >= 2]
    return out


REGRAS = {"FORCA_RELATIVA": (10, 2.0), "ROTACAO": (7, 2.5), "ESTRUTURA_FLUXO": (15, 2.0), "RESILIENCIA": (10, 2.0),
          "ACELERACAO": (5, 2.0)}


def operacoes(series, fases):
    """series: {moeda: [velas diarias]} (com BTC). Devolve operacoes no formato de tools/descoberta_long."""
    ind = {a: indicadores(dd) for a, dd in series.items() if a not in ESTAVEIS}
    btc = ind.pop("BTC", {})
    aberta = {}
    out = []
    for dia in sorted(btc):
        for k, moedas in sinais(dia, ind, btc).items():
            h, m_atr = REGRAS[k]
            for a in moedas:
                if a == "BTC" or aberta.get((k, a), 0) > dia:
                    continue
                dd, x = series[a], ind[a][dia]
                i_ent = x["i"] + 1
                if i_ent >= len(dd):
                    continue
                ent = dd[i_ent]["o"]
                stop = ent - m_atr * x["atr"]
                if stop <= 0 or ent <= 0:
                    continue
                px, t_fim = sair(dd, i_ent, stop, h)
                frac = (ent - stop) / ent
                r = (px / ent - 1 - CUSTO_BYBIT) / frac
                aberta[(k, a)] = t_fim // DAY + 1
                out.append({"k": k, "fam": FAMILIA, "a": a, "t": int(dd[i_ent]["t"]), "t_fim": int(t_fim),
                            "r": round(r, 5), "stop": round(frac, 5), "fase": fases.get(dia)})
    return out


def correr(pasta, saida=None, bybit=None):
    from tools import arena_ringue as AR
    series, btc4 = {}, None
    for f in sorted(os.listdir(pasta)):
        if not f.endswith(".csv.gz"):
            continue
        a = f[:-7]
        try:
            c4 = DL.carregar(os.path.join(pasta, f))
        except OSError:
            continue
        if a == "BTC":
            btc4 = c4
        dd = diario(c4)
        if len(dd) >= 90:
            series[a] = dd
    fases = AR.regime_by_day(btc4)
    ops = operacoes(series, fases)
    btc_px = {x["t"]: x["c"] for x in btc4}
    linhas, red = DL.avaliar([dict(o) for o in ops], btc_px)
    res = {"moedas": len(series), "operacoes": len(ops), "resultados": linhas, "redundantes": red}
    if bybit:
        so = [o for o in ops if o["a"] in bybit]
        lb, _ = DL.avaliar([dict(o) for o in so], btc_px)
        res["so_bybit_ue"] = {"moedas": len({o["a"] for o in so}), "operacoes": len(so),
                              "resultados": [l for l in lb if l["corretora"] == "bybit_ue"]}
    if saida:
        with open(saida, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    a = sys.argv
    by = None
    if "--bybit" in a:
        by = set(json.load(open(a[a.index("--bybit") + 1])))
    r = correr(a[1], a[2], by)
    for l in r["resultados"] + ((r.get("so_bybit_ue") or {}).get("resultados") or []):
        vf = l["validacao_mais_fora"]
        print(l["estrategia"], l["fase"], l["corretora"], l["classe"], "| treino", l["treino"].get("r_op"),
              l["treino"].get("dias"), "| val", l["validacao"].get("r_op"), l["validacao"].get("dias"), "| fora",
              l["fora"].get("r_op"), l["fora"].get("dias"), "| VF r_dia", vf.get("r_dia"), vf.get("ic90_dia"),
              "pf", vf.get("pf"), "holm", l["p_holm"])
