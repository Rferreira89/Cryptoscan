"""(17/11, ordem do Rui: promocao automatica) Motor de qualificacao e registo central de estrategias.

Estados: EXPLORATORY -> VALIDATION / PAPER_TRADING -> APPROVED_REAL -> ACTIVE_REAL; SUSPENDED; REJECTED.
  EXPLORATORY    backtest de treino+validacao ainda sem amostra/expectativa (Hunter: EXPLORATORIA)
  PAPER_TRADING  em paper trading prospetivo, a juntar operacoes fechadas
  VALIDATION     papel cumpre os minimos e o backtest preve amostra suficiente: pede o teste final (fora da amostra,
                 uma unica vez por regra; corre na pesquisa seguinte)
  APPROVED_REAL  teste final + robustez + papel cumprem TODOS os criterios (secao 3 da ordem)
  ACTIVE_REAL    aprovada e o piloto real esta operacional (todas as portas abertas, publicacao fresca)
  SUSPENDED      a vantagem desapareceu nas operacoes recentes (papel ou real): sem entradas reais, individualmente
  REJECTED       teste final falhado, papel claramente negativo, ou rejeicao por ordem do Rui (v2). Definitivo.
Criterios (A historico fora da amostra, B robustez, C papel, D regime) em avaliar_oos / avaliar_papel; o executor real
(tools/piloto_okx.py na main) volta a conferir os mesmos numeros antes de qualquer ordem.
Correcao de testes multiplos: Holm sobre TODOS os testes finais ja feitos (cada teste final e um teste confirmatorio;
os subconjuntos por regime contam como testes adicionais). O p e unilateral (media <= 0) por bootstrap de
acontecimentos (todas as operacoes da mesma vela de sinal reamostradas juntas).
Nada aqui envia ordens: so escreve hunter/estrategias_registo.json no ramo autonomo."""
import json
import os
import statistics
import sys
import time
import urllib.request

from tools.hunter import estat as ES
from tools.hunter import motor as MO

ESTADOS = ("EXPLORATORY", "VALIDATION", "PAPER_TRADING", "APPROVED_REAL", "ACTIVE_REAL", "SUSPENDED", "REJECTED")
C = {"oos_n_min": 100, "oos_acontecimentos_min": 30, "oos_dias_min": 30, "pf_min": 1.20, "alfa": 0.05,
     "quota_moeda_max": 0.40, "quota_acontecimento_max": 0.25, "quota_dia_max": 0.25,
     "papel_fechadas_min": 30, "papel_acontecimentos_min": 30, "papel_dias_min": 14,
     "custo_extra": 0.25, "melhores_frac": 0.05, "top_moedas": 3,
     "degradacao_janela": 30, "regime_n_min": 100}
REJEITADAS_POR_ORDEM = {"e495d11739f6": "v2 (Rompimento com reteste 4H LONG cripto): rejeitada para real pela ordem do Rui "
                                        "de 17/11 depois do teste fora da amostra (-0,30R, IC95 [-0,44; -0,16], PF 0,35)"}
PILOTO_URL = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/piloto-okx/piloto_publico.json"
ROBUSTEZ = ("custos_mais_25pct", "deslize_acima_da_media", "sem_melhores_operacoes", "sem_moedas_de_maior_contributo",
            "primeira_metade", "segunda_metade")


def _media(xs):
    return round(statistics.mean(xs), 4) if xs else None


def _quota(ops, chave):
    """Maior fracao do resultado positivo total vinda de um so grupo (moeda, acontecimento, dia)."""
    tot = sum(o["r"] for o in ops)
    if tot <= 0:
        return None
    g = {}
    for o in ops:
        g[chave(o)] = g.get(chave(o), 0.0) + o["r"]
    return round(max(g.values()) / tot, 4)


