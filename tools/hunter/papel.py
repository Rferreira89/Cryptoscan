"""Paper trading continuo do Hunter (SO PAPEL: sem chaves, sem executores, sem ordens; nunca ocupa vagas reais e
nunca se mistura com os resultados reais - ficheiro proprio no ramo autonomo).

Cada volta (depois de cada fecho de 30 min):
  1. universo completo dos X-Perps (dados publicos) e velas recentes de 30 min (reamostradas a 1H/4H);
  2. para cada estrategia de hunter/papel_estrategias.json cujo timeframe acabou de fechar: sinais na ultima vela;
  3. funil: descobertos -> dados validos -> candidatos -> rejeitados (motivo) -> aprovados -> abertas -> fechadas ->
     resultado liquido; falhas tecnicas (API) contam como oportunidades perdidas;
  4. cada operacao em papel e re-simulada com a MESMA funcao do backtest (tools/hunter/geometria.simular) sobre as
     velas que entretanto fecharam: entrada na abertura da vela seguinte, stop/alvos/saidas da estrategia, custos e
     funding real da OKX; fecha quando a saida acontece;
  5. aprendizagem/degradacao: por estrategia, R acumulado e motor de sobrevivencia (tools/autonomo.sobrevivencia):
     com limites ultrapassados deixa de abrir operacoes novas dessa estrategia; as abertas continuam geridas.

Uso: python -m tools.hunter.papel <pasta_autonomo>
"""
import json
import os
import sys
import time

import numpy as np

from tools import autonomo as AU
from tools.hunter import dados as DD, familias as FA, geometria as GE, motor as MO

VELAS = 300               # velas por timeframe (um pedido por moeda e por timeframe: 30m, 1H e 4H da propria OKX)
RISCO_PAPEL_PCT = 0.5     # dimensionamento simulado (Kelly = 0 sem vantagem demonstrada: usa-se um minimo fixo)


def _carregar(p, padrao):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return padrao


def velas_tf(inst, tf, now, request=DD.get):
    d = request("/api/v5/market/history-candles", {"instId": inst, "bar": tf, "limit": VELAS})
    if d is None:
        return None
    out = [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
            "v": float(x[5])} for x in d if len(x) > 8 and str(x[8]) == "1"]
    return sorted((b for b in out if b["t"] + DD.BAR[tf] <= now), key=lambda b: b["t"])


def recentes(uni, now, tfs, workers=6):
    """{tf: {base: velas}} recentes de todos os X-Perps e a lista de (base, tf) que falharam (falha tecnica)."""
    from concurrent.futures import ThreadPoolExecutor
    pares = [(b, tf) for b in sorted(uni) for tf in tfs]

    def um(x):
        b, tf = x
        return b, tf, velas_tf(uni[b]["inst"], tf, now)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(um, pares))
    out = {tf: {} for tf in tfs}
    falhas = []
    for b, tf, v in got:
        if v is None:
            falhas.append(f"{b} {tf}")
        elif v:
            out[tf][b] = v
    return out, falhas


def _series(velas_por_tf):
    import numpy as np
    SS = {tf: {} for tf in DD.BAR}
    for tf, porb in velas_por_tf.items():
        for b, v in porb.items():
            S = {k: np.array([x[k] for x in v], dtype=float) for k in "ohlcv"}
            S["t"] = np.array([x["t"] for x in v], dtype=np.int64)
            S["atr"] = np.array([np.nan if a is None else a for a in GE.atr_serie(v)], dtype=float)
            S["v_list"] = v
            SS[tf][b] = S
    return SS


LIMITES_ACONTECIMENTO = (1, 3, 5, None)   # carteiras-sombra: max. posicoes por acontecimento (None = sem limite)
FALHAS_MAX = 0.20                         # > 20% dos pedidos falhados: sem entradas novas (gestao continua)
def _versao():
    """Commit do codigo que esta a correr (o checkout do ramo de investigacao no inicio do job)."""
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=os.path.dirname(os.path.abspath(__file__)),
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


