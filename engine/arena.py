"""Arena: todas as estrategias competem com as mesmas regras (decisao do Rui,
2026-10-11).

Concorrentes
  - estrategias ao vivo (recuo, quebra, sweep, tendencia): contam TODOS os sinais
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
          morta deixa de abrir operacoes; uma ao vivo e desligada (ver
          MORTE AUTOMATICA).
  FORMA RECENTE (decisao do Rui, 2026-10-13: "os lutadores nao estao a
          morrer"): de hora a hora tools/arena_ringue.py poe cada lutador a
          combater nos ultimos 90 dias de mercado em todas as moedas, com
          as funcoes do sistema ao vivo e o mesmo teste contra o acaso. As
          mesmas regras de morte aplicam-se a essa amostra (dezenas de
          operacoes em vez de 2 ou 3). A morte e definitiva: quem morre nao volta (o lugar
          passa a ser de um sucessor da investigacao).
  MORTE AUTOMATICA (decisao do Rui, 2026-10-13: "as estrategias falham e
          morrem automaticamente, sem eu ter de intervir"): uma estrategia
          ao vivo que morre e desligada logo (state["disabled"], motivo
          "arena") e deixa de emitir sinais reais; as operacoes ja abertas
          continuam a ser acompanhadas ate fecharem. Substitui a opcao B.
  QUALIFICA / CAMPEAO (decisao do Rui, 2026-10-13): ver engine/promo.py.
          Com 20 ou mais operacoes no combate, R medio positivo e acima do
          percentil 95 do acaso, o lutador opera em papel ao vivo; o melhor
          qualificado da lista revista da sinais reais.
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
LOSER_N = 50                     # perdedor persistente: 50+ operacoes com R medio negativo
REGIME_STABLE = 7 * 86400        # regime de mercado firme ha 7 dias antes de um regresso
LONG_MIN_N = 15                  # operacoes minimas no ringue longo para decidir um regresso
REGIME_PT = {"subida": "tendência de subida", "queda": "tendência de descida", "lateral": "lateral"}


def market_regime(btc4=None, btc1d=None):
    """Regime do mercado pelo BTC diario: subida, queda ou lateral. Aceita
    velas diarias (btc1d, preferidas) ou de 4H (agregadas em dias)."""
    from . import backtest as B
    d = list(btc1d or []) or B.daily(btc4 or [])
    if len(d) < 200:
        return None
    c = [x["c"] for x in d]
    s50, s200 = sum(c[-50:]) / 50, sum(c[-200:]) / 200
    r30 = c[-1] / c[-31] - 1
    if c[-1] > s50 > s200 and r30 > 0.08:
        return "subida"
    if c[-1] < s50 < s200 and r30 < -0.08:
        return "queda"
    return "lateral"


def base_key(k):
    """TURTLE_R2 -> TURTLE (lutador que regressou com nome novo)."""
    import re
    return re.sub(r"_R\d+$", "", k)


def rebirth(state, now, regime):
    """Regresso dos mortos (decisao do Rui, 2026-10-14: "se for preciso voltar
    a combater com um nome novo, voltam"): quando o regime de mercado muda e
    fica firme 7 dias, cada familia morta noutro regime volta ao ringue com
    um nome novo e registo limpo (so contam operacoes a partir do regresso).
    Volta a morrer pelas mesmas regras. Devolve os regressos novos."""
    if not regime:
        return []
    ar = state.setdefault("arena", {})
    mk = state.setdefault("mercado", {})
    if mk.get("regime") != regime:
        mk.update(regime=regime, desde=int(now))
    ren = ar.setdefault("renascidos", {})
    out = []
    for k, m in (ar.get("mortos") or {}).items():
        m.setdefault("regime", regime)        # morreu no regime em que o vimos morrer
        if m.get("renasceu") or now - mk["desde"] < REGIME_STABLE:
            continue
        b = base_key(k)
        # o ringue longo (365 dias por regime) diz se a familia presta neste regime
        lg = (((ar.get("longo") or {}).get("lutadores") or {}).get(b) or {}).get("por_regime") or {}
        ev = lg.get(regime)
        prova = bool(ev and (ev.get("n") or 0) >= LONG_MIN_N and (ev.get("avg_r") or 0) > 0
                     and ev.get("acaso_p95") is not None and ev["avg_r"] > ev["acaso_p95"])
        if m["regime"] == regime:
            # mesmo regime em que morreu: so volta se o ano inteiro mostrar que
            # ganha neste regime (a morte veio de uma janela de 90 dias misturada)
            if not prova or now - (m.get("t") or now) < REGIME_STABLE:
                continue
        elif ev and (ev.get("n") or 0) >= LONG_MIN_N and not prova:
            continue                           # regime novo, mas o ano mostra que perde nele
        g = int(k[len(b) + 2:]) + 1 if k != b else 2
        nk = f"{b}_R{g}"
        ren[nk] = {"base": b, "desde": int(now), "de": k, "regime": regime}
        m["renasceu"] = nk
        out.append({"t": int(now), "event": "ARENA_REGRESSO", "id": f"regresso-{nk}",
                    "novo": nk, "nome": persona(nk), "antes": persona(k), "regime": REGIME_PT[regime],
                    "real": False})
    return out
MIN_ALIVE = 5                    # abaixo disto a investigacao tem de criar lutadores
FEE_PCT, SLIP_PCT = 0.25, 0.1
NAMES = {"PULLBACK": "Recuo (ao vivo)", "BREAKOUT": "Quebra (ao vivo)",
         "LIQUIDITY_SWEEP": "Sweep (ao vivo)", "RANGE": "Range (ao vivo)",
         "TREND_DAILY": "Tendência diária",
         "BOUNCE_G0": "Oversold Bounce original (papel)",
         "BOUNCE_V1": "Oversold Bounce + saída ao vivo (papel)",
         "BOUNCE_V2": "Oversold Bounce stop curto 2R (papel)",
         "BOUNCE_V3": "Oversold Bounce stop original 2R (papel)",
         "REJEITADOS": "Setups rejeitados pelos filtros (papel)",
         "BOUNCE_1H": "Oversold Bounce em 1H (combate)",
         "BOUNCE_X30": "Oversold Bounce RSI 30", "DIP_TREND": "Recuo em tendência forte",
         "CAPITULACAO": "Capitulação com volume",
         "BOUNCE_FLUXO": "Bounce com compradores agressivos", "BOUNCE_FORTE": "Bounce em moeda forte",
         "BOUNCE_SQUEEZE": "Bounce com shorts em aperto", "BOUNCE_ISOLADA": "Bounce com o BTC estável",
         "BOUNCE_NOREACT": "Bounce que sai sem reação", "BOUNCE_TRAIL": "Bounce com stop que sobe",
         "BOUNCE_HORAS": "Bounce só em horas líquidas",
         "BOUNCE_DESALAV": "Bounce depois da desalavancagem",
         "BOUNCE_MACRO": "Bounce com macroeconomia favorável",
         "BOUNCE_MEDO": "Bounce depois de medo na macroeconomia",
         "BOUNCE_ABSORCAO": "Bounce com absorção das vendas",
         "BOUNCE_LSR": "Bounce com vendedores a descoberto em excesso",
         "TURTLE": "Tartarugas: rompimento de 20 dias", "SQUEEZE_BB": "Compressão de volatilidade",
         "MOMENTUM": "Momentum: as 5 mais fortes da semana",
         "BRK_ESPACO": "Rompimento com espaço (sem entrada tardia)",
         "RETESTE": "Reteste do nível rompido",
         "BOUNCE_X30_PAVIO": "RSI 30 com stop abaixo dos pavios",
         "BOUNCE_X30_LIQ": "RSI 30 com stop abaixo da liquidez",
         "REVERSAO_INTERVALO": "Reversão à média no mercado lateral",
         "SHORT_X30": "Short: sobrecompra a virar", "SHORT_FLUXO": "Short: vendedores agressivos",
         "SHORT_TURTLE": "Short: quebra do mínimo de 20 dias", "SHORT_SQUEEZE": "Short: compradores alavancados a pagar",
         "SHORT_ISOLADA": "Short: subida isolada com o BTC parado"}
# cada concorrente e um analista com nome proprio (decisao do Rui)
PERSONA = {"BREAKOUT": "Bruno", "PULLBACK": "Rita", "LIQUIDITY_SWEEP": "Simão",
           "RANGE": "Raquel", "TREND_DAILY": "Teodoro", "BOUNCE_G0": "Gaspar",
           "BOUNCE_V1": "Vasco", "BOUNCE_V2": "Vera", "BOUNCE_V3": "Violeta",
           "REJEITADOS": "Óscar", "BOUNCE_1H": "Hélio",
           "BOUNCE_X30": "Xavier", "DIP_TREND": "Diana", "CAPITULACAO": "Caio",
           "BOUNCE_FLUXO": "Flávio", "BOUNCE_FORTE": "Fernanda", "BOUNCE_SQUEEZE": "Sérgio",
           "BOUNCE_ISOLADA": "Isabel", "BOUNCE_NOREACT": "Nélson", "BOUNCE_TRAIL": "Tânia",
           "BOUNCE_HORAS": "Horácio", "BOUNCE_DESALAV": "Dália",
           "BOUNCE_MACRO": "Mário", "BOUNCE_MEDO": "Vicente",
           "BOUNCE_ABSORCAO": "Abel", "BOUNCE_LSR": "Leandro",
           "TURTLE": "Rodrigo", "SQUEEZE_BB": "Beatriz", "MOMENTUM": "Mónica",
           "BRK_ESPACO": "Bernardo", "RETESTE": "Renato",
           "BOUNCE_X30_PAVIO": "Paulina", "BOUNCE_X30_LIQ": "Lucas",
           "REVERSAO_INTERVALO": "Inês",
           "SHORT_X30": "Xénia", "SHORT_FLUXO": "Filipa", "SHORT_TURTLE": "Ramiro",
           "SHORT_SQUEEZE": "Sara", "SHORT_ISOLADA": "Irene"}
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
    free = [n for n in POOL if n not in set(PERSONA.values())]   # sem nomes repetidos
    return free[h % len(free)]

CTRL_PER_SCAN = 6            # operacoes de controlo novas por scan (tempo)


def _name(k):
    b0 = base_key(k)
    base = b0.replace("_SHORT", "")
    return NAMES.get(base, base.title()) + (" short" if b0.endswith("_SHORT") else "") + \
        (" (regresso)" if b0 != k else "")


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
    # operacoes reais do campeao (estrategia BOUNCE_xx no registo): a mesma
    # entrada no papel do Bounce nao conta duas vezes
    real = {(r.get("strategy"), r["asset"], (r.get("opened_at") or 0) // TF)
            for r in state.get("ledger", []) if str(r.get("strategy")).startswith("BOUNCE_")}
    for g, b in (state.get("paper_bounce", {}).get("geo") or {}).items():
        for c in b.get("closed", []):
            k = "BOUNCE_" + g
            if (k, c["asset"], (c.get("opened_at") or 0) // TF) in real:
                continue
            out.append((k, f"{k}-{c['asset']}-{c['opened_at']}", dict(
                c, side="LONG")))
    for c in state.get("paper_shadow", {}).get("closed", []):
        out.append(("REJEITADOS", f"SHADOW-{c['asset']}-{c['opened_at']}",
                    dict(c, side="LONG")))
    for k, b in (state.get("paper_ring") or {}).items():
        for c in b.get("closed", []):
            out.append((k, f"RING-{k}-{c['asset']}-{c['opened_at']}",
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
        # a mesma gestao da operacao real: tempo maximo, saida sem reacao e
        # stop que acompanha o lucro (quando o lutador os usa)
        plan = {"stop": e * (1 + geo["stop"]), "partials": geo["partials"],
                "tp": [e * (1 + x) for x in geo["tp"]],
                "max_hold_s": geo.get("max_hold_s"), "no_react_s": geo.get("no_react_s"),
                "trail_r": geo.get("trail_r")}
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
    # revisao de 2026-10-13: quem perde dinheiro em 50+ operacoes morre, mesmo
    # que o acaso ainda seja pior (perder menos do que o acaso nao chega)
    if n >= LOSER_N and mean < 0:
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


def _forma_rows(forma):
    return (forma or {}).get("lutadores") or {}


def update(state, bars, now, seed=None, forma=None):
    """Calcula controlos em falta (no maximo CTRL_PER_SCAN por scan) e a
    classificacao. bars: {ativo: velas de 4H fechadas}. forma: resultado de
    tools/arena_ringue.py (ou None: usa o ultimo guardado). Devolve o resumo."""
    ar = state.setdefault("arena", {"ctrl": {}, "status": {}})
    if forma and _forma_rows(forma):
        ar["forma"] = {"atualizado": forma.get("atualizado"),
                       "janela_dias": forma.get("janela_dias"),
                       "moedas": forma.get("moedas"),
                       "lutadores": _forma_rows(forma)}
    fm = ar.get("forma") or {}
    frows = _forma_rows(fm)
    mortos = ar.setdefault("mortos", {})
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
    for k in frows:                          # lutadores so com forma recente
        groups.setdefault(k, [])
    for k, ts in groups.items():
        rs = [t["r"] for _, t in ts if t.get("r") is not None]
        f = frows.get(k)
        if not rs and not (f and f.get("n")) and k not in mortos:
            continue
        mean = sum(rs) / len(rs) if rs else None
        lists = [ctrl.get(key) for key, t in ts]
        has_ctrl = bool(rs) and not any(t.get("no_geometry") for _, t in ts) and \
            sum(1 for c in lists if c) >= max(1, len(rs) // 2)
        med, p95 = _dist(lists, rng) if has_ctrl else (None, None)
        v = verdict(len(rs), mean, med, p95, has_ctrl) if rs else "A COMPETIR"
        motivo = "ao vivo" if v == "MORTA" else None
        vf = (f or {}).get("veredicto")
        if vf == "MORTA" and v != "MORTA":       # a forma recente so mata
            v, motivo = "MORTA", f"forma recente ({fm.get('janela_dias', 90)} dias)"
        prev = ar["status"].get(k)
        if k in mortos:                          # a morte e definitiva
            v, motivo = "MORTA", mortos[k].get("motivo")
        elif v == "MORTA":
            mortos[k] = {"t": int(now), "motivo": motivo,
                         "n": (f or {}).get("n") if motivo and motivo.startswith("forma") else len(rs),
                         "avg_r": (f or {}).get("avg_r") if motivo and motivo.startswith("forma") else round(mean, 3)}
        ar["status"][k] = v
        row = {"id": k, "name": _name(k), "persona": persona(k), "n": len(rs),
               "wins": sum(1 for x in rs if x > 0),
               "avg_r": None if mean is None else round(mean, 3),
               "total_r": round(sum(rs), 2),
               "ultimas": [round(x, 2) for x in rs[-10:]],
               "acaso_mediana": None if med is None else round(med, 3),
               "acaso_p95": None if p95 is None else round(p95, 3),
               "estado": v, "mudou": (prev or "A COMPETIR") != v,
               "motivo": motivo if v == "MORTA" else None,
               "morte": mortos.get(k),
               "live": not (k.startswith("BOUNCE_") or k == "REJEITADOS")}
        if f:
            row["forma"] = {x: f.get(x) for x in ("n", "wins", "avg_r", "total_r",
                                                  "ultimas", "acaso_mediana",
                                                  "acaso_p95", "veredicto")}
        board.append(row)
    for k0 in ("BOUNCE_G0", "BOUNCE_V1", "BOUNCE_V2", "BOUNCE_V3",
               "REJEITADOS"):                    # papel ainda sem operacoes
        if not any(b["id"] == k0 for b in board):
            st0 = "MORTA" if k0 in mortos else "A COMPETIR"
            board.append({"id": k0, "name": _name(k0),
                          "persona": persona(k0),
                          "n": 0, "wins": 0, "avg_r": None, "total_r": 0,
                          "ultimas": [],
                          "acaso_mediana": None, "acaso_p95": None,
                          "estado": st0, "mudou": False,
                          "motivo": (mortos.get(k0) or {}).get("motivo"),
                          "morte": mortos.get(k0), "live": False})
    order = {"SOBE": 0, "A COMPETIR": 1, "MORTA": 2}

    def score(b):                            # forma recente pesa mais (amostra maior)
        f = b.get("forma") or {}
        x = f.get("avg_r") if f.get("n") else b["avg_r"]
        return -(x if x is not None else -9)
    board.sort(key=lambda b: (order[b["estado"]], score(b),
                              -b["n"] - (b.get("forma") or {}).get("n", 0)))
    # o Oscar (rejeitados) e um medidor, nao conta para o minimo de lutadores
    alive = sum(1 for b in board if b["estado"] != "MORTA"
                and b["id"] != "REJEITADOS")
    return {"atualizado": int(now), "vivos": alive, "minimo_vivos": MIN_ALIVE,
            "forma": {x: fm.get(x) for x in ("atualizado", "janela_dias", "moedas")} if fm else None,
            "recrutar": alive < MIN_ALIVE, "regras": {
        "morre": f"≥{FAST_N} operações com R médio ≤ {str(FAST_R).replace('.', ',')}R (morte rápida), ou "
                 f"≥{MIN_DEATH} operações e R médio ≤ {str(DEATH_R).replace('.', ',')}R ou abaixo "
                 f"da mediana ao acaso, ou ≥{LOSER_N} operações com R médio negativo",
        "sobe": f"≥{MIN_PROMO} operações, R médio positivo e acima do "
                "percentil 95 ao acaso",
        "forma": "de hora a hora cada lutador combate nos últimos 90 dias de "
                 "mercado, em todas as moedas, com as mesmas regras de morte; "
                 "a forma recente só mata, nunca promove; a morte é definitiva"}, "classificacao": board}


LIVE_KILLABLE = ("PULLBACK", "BREAKOUT", "LIQUIDITY_SWEEP", "RANGE",
                 "TREND_DAILY")


def auto_disable(state, summary, now):
    """Desliga as estrategias ao vivo mortas na arena. Devolve as novas."""
    dis = state.setdefault("disabled", {})
    new = []
    for b in summary.get("classificacao", []):
        k = b["id"]
        if b["estado"] == "MORTA" and k.replace("_SHORT", "") in LIVE_KILLABLE \
                and dis.get(k, {}).get("reason") != "arena":
            dis[k] = {"since": int(now), "reason": "arena",
                      "motivo": b.get("motivo")}
            new.append(k)
    return new


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
                        "name": f"{b['persona']} ({b['name']})", "estado": b["estado"],
                        "n": (b.get("morte") or {}).get("n", b["n"]),
                        "avg_r": (b.get("morte") or {}).get("avg_r", b["avg_r"]),
                        "motivo": b.get("motivo"), "strategy": b["id"],
                        "live": b["live"],
                        "real": False})
    return out
