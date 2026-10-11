"""Arena: todas as estrategias competem com as mesmas regras (decisao do Rui,
2026-10-11).

Concorrentes
  - estrategias ao vivo (recuo, quebra, sweep, ...): contam TODOS os sinais
    que emitiram, executados ou nao, porque mede-se a estrategia e nao a
    execucao do Rui;
  - papel do Oversold Bounce (G0, V1, V2, V3);
  - papel da tendencia diaria.
Medida comum: R por operacao, ja com comissoes.

Teste contra o acaso: quando uma operacao fecha, sao criadas operacoes de
controlo na mesma moeda, com entrada numa vela de 4H ao acaso ate 90 velas
(15 dias) antes ou depois, e a MESMA geometria (stop e objetivos a mesma
distancia percentual, mesmas vendas parciais, mesmos custos). E o metodo de
tools/random_baseline.py. A tendencia diaria sai por um minimo movel e nao
tem geometria fixa: e julgada so pelo R medio.

Regras (declaradas antes de haver resultados)
  MORRE   com pelo menos 10 operacoes e R medio <= -0,5R (morte rapida,
          decisao do Rui: luta ate a morte), ou
          com pelo menos 20 operacoes, se o R medio for <= -0,2R ou nao
          passar a mediana das entradas ao acaso. Uma estrategia de papel
          morta deixa de abrir operacoes. As estrategias ao vivo NUNCA sao
          desligadas pela arena (opcao B do Rui): ficam marcadas e
          continuam a dar sinais reais.
  SOBE    com pelo menos 30 operacoes, R medio positivo e acima do
          percentil 95 das entradas ao acaso: e proposta ao Rui para
          dinheiro real. A decisao e sempre dele.
"""
import bisect
import random

from . import trade

TF = 14400
WINDOW, REPS, MAX_BARS = 90, 200, 6 * 90
MIN_DEATH, MIN_PROMO, DEATH_R = 20, 30, -0.2
FAST_N, FAST_R = 10, -0.5        # morte rapida: claramente mau ao fim de 10
MIN_ALIVE = 5                    # abaixo disto a investigacao tem de criar lutadores
FEE_PCT, SLIP_PCT = 0.25, 0.1
NAMES = {"PULLBACK": "Recuo (ao vivo)", "BREAKOUT": "Quebra (ao vivo)",
         "LIQUIDITY_SWEEP": "Sweep (ao vivo)", "RANGE": "Range (ao vivo)",
         "TREND_DAILY": "Tendência diária (papel)",
         "BOUNCE_G0": "Oversold Bounce original (papel)",
         "BOUNCE_V1": "Oversold Bounce + saída ao vivo (papel)",
         "BOUNCE_V2": "Oversold Bounce stop curto 2R (papel)",
         "BOUNCE_V3": "Oversold Bounce stop original 2R (papel)",
         "REJEITADOS": "Setups rejeitados pelos filtros (papel)"}
# cada concorrente e um analista com nome proprio (decisao do Rui)
PERSONA = {"BREAKOUT": "Bruno", "PULLBACK": "Rita", "LIQUIDITY_SWEEP": "Simão",
           "RANGE": "Raquel", "TREND_DAILY": "Teodoro", "BOUNCE_G0": "Gaspar",
           "BOUNCE_V1": "Vasco", "BOUNCE_V2": "Vera", "BOUNCE_V3": "Violeta",
           "REJEITADOS": "Óscar"}
POOL = ["Leonor", "Duarte", "Matilde", "Afonso", "Carolina", "Martim", "Beatriz",
        "Lourenço", "Mariana", "Salvador", "Francisca", "Henrique", "Clara",
        "Tomás", "Joana", "Miguel", "Catarina", "Diogo", "Lara", "Gonçalo"]


def persona(k):
    """Nome do analista que representa o concorrente k (estavel: o mesmo
    concorrente tem sempre o mesmo nome; os novos recebem um da lista)."""
    base = k.replace("_SHORT", "")
    if base in PERSONA:
        return PERSONA[base] + (" Jr." if k.endswith("_SHORT") else "")
    h = sum(ord(c) * (i + 1) for i, c in enumerate(base))
    return POOL[h % len(POOL)]

CTRL_PER_SCAN = 6            # operacoes de controlo novas por scan (tempo)