VERSAO = os.environ.get("HUNTER_CODIGO") or _versao()


def deslize_por_tier(tier, spread_pct=None):
    """Deslizamento por lado (% do preco): metade do spread observado (se houver) e um minimo por escalao."""
    base = {"A": 0.03, "B": 0.08, "C": 0.20}.get(tier, 0.20)
    return round(max(base, (spread_pct or 0) / 2), 4)


def spreads(request=DD.get):
    """{inst: spread em % do meio} a partir de UM pedido publico (tickers de FUTURES)."""
    out = {}
    for t in request("/api/v5/market/tickers", {"instType": "FUTURES"}) or []:
        try:
            a, b = float(t.get("askPx") or 0), float(t.get("bidPx") or 0)
            if a > 0 and b > 0:
                out[t["instId"]] = round(100 * (a - b) / ((a + b) / 2), 4)
        except (TypeError, ValueError, KeyError):
            pass
    return out


def acontecimento(tf, t, btc_ret):
    """Um acontecimento de mercado = a mesma vela de fecho no mesmo timeframe (os sinais dessa vela partilham a
    mesma informacao de mercado); marca 'movimento do BTC' se o BTC mexeu >= 1% nessa vela."""
    tag = ""
    if btc_ret is not None and btc_ret == btc_ret and abs(btc_ret) >= 0.01:
        tag = f"|BTC{'+' if btc_ret > 0 else '-'}{abs(btc_ret) * 100:.1f}%"
    return f"{tf}@{int(t)}{tag}"


def _log(o, now, estado, **extra):
    o.setdefault("historico", []).append({"t": int(now), "estado": estado, **extra})


