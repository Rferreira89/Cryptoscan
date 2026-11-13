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
FUND_DIA = 0.0003            # (13/11) financiamento estimado 0,01%/8 h, pago enquanto a posicao esta aberta
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
    ontem = int(time.time()) // 86400 * 86400 - 86400     # abertura da ultima vela diaria (1Dutc) ja fechada
    curtos = M.setdefault("curtos", {})
    for base, inst in sorted(lista.items()):
        # (08/11) as velas diarias so mudam uma vez por dia: quem ja tem a vela de ontem nao e pedido outra vez nesta
        # volta (antes: ~230 pedidos e ~80 s de servidor em cada hora para as mesmas velas). Nada muda nas decisoes:
        # entradas e saidas so acontecem com uma vela nova.
        if M["ultimo"].get(base, 0) >= ontem:
            vistos += 1
            continue
        if curtos.get(base, 0) >= ontem:
            sem_hist += 1
            continue
        d = diario(inst)
        time.sleep(0.12)
        s = sinal(d)
        if not s:
            sem_hist += 1
            if d:
                curtos[base] = d[-1]["t"]
            continue
        curtos.pop(base, None)
        vistos += 1
        entra, sai, forca, px, m = s
        op = M["abertas"].get(base)
        if op:                                       # (13/11) avaliacao da aberta ao ultimo fecho diario
            op.update(px=px, t_px=d[-1]["t"])
        if op and sai and d[-1]["t"] > op["t"]:
            ret = px / op["entrada"] - 1 - 2 * CUSTO - FUND_DIA * max(0, (d[-1]["t"] - op["t"]) / 86400)
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
    try:
        M["resumo"].update(avaliar(M, xperps_eea()))
    except Exception as e:                           # a avaliacao nunca para o agente
        M["resumo"]["avaliacao_erro"] = str(e)[:100]
    for b in [b for b in curtos if lista and b not in lista]:   # API em baixo (lista vazia) nao apaga
        curtos.pop(b)
    del M["fechadas"][:-1000]
    return msgs


def xperps_eea():
    """Bases com X-Perp vivo na OKX EEA (o que a conta pode negociar; o agente le os perpetuos SWAP)."""
    return {i["instId"].split("-")[0] for i in A.get("/api/v5/public/instruments?instType=FUTURES")
            if "XPERP" in i.get("instId", "") and i.get("state") == "live"}


def avaliar(M, eea, agora=None):
    """(13/11, ordem do Rui) Avaliacao da carteira em papel: abertas ao ultimo fecho com custos e financiamento,
    exposicao, resultado por instrumento e o que e negociavel na conta OKX EEA. Em %, nunca dinheiro."""
    agora = agora or time.time()
    ab = []
    for b, op in sorted((M.get("abertas") or {}).items()):
        if not op.get("px"):
            ab.append({"asset": b, "avaliada": False, "negociavel_eea": b in eea})
            continue
        dias = max(0.0, ((op.get("t_px") or agora) - op["t"]) / 86400)
        ab.append({"asset": b, "avaliada": True, "dias": round(dias, 1), "negociavel_eea": b in eea,
                   "ret_pct": round(100 * (op["px"] / op["entrada"] - 1 - 2 * CUSTO - FUND_DIA * dias), 2)})
    av = [x["ret_pct"] for x in ab if x.get("avaliada")]
    por = {}
    for f in M.get("fechadas") or []:
        por.setdefault(f["asset"], []).append(f["ret_pct"])
    fech = M.get("fechadas") or []
    return {"abertas_avaliadas": ab, "abertas_n": len(ab), "abertas_sem_preco": sum(1 for x in ab if not x.get("avaliada")),
            "ret_aberto_medio_pct": round(sum(av) / len(av), 2) if av else None,
            "negociaveis_eea_abertas": sum(1 for x in ab if x["negociavel_eea"]),
            "fechadas_negociaveis_eea": sum(1 for f in fech if f["asset"] in eea),
            "por_instrumento": {k: {"n": len(v), "ret_medio_pct": round(sum(v) / len(v), 2)} for k, v in sorted(por.items())},
            "nota": "papel/sombra; sem posicoes reais; financiamento estimado 0,01%/8h"}


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
    v = st.get("volta") or {}
    if v.get("saltada") and 0 <= time.time() - (v.get("t") or 0) < 900:   # (07/11) o agente saltou esta volta repetida
        print("macro: volta repetida, saltada (velas diarias iguais as da volta anterior)")
        return 0
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