def avaliar_oos(ops, m_total):
    """Criterios A e B sobre as operacoes do teste final (fora da amostra). ops: dicts do motor (r, custos_r, t, b,
    tier, stop_pct, regime3). m_total: testes confirmatorios ja feitos (Holm)."""
    if not ops:
        return {"n": 0, "ok": False, "falhas": ["sem operacoes fora da amostra"]}
    rs = [o["r"] for o in ops]
    m, ic, p = ES.bootstrap_blocos([{"t": o["t"], "x": o["r"]} for o in ops], "x", bloco=1)
    ganhos, perdas = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    ords = sorted(ops, key=lambda o: o["t"])
    meio = len(ords) // 2
    k = max(1, int(round(C["melhores_frac"] * len(ops))))
    por_moeda = {}
    for o in ops:
        por_moeda[o["b"]] = por_moeda.get(o["b"], 0.0) + o["r"]
    top = {b for b, _ in sorted(por_moeda.items(), key=lambda x: -x[1])[:C["top_moedas"]]}
    extra_desl = lambda o: 2 * MO.deslize_tier(o.get("tier")) / max(1e-9, o.get("stop_pct") or 1e9)
    rob = {"custos_mais_25pct": _media([o["r"] - C["custo_extra"] * o.get("custos_r", 0) for o in ops]),
           "deslize_acima_da_media": _media([o["r"] - extra_desl(o) for o in ops]),
           "sem_melhores_operacoes": _media(sorted(rs)[:-k]),
           "sem_moedas_de_maior_contributo": _media([o["r"] for o in ops if o["b"] not in top]),
           "primeira_metade": _media([o["r"] for o in ords[:meio]]),
           "segunda_metade": _media([o["r"] for o in ords[meio:]])}
    conc = {"moeda": _quota(ops, lambda o: o["b"]), "acontecimento": _quota(ops, lambda o: o["t"]),
            "dia": _quota(ops, lambda o: o["t"] // 86400)}
    out = {"n": len(ops), "acontecimentos": len({o["t"] for o in ops}), "dias": len({o["t"] // 86400 for o in ops}),
           "moedas": len(por_moeda), "r_medio": round(m, 4), "ic95_acontecimento": ic, "p": round(p, 6),
           "p_holm": round(min(1.0, p * max(1, int(m_total))), 6), "m_holm": max(1, int(m_total)),
           "profit_factor": round(ganhos / perdas, 3) if perdas else None,
           "custo_medio_r": _media([o.get("custos_r", 0) for o in ops]), "robustez": rob, "concentracao": conc,
           "por_regime": {g: [len(v), _media([o["r"] for o in v])] for g, v in _grupos(ops, "regime3").items()}}
    out["falhas"] = falhas_oos(out)
    out["ok"] = not out["falhas"]
    return out


def _grupos(ops, k):
    g = {}
    for o in ops:
        g.setdefault(o.get(k) or "?", []).append(o)
    return g


def falhas_oos(o):
    f = []
    chk = [("n", o.get("n"), lambda x: x >= C["oos_n_min"]), ("acontecimentos", o.get("acontecimentos"), lambda x: x >= C["oos_acontecimentos_min"]),
           ("dias", o.get("dias"), lambda x: x >= C["oos_dias_min"]), ("r_medio", o.get("r_medio"), lambda x: x > 0),
           ("profit_factor", o.get("profit_factor"), lambda x: x >= C["pf_min"]),
           ("ic95_inferior", (o.get("ic95_acontecimento") or [None])[0], lambda x: x > 0),
           ("p_holm", o.get("p_holm"), lambda x: x < C["alfa"])]
    chk += [(f"robustez:{k}", (o.get("robustez") or {}).get(k), lambda x: x > 0) for k in ROBUSTEZ]
    for k, lim in (("moeda", C["quota_moeda_max"]), ("acontecimento", C["quota_acontecimento_max"]), ("dia", C["quota_dia_max"])):
        chk.append((f"concentracao:{k}", (o.get("concentracao") or {}).get(k), lambda x, lim=lim: x <= lim))
    for nome, v, t in chk:
        if v is None or not t(v):
            f.append(f"{nome}={v}")
    return f


def so_dados_insuficientes(falhas):
    return bool(falhas) and all(x.split("=")[0] in ("n", "acontecimentos", "dias") for x in falhas)


def avaliar_papel(fechadas, falhas_criticas=0):
    """Criterio C sobre as operacoes de papel FECHADAS com resultado (abertas nunca contam). Varias entradas do mesmo
    acontecimento contam uma vez para a independencia (media por acontecimento)."""
    ops = [o for o in fechadas if o.get("r") is not None]
    if not ops:
        return {"fechadas": 0, "acontecimentos": 0, "dias": 0, "r_medio": None, "falhas_criticas": falhas_criticas, "ok": False}
    por_ac = {}
    for o in ops:
        por_ac.setdefault(o.get("acontecimento") or o.get("t_sinal"), []).append(o["r"])
    t0 = min(o.get("t_entrada") or o["t_sinal"] for o in ops)
    t1 = max(o.get("fechada_em") or o["t_sinal"] for o in ops)
    r_ac = [statistics.mean(v) for v in por_ac.values()]
    out = {"fechadas": len(ops), "acontecimentos": len(por_ac), "dias": round((t1 - t0) / 86400, 1),
           "r_medio": _media([o["r"] for o in ops]), "r_medio_por_acontecimento": _media(r_ac),
           "falhas_criticas": int(falhas_criticas), "desde": int(t0)}
    _, ic, _ = ES.bootstrap_blocos([{"t": j, "x": x} for j, x in enumerate(r_ac)], "x", bloco=1) if len(r_ac) > 1 else (None, None, None)
    out["ic95_acontecimento"] = ic
    out["ok"] = (out["fechadas"] >= C["papel_fechadas_min"] and out["acontecimentos"] >= C["papel_acontecimentos_min"]
                 and out["dias"] >= C["papel_dias_min"] and (out["r_medio"] or 0) > 0
                 and (out["r_medio_por_acontecimento"] or 0) > 0 and out["falhas_criticas"] == 0)
    return out


def degradada(fechadas, reais=()):
    """Vantagem desapareceu? Ultimos 30 acontecimentos de papel com media <= 0, ou >= 10 operacoes reais com media
    < 0 e muito abaixo do papel."""
    ops = sorted((o for o in fechadas if o.get("r") is not None), key=lambda o: o.get("fechada_em") or o["t_sinal"])
    por_ac = {}
    for o in ops:
        por_ac.setdefault(o.get("acontecimento") or o.get("t_sinal"), []).append(o["r"])
    ult = [statistics.mean(v) for v in list(por_ac.values())[-C["degradacao_janela"]:]]
    if len(ult) >= C["degradacao_janela"] and statistics.mean(ult) <= 0:
        return f"ultimos {len(ult)} acontecimentos de papel com media {statistics.mean(ult):+.3f}R"
    rr = [o["r"] for o in reais if o.get("r") is not None]
    if len(rr) >= 10 and statistics.mean(rr) < 0 and statistics.mean(rr) < (_media(ult) or 0) - 0.5:
        return f"{len(rr)} operacoes reais com media {statistics.mean(rr):+.3f}R, muito abaixo do papel"
    return None


def _ler(p, padrao=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _piloto_publico():
    try:
        with urllib.request.urlopen(urllib.request.Request(PILOTO_URL, headers={"User-Agent": "cryptoscan"}), timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _metricas(ops):
    g = lambda k: {x: [len(v), _media([o["r"] for o in v])] for x, v in _grupos(ops, k).items()}
    return {"por_moeda": g("b"), "por_tf": g("tf"), "por_regime": g("regime")} if ops else {}


def atualizar(pasta, now=None, piloto=None):
    """Recalcula o registo central a partir dos ficheiros do Hunter (painel, papel, registo de testes, testes finais)."""
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "hunter", n)
    reg = _ler(p("estrategias_registo.json"), {"estrategias": {}})
    painel = (_ler(p("painel.json"), {}) or {}).get("estrategias") or {}
    em_papel = {e["id"]: e for e in (_ler(p("papel_estrategias.json"), {}) or {}).get("estrategias") or []}
    pst = _ler(p("papel_estado.json"), {}) or {}
    testes = (_ler(p("registo.json"), {}) or {}).get("acessos_teste") or {}
    if piloto is None:
        piloto = _piloto_publico()
    piloto_ok = bool(piloto and piloto.get("operacional") and now - int(piloto.get("t") or 0) <= 3 * 3600
                     and not piloto.get("simulacao"))
    reais = {}
    for o in (piloto or {}).get("ops") or []:
        reais.setdefault(o.get("estrategia"), []).append(o)
    fech = {}
    for o in pst.get("fechadas") or []:
        fech.setdefault(o.get("estrategia"), []).append(o)
    bloq = pst.get("bloqueadas") or {}
    ids = set(painel) | set(em_papel) | set(testes) | set(reg["estrategias"])
    pedidos = []
    for rid in sorted(ids):
        e = reg["estrategias"].get(rid) or {"id": rid, "estado": None, "historico": [], "criado": now}
        defin = (painel.get(rid) or {}).get("estrategia") or {k: em_papel[rid].get(k) for k in
                                                              ("familia", "parametros", "tf", "lado", "filtro", "stop_ref", "saida")
                                                              if rid in em_papel} or e.get("definicao")
        if defin:
            e["definicao"] = defin
            e["lado"], e["tf"], e["versao"] = defin.get("lado"), defin.get("tf"), rid
        e["backtest"] = {k: (painel.get(rid) or {}).get("backtest_treino_validacao", {}).get(k)
                         for k in ("n", "dias", "acontecimentos", "r_medio", "ic95_blocos_acontecimento", "profit_factor",
                                   "operacoes_por_semana")} if rid in painel else e.get("backtest")
        tf_doc = _ler(p(f"teste_final_{rid}.json"))
        if tf_doc and tf_doc.get("qualificacao_oos"):
            e["oos"] = tf_doc["qualificacao_oos"]
        elif rid in testes:
            t = testes[rid]["resultado"]
            e["oos"] = {"n": t.get("n"), "r_medio": t.get("r_medio"), "dias": t.get("dias_com_operacoes"),
                        "ic95_dia": t.get("ic95_r"), "p_vantagem": t.get("p_vantagem"),
                        "p_holm": round(min(1.0, (t.get("p_vantagem") or 1) * max(1, len(testes))), 6),
                        "nota": "teste final anterior ao motor de qualificacao (sem robustez/concentracao)"}
            e["oos"]["falhas"] = falhas_oos(e["oos"])
            e["oos"]["ok"] = False
        e["papel"] = avaliar_papel(fech.get(rid, []), falhas_criticas=1 if bloq.get(rid) else 0)
        e["metricas_papel"] = _metricas([o for o in fech.get(rid, []) if o.get("r") is not None])
        rr = reais.get(rid, [])
        e["real"] = {"fechadas": sum(1 for o in rr if o.get("r") is not None), "r_medio": _media([o["r"] for o in rr if o.get("r") is not None]),
                     "deslize_medio_pct": _media([o["slippage_pct"] for o in rr if o.get("slippage_pct") is not None]),
                     "papel_vs_real_r": _media([o["r"] - o["r_papel"] for o in rr if o.get("r") is not None and o.get("r_papel") is not None])}
        novo, porque = decidir(e, rid in em_papel, rid in testes, piloto_ok, rr, fech.get(rid, []))
        if novo == "VALIDATION" and rid not in testes:
            pedidos.append(rid)
        if novo != e.get("estado"):
            e["historico"].append({"t": now, "de": e.get("estado"), "para": novo, "motivo": porque})
            e["historico"] = e["historico"][-100:]
            e["desde"] = now
        e["estado"], e["motivo"] = novo, porque
        reg["estrategias"][rid] = e
    reg.update(t=now, pedidos_teste_final=pedidos, piloto_operacional=piloto_ok, criterios=C,
               aviso="registo central (17/11): APPROVED/ACTIVE so com todos os criterios; o executor real confere de novo")
    with open(p("estrategias_registo.json"), "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1, default=str)
    return reg


def decidir(e, em_papel, testada, piloto_ok, reais, fechadas):
    rid, est = e["id"], e.get("estado")
    if rid in REJEITADAS_POR_ORDEM:
        return "REJECTED", REJEITADAS_POR_ORDEM[rid]
    if est == "REJECTED":
        return "REJECTED", e.get("motivo") or "rejeitada"
    pa = e.get("papel") or {}
    if pa.get("acontecimentos", 0) >= C["papel_acontecimentos_min"] and (pa.get("ic95_acontecimento") or [0, 1])[1] < 0:
        return "REJECTED", f"papel prospetivo claramente negativo ({pa['acontecimentos']} acontecimentos, IC95 abaixo de 0)"
    if pa.get("acontecimentos", 0) >= 2 * C["papel_acontecimentos_min"] and (pa.get("r_medio") or 0) <= 0:
        return "REJECTED", f"papel prospetivo sem vantagem em {pa['acontecimentos']} acontecimentos"
    if testada:
        o = e.get("oos") or {}
        if not o.get("ok"):
            return "REJECTED", "teste final fora da amostra falhou: " + ", ".join((o.get("falhas") or [])[:6])
        if not pa.get("ok"):
            return "VALIDATION", "fora da amostra aprovado; papel ainda sem os minimos (30 fechadas, 30 acontecimentos, 14 dias, media > 0)"
        deg = degradada(fechadas, reais)
        if deg:
            return "SUSPENDED", "degradacao: " + deg
        if est == "SUSPENDED" and len([o for o in fechadas if (o.get("fechada_em") or 0) > (e.get("desde") or 0)]) < C["degradacao_janela"]:
            return "SUSPENDED", "suspensa: espera 30 acontecimentos novos sem degradacao"
        if piloto_ok:
            return "ACTIVE_REAL", "todos os criterios cumpridos e piloto real operacional"
        return "APPROVED_REAL", "todos os criterios cumpridos; piloto real ainda nao operacional"
    if em_papel:
        bt = e.get("backtest") or {}
        prev = (bt.get("operacoes_por_semana") or 0) * 8.5                # teste final ~60 dias
        if pa.get("ok") and prev >= C["oos_n_min"]:
            return "VALIDATION", "papel cumpre os minimos e o backtest preve amostra suficiente: teste final pedido"
        if pa.get("ok"):
            return "PAPER_TRADING", f"papel cumpre os minimos mas o teste final teria ~{prev:.0f} operacoes (< 100): espera"
        return "PAPER_TRADING", (f"papel: {pa.get('fechadas', 0)} fechadas, {pa.get('acontecimentos', 0)} acontecimentos, "
                                 f"{pa.get('dias', 0)} dias")
    return "EXPLORATORY", "sem amostra/expectativa suficientes no backtest; fora do papel"


if __name__ == "__main__":
    r = atualizar(sys.argv[1])
    print(json.dumps({k: v["estado"] for k, v in r["estrategias"].items()}, ensure_ascii=False))