def _name(k):
    base = k.replace("_SHORT", "")
    return NAMES.get(base, base.title()) + (" short" if k.endswith("_SHORT")
                                            else "")


def trades(state):
    """[(concorrente, chave unica, operacao)] de todas as fontes."""
    out = []
    for r in state.get("ledger", []):
        if r.get("kind") != "4H" or r.get("status") != "CLOSED" or \
                r.get("result_r") is None or not r.get("entry"):
            continue
        k = r["strategy"] + ("_SHORT" if r.get("side") == "SHORT" else "")
        out.append((k, r["id"], {
            "asset": r["asset"], "side": r.get("side", "LONG"),
            "entry": r["entry"], "stop": r["stop"], "tp": r["tp"],
            "partials": r.get("partials") or [50, 30, 20],
            "opened_at": r.get("opened_at"), "closed_at": r.get("closed_at"),
            "r": r["result_r"], "breakeven": True}))
    for g, b in (state.get("paper_bounce", {}).get("geo") or {}).items():
        for c in b.get("closed", []):
            k = "BOUNCE_" + g
            out.append((k, f"{k}-{c['asset']}-{c['opened_at']}", dict(
                c, side="LONG")))
    for c in state.get("paper_shadow", {}).get("closed", []):
        out.append(("REJEITADOS", f"SHADOW-{c['asset']}-{c['opened_at']}",
                    dict(c, side="LONG")))
    for c in state.get("paper_trend", {}).get("closed", []):
        out.append(("TREND_DAILY", f"TREND-{c.get('asset')}-{c.get('exit_t')}",
                    {"asset": c.get("asset"), "r": c.get("r"),
                     "no_geometry": True}))
    return out


def control_rs(c4, t_entry, geo, side, rng, reps=REPS):
    """R de operacoes de controlo ao acaso (lista, pode ser curta se o
    historico disponivel nao chegar)."""
    ts = [b["t"] for b in c4]
    i = bisect.bisect_right(ts, t_entry) - 1
    if i < 0:
        return []
    lo, hi = max(0, i - WINDOW), min(len(c4) - 2, i + WINDOW)
    out = []
    for _ in range(reps):
        j = rng.randint(lo, hi)
        b = c4[j]
        e = b["o"]
        plan = {"stop": e * (1 + geo["stop"]), "partials": geo["partials"],
                "tp": [e * (1 + x) for x in geo["tp"]]}
        pos = trade.open_position(plan, e, b["t"], FEE_PCT, SLIP_PCT,
                                  breakeven=geo["breakeven"], side=side)
        k = j
        while not pos["closed"] and k < len(c4) and k - j <= MAX_BARS:
            x = c4[k]
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
            k += 1
        if pos["closed"]:
            out.append(round(pos["r"], 3))
    return out


def geometry(t):
    e = t["entry"]
    if not e or not t.get("stop") or not t.get("tp"):
        return None
    return {"stop": t["stop"] / e - 1, "tp": [x / e - 1 for x in t["tp"]],
            "partials": list(t["partials"]),
            "breakeven": bool(t.get("breakeven", True))}


def verdict(n, mean, med, p95, has_ctrl):
    if n >= MIN_PROMO and mean > 0 and has_ctrl and p95 is not None \
            and mean > p95:
        return "SOBE"
    if n >= FAST_N and mean <= FAST_R:             # morte rapida
        return "MORTA"
    if n >= MIN_DEATH and (mean <= DEATH_R or (has_ctrl and med is not None
                                               and mean <= med)):
        return "MORTA"
    return "A COMPETIR"