def volta(pasta, now=None, uni=None, velas=None, funding_fn=None, falhas=None, spread_fn=None):
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "hunter", n)
    os.makedirs(os.path.join(pasta, "hunter"), exist_ok=True)
    est = _carregar(p("papel_estrategias.json"), {"estrategias": []})["estrategias"]
    # (17/11) estrategias REJECTED no registo central nao abrem novas posicoes de papel (as abertas fecham normalmente)
    rejeitadas = {k for k, v in (_carregar(p("estrategias_registo.json"), {}).get("estrategias") or {}).items()
                  if v.get("estado") == "REJECTED"}
    est = [e for e in est if e["id"] not in rejeitadas]
    st = _carregar(p("papel_estado.json"), {"abertas": [], "fechadas": [], "funil_total": {}, "voltas": 0,
                                             "bloqueadas": {}})
    st.setdefault("vistos", [])
    if uni is None:
        uni = DD.universo()
    tfs_agora = sorted({e["tf"] for e in est if not (now // 1800 * 1800) % DD.BAR[e["tf"]]} |
                       {o["tf"] for o in st["abertas"]} | {o["stop_ref"] for o in st["abertas"]} |
                       {e["stop_ref"] for e in est} | {"1H"})
    pedidos = len(uni) * len(tfs_agora)
    if velas is None:
        velas, falhas = recentes(uni, now, tfs_agora)
    falhas = falhas or []
    sp = (spread_fn or spreads)() if spread_fn is not False else {}
    funding_fn = funding_fn or (lambda inst: DD.funding(inst) or [])
    validos, rej_dados = {}, {}
    for tf, porb in velas.items():
        validos[tf] = {}
        for b, v in porb.items():
            ok, mot = DD.validar(v, DD.BAR[tf], now)
            if ok:
                validos[tf][b] = v
            else:
                rej_dados[f"{b} {tf}"] = mot
    SS = _series(validos)
    dados_ctx = {b: {"info": uni.get(b, {}), "funding": []} for tf in validos for b in validos[tf]}
    if any(e["familia"] == "funding_extremo" for e in est):
        for b in dados_ctx:
            dados_ctx[b]["funding"] = funding_fn(uni[b]["inst"]) if b in uni else []
    MM = {tf: MO.contexto(SS, dados_ctx, tf) for tf in DD.BAR}
    fiavel = not pedidos or len(falhas) / max(1, pedidos) <= FALHAS_MAX
    funil = {"instrumentos_descobertos": len(uni), "com_dados_validos": len({b for tf in validos for b in validos[tf]}),
             "falhas_tecnicas": len(falhas), "excluidos_por_dados": len(rej_dados), "dados_fiaveis": fiavel,
             "sinais_brutos": 0, "rejeitados": {}, "elegiveis_apos_concentracao": 0, "abertas_novas": 0,
             "fechadas_agora": 0, "acontecimentos_novos": 0, "moedas_com_sinal": 0}

    def rejeita(m):
        funil["rejeitados"][m] = funil["rejeitados"].get(m, 0) + 1

    vistos = set(st["vistos"]) | {o["id_op"] for o in st["abertas"]} | {o["id_op"] for o in st["fechadas"]}
    abertas_chave = {(o["estrategia"], o["b"]) for o in st["abertas"]}
    moeda_acont = {(o["b"], o.get("acontecimento")) for o in st["abertas"]}
    por_acont = {}
    for o in st["abertas"]:
        for k in o.get("carteiras") or []:
            por_acont[(k, o.get("acontecimento"))] = por_acont.get((k, o.get("acontecimento")), 0) + 1
    brutos = []
    for e in est:
        tf = e["tf"]
        s = DD.BAR[tf]
        if (now // 1800 * 1800) % s or tf not in SS:            # o tf desta estrategia nao fechou nesta volta
            continue
        with np.errstate(all="ignore"):
            for b, S in SS[tf].items():
                L, Sh = FA.FAMILIAS[e["familia"]][0](S, MM[tf][b], e["parametros"])
                ii = L if e["lado"] == "LONG" else Sh
                i = len(S["c"]) - 1
                if not len(ii) or ii[-1] != i:
                    continue
                brutos.append((e, b, S, i))
    funil["sinais_brutos"] = len(brutos)
    funil["moedas_com_sinal"] = len({b for _, b, _, _ in brutos})
    acont_vistos = set()
    for e, b, S, i in brutos:
        tf = e["tf"]
        s = DD.BAR[tf]
        id_op = f"{e['id']}|{b}|{int(S['t'][i])}"
        if id_op in vistos:
            rejeita("sinal ja tratado (protecao contra duplicados apos reinicio)")
            continue
        if not fiavel:
            rejeita("dados pouco fiaveis nesta volta (falhas de API): sem entradas novas")
            continue
        if st["bloqueadas"].get(e["id"]):
            rejeita("estrategia bloqueada pelo motor de sobrevivencia")
            continue
        if S["t"][i] + s > now:
            rejeita("vela ainda aberta")
            continue
        if (e["id"], b) in abertas_chave:
            rejeita("ja ha posicao desta estrategia nesta moeda")
            continue
        f = MO.FILTROS.get(e.get("filtro"))
        if f and not f(MM, tf, b, i, dados_ctx):
            rejeita(f"filtro {e.get('filtro')}")
            continue
        a = MO.atr_ref(SS, b, tf, i, e["stop_ref"])
        if not a:
            rejeita("ATR de referencia indisponivel")
            continue
        btc = MM[tf][b].get("btc_ret_1")
        ac = acontecimento(tf, S["t"][i], None if btc is None else float(btc[i]))
        if (b, ac) in moeda_acont:
            rejeita("ja ha exposicao a esta moeda neste acontecimento (outra estrategia)")
            continue
        carteiras = []
        for lim in LIMITES_ACONTECIMENTO:
            k = f"max{lim}" if lim else "sem_limite"
            if lim is None or por_acont.get((k, ac), 0) < lim:
                carteiras.append(k)
                por_acont[(k, ac)] = por_acont.get((k, ac), 0) + 1
        if "max3" not in carteiras:                # carteira principal: no maximo 3 posicoes por acontecimento
            rejeita("concentracao: acontecimento ja com 3 posicoes (segue so nas carteiras-sombra max5/sem_limite)")
        else:
            funil["elegiveis_apos_concentracao"] += 1
        if ac not in acont_vistos:
            acont_vistos.add(ac)
        info = uni.get(b) or {}
        tier = DD.tier(info, validos.get("1H", {}).get(b) or validos.get(tf, {}).get(b) or [])["tier"]
        spread = sp.get(info.get("inst"))
        desl = deslize_por_tier(tier, spread)
        stop_pct = float(100 * e["saida"]["k"] * a / S["c"][i])
        dim = AU.dimensionar(RISCO_PAPEL_PCT, stop_pct, 5, 2 * (GE.COMISSAO + desl), {"risco_max_pct": 5.0})
        o = {"id_op": id_op, "estrategia": e["id"], "versao_estrategia": e["id"], "versao_codigo": VERSAO,
             "familia": e["familia"], "veredicto_origem": e.get("veredicto"), "b": b, "inst": info.get("inst"),
             "mercado": "OKX X-Perp (PAPEL)", "classe": info.get("classe"), "tier": tier, "lado": e["lado"], "tf": tf,
             "t_sinal": int(S["t"][i]), "atr_ref": a, "saida": e["saida"], "stop_ref": e["stop_ref"],
             "regime": MO._regime(MM, tf, b, i), "acontecimento": ac, "carteiras": carteiras,
             "custos_previstos": {"comissao_lado_pct": GE.COMISSAO, "deslize_lado_pct": desl, "spread_pct": spread},
             "decisao": {"fecho": float(S["c"][i]), "atr_tf": float(S["atr"][i]), "atr_ref": a,
                         "btc_ret_vela": None if btc is None or btc[i] != btc[i] else round(float(btc[i]), 5),
                         "velas_disponiveis": int(i + 1), "ultima_vela_fechada": int(S["t"][i])},
             "tamanho": dim, "aberta_em": now}
        _log(o, now, "sinal aceite: entrada na abertura da vela seguinte")
        st["abertas"].append(o)
        vistos.add(id_op)
        abertas_chave.add((e["id"], b))
        moeda_acont.add((b, ac))
        funil["abertas_novas"] += 1
    funil["acontecimentos_novos"] = len(acont_vistos)
    # acompanhar e fechar (so velas fechadas; a mesma funcao do backtest)
    ficam = []
    for o in st["abertas"]:
        v = (velas.get(o["tf"]) or {}).get(o["b"]) or []
        i = next((k for k, x in enumerate(v) if x["t"] == o["t_sinal"]), None)
        if i is None:
            if now - o["t_sinal"] > 3 * 86400:
                o.update(fechada_em=now, motivo="dados indisponiveis (fecho administrativo, sem resultado)", r=None)
                _log(o, now, "fechada sem resultado: dados indisponiveis")
                st["fechadas"].append(o)
            else:
                _log(o, now, "sem dados nesta volta (gestao continua na seguinte)") if not fiavel else None
                ficam.append(o)
            continue
        if i + 1 >= len(v):
            ficam.append(o)                          # ainda nao abriu (espera a vela seguinte)
            continue
        fund = funding_fn(o["inst"]) if o.get("inst") else []
        desl = (o.get("custos_previstos") or {}).get("deslize_lado_pct", GE.DESLIZE)
        r = GE.simular(v, i, o["lado"], o["atr_ref"], o["saida"], fund, None, deslize=desl)
        if r is None:
            ficam.append(o)
            continue
        ultimo = len(v) - 1
        terminou = r["saida"] != "tempo" or i + o["saida"]["hold"] <= ultimo
        if "entrada" not in o:
            d = 1 if o["lado"] == "LONG" else -1
            o["entrada"] = round(v[i + 1]["o"] * (1 + d * desl / 100), 10)
            o["t_entrada"] = v[i + 1]["t"]
            risco = o["saida"]["k"] * o["atr_ref"]
            o["stop_inicial"] = o["entrada"] - d * risco
            o["objetivo"] = o["entrada"] + d * o["saida"]["tp"] * risco if o["saida"].get("tp") else None
            _log(o, now, "entrada simulada", preco=o["entrada"])
        if terminou:
            d = 1 if o["lado"] == "LONG" else -1
            preco_saida = o["entrada"] + d * r["bruto_r"] * o["saida"]["k"] * o["atr_ref"]
            o.update(fechada_em=now, r=round(r["r"], 4), bruto_r=round(r["bruto_r"], 4),
                     custos={"comissoes_e_deslize_r": round(r["custos_r"] - (o["entrada"] * r["funding_pct"] / 100) /
                                                            (o["saida"]["k"] * o["atr_ref"]), 4),
                             "funding_pct": r["funding_pct"], "funding_fonte": r["funding_fonte"], "total_r": round(r["custos_r"], 4)},
                     custos_r=round(r["custos_r"], 4), funding_pct=r["funding_pct"], motivo=r["saida"],
                     preco_saida_equivalente=round(preco_saida, 10), velas=r["velas"],
                     permanencia_min=r["velas"] * DD.BAR[o["tf"]] // 60,
                     resultado_pct_preco=round(100 * d * (preco_saida - o["entrada"]) / o["entrada"], 4),
                     resultado_liquido_pct_capital=round(r["r"] * (o.get("tamanho") or {}).get("risco_pct", 0), 4))
            _log(o, now, f"fechada: {r['saida']}", r=o["r"])
            st["fechadas"].append(o)
            funil["fechadas_agora"] += 1
        else:
            o["r_atual"] = round(r["r"], 4)
            ficam.append(o)
    st["abertas"] = ficam
    # aprendizagem: sobrevivencia por estrategia e resultados por carteira-sombra
    por, cart = {}, {}
    for o in st["fechadas"]:
        if o.get("r") is not None:
            por.setdefault(o["estrategia"], []).append(o)
            for k in o.get("carteiras") or ["sem_limite"]:
                cart.setdefault(k, []).append(o)
    resumo = {}
    for k, ops in por.items():
        rs = [o["r"] for o in ops]
        sv = AU.sobrevivencia(rs)
        resumo[k] = {"n": len(rs), "moedas": len({o["b"] for o in ops}), "dias": len({o["t_sinal"] // 86400 for o in ops}),
                     "acontecimentos": len({o.get("acontecimento") for o in ops}), "r_medio": round(sum(rs) / len(rs), 4),
                     "r_total": round(sum(rs), 3), "acerto": round(sum(1 for x in rs if x > 0) / len(rs), 3),
                     "drawdown_r": sv["drawdown_r"], "novas_entradas": sv["novas_entradas"], "motivos": sv["motivos"]}
        if not sv["novas_entradas"]:
            st["bloqueadas"][k] = sv["motivos"]
    st["resumo"] = resumo
    st["carteiras_sombra"] = {k: {"n": len(v), "acontecimentos": len({o.get("acontecimento") for o in v}),
                                  "r_total": round(sum(o["r"] for o in v), 3),
                                  "r_medio": round(sum(o["r"] for o in v) / len(v), 4)} for k, v in sorted(cart.items())}
    st["funil_ultima"] = {**funil, "t": now, "versao_codigo": VERSAO}
    tot = st["funil_total"]
    for k, v in funil.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            tot[k] = tot.get(k, 0) + v if k not in ("instrumentos_descobertos", "com_dados_validos") else v
    for m, n in funil["rejeitados"].items():
        tot.setdefault("rejeitados", {})[m] = tot.get("rejeitados", {}).get(m, 0) + n
    st["voltas"] += 1
    st["t"] = now
    st["aviso"] = "PAPEL: simulado, nunca somado aos resultados reais; sem ordens"
    st["fechadas"] = st["fechadas"][-5000:]
    st["vistos"] = sorted(vistos)[-20000:]
    with open(p("papel_estado.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=0)
    linha = {"t": now, "versao": VERSAO, **{k: v for k, v in funil.items()}, "abertas": len(st["abertas"]),
             "fechadas_total": len(st["fechadas"]),
             "estado": ("falha tecnica" if not fiavel else "sem sinais (ausencia legitima)" if not brutos else "ativo")}
    if validos.get("1H"):                       # (18/11) categoria D: movimentos que nenhum sinal apanhou
        try:
            from tools.hunter import cobertura as CB
            linha["cobertura"] = CB.atualizar(pasta, validos["1H"], uni or {}, now, st)
        except Exception as e:
            linha["cobertura"] = {"erro": f"{type(e).__name__}: {str(e)[:120]}"}
    with open(p("papel_ciclos.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return st


def resumo_diario(pasta, now=None):
    """Texto curto do dia (UTC anterior): atividade, sinais, entradas, saidas, bloqueios, falhas e resultados."""
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "hunter", n)
    dia0 = (now // 86400 - 1) * 86400
    linhas = []
    if os.path.exists(p("papel_ciclos.jsonl")):
        with open(p("papel_ciclos.jsonl"), encoding="utf-8") as f:
            linhas = [json.loads(x) for x in f if x.strip()]
    ontem = [x for x in linhas if dia0 <= x["t"] < dia0 + 86400]
    st = _carregar(p("papel_estado.json"), {"fechadas": [], "abertas": [], "bloqueadas": {}})
    fe = [o for o in st["fechadas"] if dia0 <= (o.get("fechada_em") or 0) < dia0 + 86400 and o.get("r") is not None]
    soma = lambda k: sum(x.get(k, 0) for x in ontem if isinstance(x.get(k, 0), int))
    falhas = sum(1 for x in ontem if x.get("estado") == "falha tecnica")
    txt = (f"🧪 Hunter (PAPEL, não é dinheiro real) — {time.strftime('%Y-%m-%d', time.gmtime(dia0))}\n"
           f"Voltas: {len(ontem)} (falhas técnicas: {falhas}) | sinais brutos: {soma('sinais_brutos')} | "
           f"elegíveis: {soma('elegiveis_apos_concentracao')} | abertas: {soma('abertas_novas')} | "
           f"fechadas: {len(fe)}\n"
           f"Resultado das fechadas: {sum(o['r'] for o in fe):+.2f}R em {len(fe)} op."
           f" | abertas agora: {len(st['abertas'])} | estratégias bloqueadas: {len(st.get('bloqueadas') or {})}")
    return txt


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "resumo":
        print(resumo_diario(sys.argv[1]))
    else:
        agora = int(time.time())
        uni = DD.universo()
        s = volta(sys.argv[1], now=agora, uni=uni)
        print(json.dumps(s["funil_ultima"], ensure_ascii=False), "abertas", len(s["abertas"]), "fechadas", len(s["fechadas"]))
        try:                                   # arquivo de derivados: falhar aqui nunca impede o papel
            from tools.hunter import derivados as DV
            linhas, disp = DV.fotografia(uni, agora, completa=(agora // 1800) % 2 == 0)
            print("derivados:", DV.arquivar(sys.argv[1], linhas, disp, agora), json.dumps(disp))
        except Exception as e:
            print("derivados falhou:", type(e).__name__, str(e)[:160])
        try:                                   # (17/11) registo central de estrategias: falhar aqui nunca impede o papel
            from tools.hunter import qualificacao as QU
            rg = QU.atualizar(sys.argv[1], agora)
            print("registo:", json.dumps({k: v["estado"] for k, v in rg["estrategias"].items()}))
        except Exception as e:
            print("qualificacao falhou:", type(e).__name__, str(e)[:160])
        pd = os.path.join(sys.argv[1], "hunter", "papel_diario.jsonl")      # resumo diario (uma linha por dia UTC)
        dia = time.strftime("%Y-%m-%d", time.gmtime(agora - 86400))
        ja = os.path.exists(pd) and any(json.loads(x).get("dia") == dia for x in open(pd, encoding="utf-8") if x.strip())
        if not ja:
            with open(pd, "a", encoding="utf-8") as f:
                f.write(json.dumps({"dia": dia, "texto": resumo_diario(sys.argv[1], agora)}, ensure_ascii=False) + "\n")
