"""C3 (13/11, ordem do Rui): deriva do preco depois de uma listagem nova. Fonte: velas de 4h do historico (ramos
history + history-delistadas, incluindo moedas ja retiradas, para reduzir o vies de sobrevivencia). A data da
listagem e a da primeira vela no historico (a listagem na fonte dos dados, normalmente a Binance; a Bybit UE pode
listar noutra data). KII, PONS e OPG nao tem historia suficiente e ficam de fora (anotado, nao inventado).
Regras fixas antes de correr: entrada na abertura do 2.o dia completo (as primeiras 24 h, de preco erratico e
spread largo, ficam de fora); saida por tempo ao fim de 7 ou 30 dias; LONG e SHORT (4 testes, Holm); custos Bybit UE
0,35% por lado; SHORT com juro de 0,05%/dia (moedas novas raramente se podem pedir emprestadas na Bybit UE: o SHORT
pode nem ser executavel). Dois periodos: listagens de 2024 e listagens desde 2025.
Uso: python3 backtest/estudos/c3_listagens.py <pasta_4h> [saida.json]"""
import gzip
import json
import math
import os
import sys
import time

DAY = 86400
CUSTO, JURO = 0.007, 0.0005


def correr(pasta, desde=1704067200):
    ev = []
    for f in sorted(os.listdir(pasta)):
        if not f.endswith(".csv.gz"):
            continue
        rows = [l.split(",") for l in gzip.open(os.path.join(pasta, f), "rt").read().split()]
        c4 = [(int(float(z[0])), float(z[1]), float(z[4])) for z in rows if len(z) >= 5]
        if not c4 or c4[0][0] < desde or f[:-7] in ("BTC",):
            continue
        t0 = (c4[0][0] // DAY + 1) * DAY + DAY                # abertura do 2.o dia completo
        ent = next((o for t, o, c in c4 if t >= t0), None)
        if not ent:
            continue
        r = {"moeda": f[:-7], "listagem": time.strftime("%Y-%m-%d", time.gmtime(c4[0][0])), "t": c4[0][0]}
        for h in (7, 30):
            fim = next((c for t, o, c in reversed(c4) if t < t0 + h * DAY), None)
            if fim and c4[-1][0] >= t0 + h * DAY - 4 * 3600:
                mv = fim / ent - 1
                r[f"long_{h}"] = mv - CUSTO
                r[f"short_{h}"] = -mv - CUSTO - JURO * h
        ev.append(r)
    linhas = []
    for k in ("long_7", "short_7", "long_30", "short_30"):
        xs = [e for e in ev if k in e]
        p1 = [e[k] for e in xs if e["t"] < 1735689600]
        p2 = [e[k] for e in xs if e["t"] >= 1735689600]
        allr = [e[k] for e in xs]
        m = sum(allr) / len(allr) if allr else 0
        sd = math.sqrt(sum((x - m) ** 2 for x in allr) / max(1, len(allr) - 1)) if allr else 0
        tt = m / (sd / math.sqrt(len(allr))) if sd else 0
        p = 0.5 * (1 - math.erf(tt / math.sqrt(2)))
        linhas.append({"teste": k, "n": len(allr), "medio_pct": round(100 * m, 2),
                       "mediana_pct": round(100 * sorted(allr)[len(allr) // 2], 2) if allr else None,
                       "acerto_pct": round(100 * sum(x > 0 for x in allr) / len(allr), 1) if allr else None,
                       "2024_medio_pct": round(100 * sum(p1) / len(p1), 2) if p1 else None, "2024_n": len(p1),
                       "desde_2025_medio_pct": round(100 * sum(p2) / len(p2), 2) if p2 else None, "desde_2025_n": len(p2),
                       "p": round(p, 4)})
    ps = [l["p"] for l in linhas]
    ordem = sorted(range(len(ps)), key=lambda i: ps[i])
    cor = 0.0
    for j, i in enumerate(ordem):
        cor = max(cor, min(1.0, (len(ps) - j) * ps[i]))
        linhas[i]["p_holm"] = round(cor, 4)
        linhas[i]["vantagem"] = bool(cor < 0.05 and (linhas[i]["2024_medio_pct"] or 0) > 0
                                     and (linhas[i]["desde_2025_medio_pct"] or 0) > 0)
    return {"listagens": len(ev), "linhas": linhas, "eventos": ev,
            "fora_por_falta_de_historia": ["KII", "PONS", "OPG"]}


if __name__ == "__main__":
    r = correr(sys.argv[1])
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"), indent=1)
    print("listagens", r["listagens"])
    for l in r["linhas"]:
        print(l)
