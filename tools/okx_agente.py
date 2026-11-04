"""(04/11) Agente OKX — varre todos os contratos perpetuos de cripto da OKX Europa e procura as melhores
oportunidades da compra no panico (H23 L10, a estrategia com melhor prova ao nivel da conta; com custos de
futuros +0,105R por operacao no historico, H38). Pedido do Rui: "um agente especializado que varra o mercado
todo e nos de as melhores oportunidades".

SO PAPEL nesta versao: nao envia ordens. Avisa no Telegram e regista cada oportunidade e o resultado, numa conta
simulada de 20 USD com risco de 1% por operacao (a conta real do Rui na OKX). O dinheiro real liga-se quando a
estrategia cumprir a autorizacao previa do Rui (30 operacoes em papel com media positiva).

Dados: so a API publica da OKX (velas de 4H e financiamento dos perpetuos USDT), sem chave.
Estado: okx.json no ramo "okx" (repositorio publico: so precos publicos e resultados em R e %, nunca dinheiro real).
"""
import json, os, socket, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import papel_panico as P            # noqa: E402  (mesma regra e mesmas saidas do papel da Bybit)

_gai = socket.getaddrinfo                        # o servidor europeu tem IPv6; a chave da OKX esta presa ao IPv4
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, socket.AF_INET, *a, **k)
BASE = "https://eea.okx.com"
H4 = 14400
CONTA0, RISCO = 20.0, 0.01
CUSTO_LIM, CUSTO_MKT = 0.0002, 0.0010            # futuros: 0,02% maker; 0,05% taker + 0,05% deslize


def get(path, tent=3):
    for k in range(tent):
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": "cryptoscan/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            if d.get("code") == "0":
                return d.get("data") or []
            if d.get("code") == "50011":            # limite de pedidos: espera
                time.sleep(2)
                continue
            return []
        except Exception:
            time.sleep(1 + k)
    return []


def e_cripto(i, spot):
    """(04/11) A OKX marca a classe do contrato em instCategory (1 = cripto; 3 = acoes, 4 = materias-primas...).
    Antes usava-se so "a base existe no spot", o que punha criptos novas sem spot (0G, AERO, ENSO, SOON...) no agente
    das acoes e fora da compra no panico. Sem o campo, fica a regra antiga."""
    cat = str(i.get("instCategory") or "")
    if cat:
        return cat == "1"
    return i["instId"].split("-")[0] in spot


def moedas():
    """Perpetuos USDT de cripto (instCategory 1; sem esse campo, a base tem de existir no spot da OKX)."""
    spot = {i["baseCcy"] for i in get("/api/v5/public/instruments?instType=SPOT") if i.get("state") == "live"}
    out = {}
    for i in get("/api/v5/public/instruments?instType=SWAP"):
        if i.get("state") != "live" or i.get("settleCcy") != "USDT" or i.get("ctType") != "linear":
            continue
        if e_cripto(i, spot):
            out[i["instId"].split("-")[0]] = {"inst": i["instId"], "ctVal": float(i.get("ctVal") or 0),
                                              "minSz": float(i.get("minSz") or 0), "lotSz": float(i.get("lotSz") or 0)}
    return out


def velas(inst):
    d = get(f"/api/v5/market/candles?instId={inst}&bar=4H&limit=300")
    c4 = [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
          for x in reversed(d) if len(x) > 8 and x[8] == "1"]          # so velas fechadas (confirm = 1)
    return c4