def _dist(ctrl_lists, rng, reps=1000):
    """Distribuicao do R medio ao acaso: uma operacao de controlo por
    operacao real em cada repeticao."""
    ls = [c for c in ctrl_lists if c]
    if not ls:
        return None, None
    means = sorted(sum(rng.choice(c) for c in ls) / len(ls) for _ in range(reps))
    return means[len(means) // 2], means[int(0.95 * (len(means) - 1))]


def update(state, bars, now, seed=None):
    """Calcula controlos em falta (no maximo CTRL_PER_SCAN por scan) e a
    classificacao. bars: {ativo: velas de 4H fechadas}. Devolve o resumo."""
    ar = state.setdefault("arena", {"ctrl": {}, "status": {}})
    ctrl = ar.setdefault("ctrl", {})
    rng = random.Random(seed if seed is not None else now)
    all_t = trades(state)
    done = 0
    for k, key, t in all_t:
        if key in ctrl or t.get("no_geometry") or done >= CTRL_PER_SCAN:
            continue
        c4, geo = bars.get(t["asset"]), geometry(t)
        if not c4 or not geo or not t.get("opened_at"):
            continue
        side = "SHORT" if t.get("side") == "SHORT" else "LONG"
        ctrl[key] = control_rs(c4, t["opened_at"], geo, side, rng)
        done += 1
    keys = {key for _, key, _ in all_t}
    for key in [x for x in ctrl if x not in keys]:      # operacoes ja apagadas
        del ctrl[key]
    groups = {}
    for k, key, t in all_t:
        groups.setdefault(k, []).append((key, t))
    board = []
    for k, ts in groups.items():
        rs = [t["r"] for _, t in ts if t.get("r") is not None]
        if not rs:
            continue
        mean = sum(rs) / len(rs)
        lists = [ctrl.get(key) for key, t in ts]
        has_ctrl = not any(t.get("no_geometry") for _, t in ts) and \
            sum(1 for c in lists if c) >= max(1, len(rs) // 2)
        med, p95 = _dist(lists, rng) if has_ctrl else (None, None)
        v = verdict(len(rs), mean, med, p95, has_ctrl)
        prev = ar["status"].get(k)
        ar["status"][k] = v
        board.append({"id": k, "name": _name(k), "persona": persona(k), "n": len(rs),
                      "wins": sum(1 for x in rs if x > 0),
                      "avg_r": round(mean, 3), "total_r": round(sum(rs), 2),
                      "ultimas": [round(x, 2) for x in rs[-10:]],
                      "acaso_mediana": None if med is None else round(med, 3),
                      "acaso_p95": None if p95 is None else round(p95, 3),
                      "estado": v, "mudou": (prev or "A COMPETIR") != v,
                      "live": not (k.startswith("BOUNCE_") or k in ("TREND_DAILY", "REJEITADOS"))})
    for k0 in ("BOUNCE_G0", "BOUNCE_V1", "BOUNCE_V2", "BOUNCE_V3",
               "REJEITADOS"):                    # papel ainda sem operacoes
        if not any(b["id"] == k0 for b in board):
            board.append({"id": k0, "name": _name(k0),
                          "persona": persona(k0),
                          "n": 0, "wins": 0, "avg_r": None, "total_r": 0,
                          "acaso_mediana": None, "acaso_p95": None,
                          "estado": "A COMPETIR", "mudou": False,
                          "live": False})
    order = {"SOBE": 0, "A COMPETIR": 1, "MORTA": 2}
    board.sort(key=lambda b: (order[b["estado"]],
                              -(b["avg_r"] if b["avg_r"] is not None else -9),
                              -b["n"]))
    # o Oscar (rejeitados) e um medidor, nao conta para o minimo de lutadores
    alive = sum(1 for b in board if b["estado"] != "MORTA"
                and b["id"] != "REJEITADOS")
    return {"atualizado": int(now), "vivos": alive, "minimo_vivos": MIN_ALIVE,
            "recrutar": alive < MIN_ALIVE, "regras": {
        "morre": f"≥{FAST_N} operações com R médio ≤ {str(FAST_R).replace('.', ',')}R (morte rápida), ou "
                 f"≥{MIN_DEATH} operações e R médio ≤ {str(DEATH_R).replace('.', ',')}R ou abaixo "
                 "da mediana ao acaso",
        "sobe": f"≥{MIN_PROMO} operações, R médio positivo e acima do "
                "percentil 95 ao acaso"}, "classificacao": board}


def dead_paper(state):
    """Concorrentes de papel mortos (deixam de abrir operacoes)."""
    return {k for k, v in state.get("arena", {}).get("status", {}).items()
            if v == "MORTA" and (k.startswith("BOUNCE_") or k == "TREND_DAILY")}


def events(summary, now):
    """Avisos de mudanca de estado (morte ou subida)."""
    out = []
    for b in summary.get("classificacao", []):
        if b["mudou"] and b["estado"] in ("MORTA", "SOBE"):
            out.append({"t": now, "event": "ARENA", "id": f"arena-{b['id']}",
                        "name": f"{b['persona']} ({b['name']})", "estado": b["estado"], "n": b["n"],
                        "avg_r": b["avg_r"], "live": b["live"],
                        "real": False})
    return out
