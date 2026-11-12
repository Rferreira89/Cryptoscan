"""(12/11 15:44, ordem do Rui: "autorizo a ativacao de estrategias LONG em producao quando cada uma cumprir ...; nao
precisas de pedir nova autorizacao") Porta automatica do LONG real na Bybit UE.

Uma estrategia LONG so passa a dinheiro real quando TODOS os criterios da ordem estao provados, cada um com a sua
fonte publica (nada aqui e opiniao):
  1. expectativa liquida > 0 depois de custos e
  2. validacao fora da amostra e
  4. correcao para multiplos testes:
       a descoberta semanal (ramo descoberta-long, tools/descoberta_long: periodos fixos, custos reais, Holm)
       classifica-a "VANTAGEM DEMONSTRADA" na corretora bybit_ue e numa fase do mercado;
  3. robustez a pequenas alteracoes dos parametros: a mesma linha tem "robusta": true (grelha de vizinhos);
  papel: validacao em papel continua com >= PAPEL_MIN operacoes fechadas, R/op > 0 e PF > 1 (registo PAPER do
       motor ou tools/papel_transversal);
  5./6. stops tecnicos, dimensionamento e testes de execucao: so estrategias com motor ao vivo no registo do
       scanner (engine/promo.registry) entram, porque so essas passam pelo mesmo plano, stop e executor testados;
  7. risco: entra a 1% por operacao, 1 posicao, dentro do teto agregado de 5% da conta (engine/promo.risco_aberto).
Sai sozinha (volta a papel) quando deixa de cumprir: a avaliacao corre em cada ciclo.
Sem dinheiro: tudo em R e classes."""

TETO_LONG_PCT = 1.0
PAPEL_MIN = 30
CLASSE_OK = "VANTAGEM DEMONSTRADA"


def _papel(estrategia, ledger, papel_transversal):
    rs = [float(r["result_r"]) for r in ledger or []
          if r.get("strategy") == estrategia and r.get("mode") == "PAPER" and r.get("status") == "CLOSED"
          and r.get("result_r") is not None]
    for o in ((papel_transversal or {}).get("fechadas") or []):
        if o.get("k") == estrategia and o.get("r") is not None:
            rs.append(float(o["r"]))
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return {"n": len(rs), "r_op": round(sum(rs) / len(rs), 4) if rs else None,
            "pf": round(g / p, 3) if p > 0 else (None if not rs else float("inf"))}


def avaliar(descoberta, ledger, papel_transversal, motores, inicio=0):
    """(pilotos, relatorio). descoberta: json semanal (lista "resultados"); motores: estrategias com motor ao vivo.
    pilotos: [{"estrategia", "fase", "teto_pct": 1, "max_posicoes": 1, "perda_max_r": -8, "juro_max_r": 0.06,
    "dias_max": 20, "inicio", "lado": "LONG", "porta": True}]."""
    linhas = [l for l in ((descoberta or {}).get("resultados") or []) if l.get("corretora") == "bybit_ue"]
    rel, pilotos = {}, []
    for l in linhas:
        k, fase = l.get("estrategia"), l.get("fase")
        falta = []
        classe = l.get("classe") or l.get("veredicto")      # ficheiros antigos da descoberta: "veredicto"
        if str(classe or "").upper() != CLASSE_OK:
            falta.append(f"classe {classe}")
        if l.get("robusta") is not True:
            falta.append("robustez a parametros vizinhos nao provada")
        pp = _papel(k, ledger, papel_transversal)
        if pp["n"] < PAPEL_MIN:
            falta.append(f"papel {pp['n']}/{PAPEL_MIN} operacoes")
        elif not (pp["r_op"] or 0) > 0 or not (pp["pf"] or 0) > 1:
            falta.append(f"papel sem vantagem (R/op {pp['r_op']}, PF {pp['pf']})")
        if k not in (motores or ()):
            falta.append("sem motor ao vivo no scanner")
        chave = f"{k}|{fase}"
        # "motivos" (e nao "falta": a publicacao publica apaga chaves comecadas por "falta", pensadas para dinheiro)
        rel[chave] = {"motivos": falta, "papel": pp, "classe": classe}
        if not falta:
            pilotos.append({"estrategia": k, "fase": fase, "teto_pct": TETO_LONG_PCT, "max_posicoes": 1,
                            "perda_max_r": -8, "juro_max_r": 0.06, "dias_max": 20, "inicio": inicio,
                            "lado": "LONG", "porta": True})
    return pilotos, rel


def piloto_de(cfg, estrategia):
    """A configuracao de piloto que se aplica a esta estrategia: o piloto principal (SHORT_TURTLE) ou um LONG da
    porta. O teto de um LONG nunca passa de 1%, venha de onde vier."""
    pl = (cfg or {}).get("piloto") or {}
    if pl and pl.get("estrategia") == estrategia:
        return pl
    for p in (cfg or {}).get("pilotos_long") or []:
        if p.get("estrategia") == estrategia:
            return dict(p, teto_pct=min(float(p.get("teto_pct") or TETO_LONG_PCT), TETO_LONG_PCT))
    return {}


def reduzir(descoberta, papel):
    """O minimo a guardar no estado (sem dinheiro): linhas bybit_ue da descoberta e os R do papel continuo."""
    lin = [{k: l.get(k) for k in ("estrategia", "fase", "corretora", "classe", "veredicto", "robusta")}
           for l in ((descoberta or {}).get("resultados") or []) if l.get("corretora") == "bybit_ue"]
    fech = [{"k": o.get("k"), "r": o.get("r")} for o in ((papel or {}).get("fechadas") or [])][-2000:]
    return {"descoberta": {"resultados": lin}, "papel": {"fechadas": fech}}


def aplicar(cfg, state, motores, now):
    """cfg com os LONG que passam a porta acrescentados a pilotos_long, real_autorizados e campeoes_estudo da sua
    fase; relatorio em state["porta_long"]. Sem dados de evidencia: nada muda."""
    dados = state.get("porta_dados") or {}
    inicio = int((state.get("porta_long") or {}).get("inicio") or now)
    pilotos, rel = avaliar(dados.get("descoberta"), state.get("ledger"), dados.get("papel"), motores, inicio)
    state["porta_long"] = {"t": int(now), "inicio": inicio, "pilotos": [p["estrategia"] for p in pilotos],
                           "relatorio": rel}
    if not pilotos:
        return cfg
    c = dict(cfg)
    c["pilotos_long"] = list(cfg.get("pilotos_long") or []) + pilotos
    c["real_autorizados"] = sorted(set(cfg.get("real_autorizados") or []) | {p["estrategia"] for p in pilotos})
    est = {f: list(v) for f, v in (cfg.get("campeoes_estudo") or {}).items()}
    for p in pilotos:
        est.setdefault(p["fase"], [])
        if p["estrategia"] not in est[p["fase"]]:
            est[p["fase"]].append(p["estrategia"])
    c["campeoes_estudo"] = est
    return c