def funding(inst, cache):
    """[(t_s, taxa)] por ordem; guarda em cache e so pede o que falta."""
    tem = cache.get(inst) or []
    novos, depois = [], ""
    for _ in range(4):                                                  # ate 400 registos (~133 dias)
        d = get(f"/api/v5/public/funding-rate-history?instId={inst}&limit=100{depois}")
        if not d:
            break
        lote = [(int(x["fundingTime"]) // 1000, float(x["realizedRate"] or x["fundingRate"])) for x in d]
        novos += lote
        if tem and min(t for t, _ in lote) <= tem[-1][0]:
            break
        depois = f"&after={d[-1]['fundingTime']}"
        time.sleep(0.12)
    junta = {t: r for t, r in tem}
    junta.update({t: r for t, r in novos})
    cache[inst] = sorted(junta.items())[-400:]
    return cache[inst]


def r_futuros(e, px, risco, custo_saida):
    return round(((px - e) - (CUSTO_LIM * e + custo_saida * px)) / risco, 3)


def seguir(op, c4):
    """Como engine/papel_panico._seguir, com custos de futuros."""
    for b in c4:
        if b["t"] <= op.get("visto", 0):
            continue
        op["visto"] = b["t"]
        primeira = b["t"] == op["t_fill"]
        if b["l"] <= op["stop"] and (not primeira or b["o"] > op["stop"]):
            return r_futuros(op["entrada"], op["stop"], op["risco"], CUSTO_MKT), "stop"
        if b["h"] >= op["alvo"]:
            return r_futuros(op["entrada"], op["alvo"], op["risco"], CUSTO_LIM), "objetivo"
        if b["t"] >= op["t_fill"] + (P.HOLD - 1) * H4:
            return r_futuros(op["entrada"], b["c"], op["risco"], CUSTO_MKT), "tempo"
    return None


def nota(s, tipo):
    """Qualidade para ordenar: panico do mercado todo primeiro (H28), depois financiamento e queda mais extremos."""
    return (1 if tipo == "mercado" else 0, -s["funding"] * 1e4, -s["queda_3d_pct"])


def tamanho(conta, lim, stop, info):
    """Nominal para arriscar 1% da conta e se cabe na ordem minima do contrato."""
    nominal = RISCO * conta / ((lim - stop) / lim)
    minimo = info["ctVal"] * info["minSz"] * lim
    return round(nominal, 2), round(minimo, 2), nominal >= minimo


def correr(st, now):
    st.setdefault("pend", {}); st.setdefault("abertas", {}); st.setdefault("fechadas", [])
    st.setdefault("conta_sim", CONTA0); st.setdefault("ultimo", {}); cache = st.setdefault("funding", {})
    lista = moedas()
    btc = velas(lista["BTC"]["inst"]) if "BTC" in lista else []
    msgs, novos, vistas, radar = [], [], 0, []
    for a, info in sorted(lista.items()):
        c4 = velas(info["inst"])
        time.sleep(0.12)
        if len(c4) < P.ATR_N + 20:
            continue
        vistas += 1
        radar.append((a, info, c4))
        p = st["pend"].get(a)
        if p:                                                           # ordem limite a espera (2 velas)
            for b in c4:
                if p["t_sig"] < b["t"] <= p["t_sig"] + P.VALIDA * H4 and b["l"] <= p["lim"]:
                    e = min(p["lim"], b["o"])
                    stop = e - 2 * p["atr"]
                    st["abertas"][a] = {**p, "entrada": e, "stop": stop, "alvo": e + 2 * (e - stop), "risco": e - stop,
                                        "t_fill": b["t"], "visto": b["t"] - 1}
                    st["pend"].pop(a)
                    msgs.append(f"📝 OKX papel — {a}: a ordem limite executou a {e:.6g} (stop {stop:.6g}, objetivo {e + 2 * (e - stop):.6g}).")
                    break
            else:
                if c4[-1]["t"] >= p["t_sig"] + P.VALIDA * H4:
                    st["pend"].pop(a)
        op = st["abertas"].get(a)
        if op:
            fim = seguir(op, [b for b in c4 if b["t"] >= op["t_fill"]])
            if fim:
                st["conta_sim"] = round(st["conta_sim"] * (1 + RISCO * fim[0]), 4)
                st["fechadas"].append({"asset": a, "t_sig": op["t_sig"], "r": fim[0], "motivo": fim[1], "tipo": op.get("tipo"),
                                       "t_fim": op.get("visto")})
                st["abertas"].pop(a)
                rs = [x["r"] for x in st["fechadas"]]
                msgs.append(f"📝 OKX papel — {a} fechou ({fim[1]}): {fim[0]:+.2f}R. {len(rs)} operações, média {sum(rs) / len(rs):+.2f}R; "
                            f"conta simulada de 20 USD: {100 * (st['conta_sim'] / CONTA0 - 1):+.1f}%.")
        if a in st["pend"] or a in st["abertas"] or c4[-1]["t"] <= st["ultimo"].get(a, 0):
            continue
        st["ultimo"][a] = c4[-1]["t"]
        if c4[-1]["c"] / c4[-19]["c"] - 1 > -0.10:                      # sem queda de 10% em 3 dias nao vale pedir o financiamento
            continue
        s = P.sinal(c4, funding(info["inst"], cache))
        if not s:
            continue
        s["tipo"] = P.tipo_panico(btc, s["t_sig"])
        st["pend"][a] = s
        novos.append((a, s, info))
    for k in [k for k in cache if k.split("-")[0] not in lista]:
        cache.pop(k)
    if novos:
        novos.sort(key=lambda x: nota(x[1], x[1].get("tipo")), reverse=True)
        linhas = []
        for a, s, info in novos[:8]:
            stop = s["lim"] - 2 * s["atr"]
            nom, mn, cabe = tamanho(st["conta_sim"], s["lim"], stop, info)
            linhas.append(f"• {a}: compra limite {s['lim']:.6g} (válida 8 h), stop {stop:.6g} ({100 * (stop / s['lim'] - 1):.1f}%), "
                          f"objetivo {s['lim'] + 2 * (s['lim'] - stop):.6g}; queda 3 dias {s['queda_3d_pct']}%, financiamento "
                          f"{100 * s['funding']:.3f}%, pânico {s.get('tipo') or '?'}; posição p/ 20 USD ~{nom} USD "
                          f"({'cabe' if cabe else 'abaixo do mínimo de ' + str(mn)})")
        msgs.insert(0, f"🔎 Agente OKX — {len(novos)} oportunidade(s) de compra no pânico (só papel), melhores primeiro:\n" + "\n".join(linhas))
    try:                                         # (04/11) H46 recuo na subida (papel; real com okx_config "recuo_real")
        import okx_recuo
        msgs += okx_recuo.correr(st, radar, lista, now)
    except Exception as e:
        print("recuo erro:", type(e).__name__)
    try:                                         # (04/11) dinheiro real na OKX (okx_config.json "real": true)
        import okx_exec
        novos_real = sorted(st["pend"].items(), key=lambda kv: nota(kv[1], kv[1].get("tipo")), reverse=True)
        novos_real += [(a, {**s_, "tipo": "recuo"}) for a, s_ in sorted(((st.get("recuo") or {}).get("pend") or {}).items())
                       if a not in st["pend"]]
        okx_exec.correr(st, novos_real, now, msgs)
    except Exception as e:
        msgs.append(f"⚠️ OKX real: erro na execução ({type(e).__name__}); nada novo foi enviado.")
        print("okx_exec erro:", type(e).__name__, str(e)[:120])
    try:
        tem = set(st["abertas"]) | set(st["pend"]) | set((st.get("real") or {}).get("ops") or {})
        st["radar"] = radar_quase([x for x in radar if x[0] not in tem], btc, cache)
        m = relatorio_radar(st, now)
        if m:
            msgs.append(m)
    except Exception as e:
        print("radar erro:", type(e).__name__)
    st["resumo"] = {"t": int(now), "contratos": len(lista), "analisados": vistas, "pendentes": sorted(st["pend"]),
                    "abertas": sorted(st["abertas"]), "n": len(st["fechadas"]),
                    "r_medio": round(sum(x["r"] for x in st["fechadas"]) / len(st["fechadas"]), 3) if st["fechadas"] else None,
                    "conta_sim_pct": round(100 * (st["conta_sim"] / CONTA0 - 1), 2)}
    try:
        st["desempenho"] = {k: metricas([x["r"] for x in st["fechadas"] if f(x)])
                            for k, f in (("mercado", lambda x: x.get("tipo") == "mercado"),
                                         ("isolado", lambda x: x.get("tipo") != "mercado"), ("todos", lambda x: True))}
        m = alerta_vantagem(st)
        if m:
            msgs.append(m)
    except Exception as e:
        print("desempenho erro:", type(e).__name__)
    del st["fechadas"][:-1000]
    return msgs


# (04/11) Calibracao: o que o teste prometeu (H40, custos de futuros, duas metades) contra o que acontece ao vivo
REF_H40 = {"mercado": (0.174, 0.406), "isolado": (-0.126, 0.076)}


def metricas(rs):
    """Expectativa, acerto, profit factor e intervalo de 95% da media (R por operacao), so com resultados reais."""
    n = len(rs)
    if not n:
        return {"n": 0}
    m = sum(rs) / n
    sd = (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5 if n > 1 else None
    ganhos, perdas = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    se = sd / n ** 0.5 if sd is not None else None
    return {"n": n, "r_medio": round(m, 3), "acerto_pct": round(100 * sum(r > 0 for r in rs) / n),
            "profit_factor": round(ganhos / perdas, 2) if perdas else None,
            "ic95": [round(m - 1.96 * se, 3), round(m + 1.96 * se, 3)] if se is not None else None}


def alerta_vantagem(st):
    """Com 20+ operacoes em papel do panico do mercado: avisa (uma vez por patamar de 10) se o intervalo de 95%
    ja exclui o que o teste prometeu (vantagem em duvida) ou se confirma media positiva."""
    d = (st.get("desempenho") or {}).get("mercado") or {}
    n, ic = d.get("n", 0), d.get("ic95")
    if n < 20 or not ic or st.get("alerta_n") == n // 10:
        return None
    st["alerta_n"] = n // 10
    lo, hi = REF_H40["mercado"]
    if ic[1] < 0:
        return (f"🚨 Calibração OKX: {n} operações em papel do pânico do mercado com média {d['r_medio']:+.2f}R "
                f"(95%: {ic[0]:+.2f} a {ic[1]:+.2f}R). A vantagem do teste ({lo:+.2f} a {hi:+.2f}R) não se está a confirmar: "
                "proponho suspender o dinheiro real até ver a causa.")
    if ic[0] > 0:
        return f"✅ Calibração OKX: {n} operações em papel, média {d['r_medio']:+.2f}R, 95% acima de zero. A vantagem confirma-se ao vivo."
    return (f"📏 Calibração OKX: {n} operações em papel, média {d['r_medio']:+.2f}R (95%: {ic[0]:+.2f} a {ic[1]:+.2f}R; "
            f"teste {lo:+.2f} a {hi:+.2f}R). Ainda sem conclusão.")


RADAR_QUEDA = -0.05      # so pede o financiamento a quem ja caiu 5% em 3 dias (metade do caminho para o sinal)
RADAR_HORA = 19          # relatorio diario no Telegram a esta hora UTC


def radar_quase(radar, btc, cache):
    """(04/11) Pedido do Rui: "nao perder operacoes". Para cada moeda, quao perto esta de cada condicao do sinal:
    queda de 3 dias (precisa <= -10%), financiamento negativo e no 5% mais baixo dos ultimos 90 dias, e o BTC a cair 3%
    em 24 h (pânico do mercado, o que vai a dinheiro real). Devolve as 8 mais perto, so com precos e percentagens."""
    btc_24h = round(100 * (btc[-1]["c"] / btc[-7]["c"] - 1), 1) if len(btc) > 7 else None
    out = []
    for a, info, c4 in radar:
        q = c4[-1]["c"] / c4[-19]["c"] - 1
        if q > RADAR_QUEDA:
            continue
        f = funding(info["inst"], cache) if q <= RADAR_QUEDA else []
        conh = [x for x in f if x[0] <= c4[-1]["t"] + H4]
        fv = conh[-1][1] if conh else None
        p5 = P._pct5([x[1] for x in conh[-271:-1]]) if len(conh) >= 271 else None
        falta = []
        if q > -0.10:
            falta.append(f"queda de 3 dias {100 * q:.1f}% (precisa de -10%)")
        if fv is None or p5 is None:
            falta.append("sem histórico de financiamento suficiente")
        elif fv >= 0 or fv > p5:
            falta.append(f"financiamento {100 * fv:.3f}% (precisa de negativo e ≤ {100 * p5:.3f}%)")
        if btc_24h is None:
            falta.append("sem dados do BTC")
        elif btc_24h > 100 * P.BTC_QUEDA:
            falta.append(f"BTC {btc_24h:+.1f}% em 24 h (dinheiro real só com o BTC a cair 3%)")
        # distancia: quanto falta em cada condicao, normalizado
        d = max(0.0, q + 0.10) / 0.10 + (0 if fv is not None and p5 is not None and fv < 0 and fv <= p5 else 1)
        out.append({"a": a, "q": round(100 * q, 1), "f": None if fv is None else round(100 * fv, 4),
                    "p5": None if p5 is None else round(100 * p5, 4), "falta": falta, "d": round(d, 3)})
        time.sleep(0.05)
    out.sort(key=lambda x: x["d"])
    return {"btc_24h": btc_24h, "lista": out[:8]}


def relatorio_radar(st, now):
    """Uma vez por dia (19 h UTC): as moedas mais perto do sinal e o que lhes falta, para o Rui ver que nada passa."""
    dia = int(now // 86400)
    if time.gmtime(now).tm_hour != RADAR_HORA or st.get("radar_dia") == dia:
        return None
    st["radar_dia"] = dia
    R = st.get("radar") or {}
    L = R.get("lista") or []
    cab = f"🧭 Radar diário OKX — 220 criptos analisadas de hora a hora. BTC {R.get('btc_24h')}% em 24 h.\n"
    if not L:
        return cab + "Nenhuma moeda caiu 5% ou mais em 3 dias: não há nenhum pânico em formação. Nada perdido."
    linhas = [f"• {x['a']}: " + ("TODAS as condições cumpridas" if not x["falta"] else "falta " + "; ".join(x["falta"])) for x in L[:5]]
    return cab + "As mais perto de dar sinal de compra:\n" + "\n".join(linhas)


def telegram(txt):
    t, c = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not t or not c:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage",
                                                      data=json.dumps({"chat_id": c, "text": txt[:4000]}).encode(),
                                                      headers={"Content-Type": "application/json"}), timeout=20)
    except Exception as e:                       # nunca imprimir a mensagem do erro: pode conter o URL com o token
        print("telegram falhou:", type(e).__name__)


def main(caminho):
    st = json.load(open(caminho)) if os.path.exists(caminho) else {}
    primeira = not st
    msgs = correr(st, time.time())
    json.dump(st, open(caminho, "w"), separators=(",", ":"))
    r = st["resumo"]
    print(f"contratos {r['contratos']} | analisados {r['analisados']} | pendentes {r['pendentes']} | abertas {r['abertas']} | "
          f"fechadas {r['n']} | R medio {r['r_medio']} | conta simulada {r['conta_sim_pct']:+.2f}%")
    if primeira:
        msgs.insert(0, f"🤖 Agente OKX ligado: analisa {r['analisados']} perpétuos de cripto da OKX de hora a hora "
                       "(compra no pânico, só papel). Avisa aqui quando houver oportunidades.")
    import re
    for m in msgs:
        telegram(m)
        if "OKX real" in m:                      # registo publico: sem numeros (podem ser valores da conta)
            print("msg:", re.sub(r"\d", "#", m)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "okx.json"))
