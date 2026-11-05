"""(04/11) Agente OKX macro — acoes, indices e materias-primas da OKX Europa (Nvidia, Apple, S&P 500, ouro, prata,
petroleo...). Pedido do Rui: "esse agente tambem verifica outras acoes e derivados? quero um tambem assim".

EXPERIMENTAL e SO PAPEL: nao ha prova nestes mercados com estes contratos. Regra pre-declarada (a familia com
melhor prova no H33/H39, so compras, porque os shorts de tendencia perderam em todos os mercados testados):
  entra comprado quando o fecho diario passa acima da media de 50 dias e essa media esta a subir face a 10 dias antes;
  sai quando o fecho diario fica abaixo da media de 50 dias. Custos 0,10% por lado (financiamento nao incluido).
Ordena as oportunidades pela forca: distancia acima da media e subida dos ultimos 20 dias.
Estado: chave "macro" do okx.json (ramo "okx"); so precos publicos e resultados em %.
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(__file__))
import okx_agente as A                           # noqa: E402  (mesma ligacao IPv4, pedidos e Telegram)

N, SUBIDA_DIAS, CUSTO = 50, 10, 0.001
# (04/11) ETF alavancados/inversos e de volatilidade: perdem valor com o tempo por construcao; a tendencia neles engana
FORA = {"SQQQ", "TQQQ", "SOXS", "SOXL", "UVXY", "VXX", "TSLL", "TSLQ", "NVDL", "NVDD", "SPXU", "SPXL", "UPRO", "SDS", "QID",
        "LABU", "LABD", "MSTU", "MSTZ", "CONL"}


def contratos():
    spot = {i["baseCcy"] for i in A.get("/api/v5/public/instruments?instType=SPOT") if i.get("state") == "live"}
    out = {}
    for i in A.get("/api/v5/public/instruments?instType=SWAP"):
        if i.get("state") != "live" or i.get("settleCcy") != "USDT" or i.get("ctType") != "linear":
            continue
        base = i["instId"].split("-")[0]
        if not A.e_cripto(i, spot) and base not in FORA:    # nao e cripto: acao, indice ou materia-prima
            out[base] = i["instId"]
    return out


def diario(inst):
    d = A.get(f"/api/v5/market/candles?instId={inst}&bar=1Dutc&limit=300")
    return [{"t": int(x[0]) // 1000, "c": float(x[4])} for x in reversed(d) if len(x) > 8 and x[8] == "1"]


def sinal(d):
    """(dentro, forca) para o ultimo dia fechado, ou None sem historico."""
    if len(d) < N + SUBIDA_DIAS + 1:
        return None
    c = [x["c"] for x in d]
    m = sum(c[-N:]) / N
    m10 = sum(c[-N - SUBIDA_DIAS:-SUBIDA_DIAS]) / N
    forca = (c[-1] / m - 1) + (c[-1] / c[-21] - 1 if len(c) > 21 else 0)
    return c[-1] > m and m > m10, c[-1] < m, round(100 * forca, 1), c[-1], m


def correr(st):
    M = st.setdefault("macro", {"abertas": {}, "fechadas": [], "ultimo": {}})
    msgs, novos, vistos, sem_hist = [], [], 0, 0
    lista = contratos()
    retirar_fora(M, lista)
    for base, inst in sorted(lista.items()):
        d = diario(inst)
        time.sleep(0.12)
        s = sinal(d)
        if not s:
            sem_hist += 1
            continue
        vistos += 1
        entra, sai, forca, px, m = s
        op = M["abertas"].get(base)
        if op and sai and d[-1]["t"] > op["t"]:
            ret = px / op["entrada"] - 1 - 2 * CUSTO
            M["fechadas"].append({"asset": base, "t": op["t"], "t_fim": d[-1]["t"], "ret_pct": round(100 * ret, 2)})
            M["abertas"].pop(base)
            rs = [x["ret_pct"] for x in M["fechadas"]]
            msgs.append(f"📝 OKX macro (papel) — {base} saiu (fecho abaixo da média de 50 dias): {100 * ret:+.1f}%. "
                        f"{len(rs)} operações, média {sum(rs) / len(rs):+.1f}%.")
        elif not op and entra and d[-1]["t"] > M["ultimo"].get(base, 0):
            M["abertas"][base] = {"t": d[-1]["t"], "entrada": px}
            novos.append((forca, base, px, m))
        M["ultimo"][base] = d[-1]["t"]
    if novos:
        novos.sort(reverse=True)
        msgs.insert(0, "📈 Agente OKX macro — entradas novas em tendência de subida (EXPERIMENTAL, só papel, sem prova nestes "
                       "mercados):\n" + "\n".join(f"• {b}: {px:.6g}, {100 * (px / m - 1):+.1f}% acima da média de 50 dias, força {f}"
                                                 for f, b, px, m in novos[:10]))
    rs = [x["ret_pct"] for x in M["fechadas"]]
    M["resumo"] = {"analisados": vistos, "sem_historico": sem_hist, "abertas": sorted(M["abertas"]), "n": len(rs),
                   "ret_medio_pct": round(sum(rs) / len(rs), 2) if rs else None}
    del M["fechadas"][:-1000]
    return msgs


def retirar_fora(M, lista):
    """(05/11) Operacoes em papel de contratos que deixaram de pertencer a este agente (passaram a cripto pelo
    instCategory, ou ETF alavancados agora em FORA) nunca mais eram vistas e ficavam abertas para sempre, a sujar o
    resumo. Saem para "retiradas", sem resultado (nao contam na media). So com a lista lida (API em baixo nao apaga)."""
    if not lista:
        return []
    fora = sorted(b for b in M["abertas"] if b not in lista)
    for b in fora:
        M.setdefault("retiradas", []).append({"asset": b, **M["abertas"].pop(b), "motivo": "fora do agente macro"})
    del M.setdefault("retiradas", [])[:-200]
    return fora


def main(caminho):
    st = json.load(open(caminho)) if os.path.exists(caminho) else {}
    primeira = "macro" not in st
    msgs = correr(st)
    json.dump(st, open(caminho, "w"), separators=(",", ":"))
    r = st["macro"]["resumo"]
    print(f"macro: analisados {r['analisados']} | sem historico {r['sem_historico']} | abertas {len(r['abertas'])} | fechadas {r['n']}")
    if primeira:
        msgs.insert(0, f"🤖 Agente OKX macro ligado: ações, índices e matérias-primas da OKX ({r['analisados']} com histórico "
                       f"suficiente; {len(r['abertas'])} já em tendência de subida). Experimental, só papel.")
    for m in msgs:
        A.telegram(m)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "okx.json"))
