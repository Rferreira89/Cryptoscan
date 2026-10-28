"""Promocao pela arena (decisao do Rui, 2026-10-13: "quero continuar com
operacoes e sinais em tempo real e com dinheiro real ... sempre as melhores
estrategias").

Um lutador QUALIFICA-SE quando, no combate de hora a hora (forma recente,
tools/arena_ringue.py), tem pelo menos MIN_N operacoes, R medio positivo e
acima do percentil 95 das entradas ao acaso, e nao esta morto. Os
qualificados com funcao de sinal (tools/arena_ringue.SINAIS) operam:
  - o CAMPEAO (o qualificado com melhor R medio) da sinais REAIS, pelo
    mesmo circuito das outras operacoes reais: alerta de compra com ordem
    pronta, botoes executei / nao executei, acompanhamento ao minuto,
    travoes de perda, limite de operacoes e registo;
  - os restantes ficam em papel ao vivo (engine/paper_ring.py).
So pode ser campeao um lutador da lista REAL_OK (codigo revisto).
Se o campeao morrer (no combate ou nas operacoes ao vivo, com as regras da
arena), perde o lugar logo e o seguinte qualificado assume. Sem
qualificados, nao ha sinais reais: nunca se volta a uma estrategia morta.
"""
from . import risk, venue

MIN_N = 20
TF = 14400
# Protecao contra quedas em cadeia (decisao do Rui, 2026-10-13): o Bounce
# compra quedas de mercado e os sinais chegam em grupo, em moedas que se
# mexem juntas. No maximo MAX_PER_BAR entradas novas por vela de 4H; o resto
# fica registado como oportunidade perdida.
MAX_PER_BAR = 2
# Lutadores cujo codigo de sinal foi revisto numa sessao com o Rui e que por
# isso podem ser campeoes com dinheiro real. Os lutadores novos criados pelos
# agentes entram no combate e em papel ao vivo sozinhos; para dinheiro real
# o codigo deles tem de ser revisto e acrescentado aqui (os agentes nao
# mexem em engine/).
class _RealOK(frozenset):
    """Lista de codigo revisto para dinheiro real. Um lutador que regressa
    com nome novo (TURTLE_R2) herda a revisao da familia de origem."""
    def __contains__(self, k):
        import re
        return frozenset.__contains__(self, k) or (
            isinstance(k, str) and frozenset.__contains__(self, re.sub(r"_R\d+$", "", k)))


# decisao do Rui (2026-10-14: "quero todas as estrategias e as melhores a
# funcionar"): todas as familias com funcao de sinal revista podem dar sinais
# reais, mas SO depois de se qualificarem no combate (20+ operacoes, R medio
# positivo e acima do percentil 95 do acaso). Quem nao prova, nao opera.
REAL_OK = _RealOK({"BOUNCE_G0", "BOUNCE_V2", "BOUNCE_V3", "BOUNCE_X30", "DIP_TREND",
                   "CAPITULACAO", "BOUNCE_FLUXO", "BOUNCE_FORTE", "BOUNCE_SQUEEZE",
                   "BOUNCE_ISOLADA", "BOUNCE_NOREACT", "BOUNCE_TRAIL", "BOUNCE_HORAS",
                   "BOUNCE_DESALAV", "BOUNCE_ABSORCAO", "BOUNCE_LSR", "BOUNCE_MACRO",
                   "BOUNCE_MEDO", "TURTLE", "SQUEEZE_BB", "MOMENTUM", "BRK_ESPACO", "RETESTE",
                   "BOUNCE_X30_PAVIO", "BOUNCE_X30_LIQ", "REVERSAO_INTERVALO", "VOLUME_ACUMULACAO", "FIBO_RECUO",
                   "SHORT_X30", "SHORT_FLUXO", "SHORT_TURTLE", "SHORT_SQUEEZE", "SHORT_ISOLADA",
                   # equipa das maiores (BTC, ETH, SOL), Rui 2026-10-18
                   "MAIORES_RECUO", "MAIORES_TENDENCIA", "MAIORES_FUNDING", "BOUNCE_AMPLITUDE",
                   "SHORT_MAIORES_RECUO", "SHORT_MAIORES_TENDENCIA"})


EU = None            # dados do servidor europeu (scanner.run preenche)
DAILY = {}           # velas diarias do scanner por moeda (scanner.run preenche)


def set_context(rows, bars):
    """Da as funcoes de sinal o BTC, o funding atual (Binance pelo servidor
    europeu, ou OKX) e o open interest da Binance de cada moeda."""
    try:
        from tools.arena_ringue import CTX
    except Exception:
        return
    CTX["btc"] = bars.get("BTC")
    CTX["daily"] = {a: c for a, c in (DAILY or {}).items() if c}
    CTX["bars"] = {a: c for a, c in bars.items() if c}    # rotacao: ranking ao vivo
    CTX["rank"] = {}
    # a taxa atual conta como a ultima liquidacao (ha menos de 4 horas)
    CTX["funding"] = {r["asset"]: [(int(__import__("time").time()) - 14000,
                                    (r.get("derivatives") or {}).get("funding_rate"))]
                      for r in rows if (r.get("derivatives") or {}).get("funding_rate") is not None}
    # open interest da Binance de 4 em 4 horas (servidor europeu)
    CTX["oi"] = {b: [tuple(x) for x in c.get("oi") or []]
                 for b, c in ((EU or {}).get("moedas") or {}).items()}
    CTX["ls"] = {b: [tuple(x) for x in c.get("ls") or []]
                 for b, c in ((EU or {}).get("moedas") or {}).items()}
    CTX["macro"] = {k: [tuple(x) for x in v]
                    for k, v in ((EU or {}).get("macro") or {}).items()}


def macro_summary(now):
    """Leitura macro atual para a pagina (None sem dados do servidor europeu)."""
    try:
        from tools import arena_ringue as AR
    except Exception:
        return None
    m = {k: [tuple(x) for x in v] for k, v in ((EU or {}).get("macro") or {}).items()}
    if not m:
        return None
    old, AR.CTX["macro"] = AR.CTX.get("macro"), m
    try:
        r = lambda x, n=2: None if x is None else round(x * 100, n)
        return {"estado": AR.macro_state(now), "vix": AR.macro_at("VIX", now),
                "sp_24h_pct": r(AR.macro_chg("SP", now, 86400)),
                "dxy_5d_pct": r(AR.macro_chg("DXY", now, 5 * 86400)),
                "us10y": AR.macro_at("US10Y", now)}
    finally:
        AR.CTX["macro"] = old


def registry():
    try:
        from tools.arena_ringue import SINAIS
        return SINAIS
    except Exception:                       # o motor nunca para por isto
        return {}


def qualified(state):
    """[(chave, R medio no combate)] dos qualificados, melhor primeiro."""
    ar = state.get("arena") or {}
    st, mortos = ar.get("status") or {}, ar.get("mortos") or {}
    out = []
    for k, f in ((ar.get("forma") or {}).get("lutadores") or {}).items():
        if k in mortos or st.get(k) == "MORTA" or not f:
            continue
        n, r, p95 = f.get("n") or 0, f.get("avg_r"), f.get("acaso_p95")
        if n >= MIN_N and r is not None and r > 0 and p95 is not None and r > p95:
            out.append((k, r, r_month(f)))
    # ordem pelo crescimento que da ao capital por mes (decisao do Rui,
    # 2026-10-15), nao so pelo ganho medio por operacao
    return [(k, r) for k, r, _ in sorted(out, key=lambda x: (-x[2], -x[1]))]


# ---------- contributo para a meta do milhao ----------
# O que leva ao milhao e o crescimento por mes: ganho medio x operacoes por
# mes. No combate de 90 dias o lutador opera em dezenas de moedas ao mesmo
# tempo; ao vivo as vagas, as familias e o limite por vela cortam isso, por
# isso conta no maximo LIVE_CAP operacoes por mes (estimativa prudente).
LIVE_CAP = 8


def r_month(f):
    n, r = f.get("n") or 0, f.get("avg_r") or 0
    return round(r * min(n / 3.0, LIVE_CAP), 2)


def growth(state, cfg):
    """[{id, persona, avg_r, ops_mes, r_mes, pct_mes, anos}] dos qualificados,
    do maior contributo para o menor. pct_mes usa o risco atual por operacao."""
    import math
    from . import arena
    cap = cfg.get("capital_usdc") or 0
    # max_risk_usdc ja vem dividido por dois quando o risco esta reduzido
    # (engine/scanner.py): nao dividir outra vez (contra-auditoria, 20/10)
    risk = (cfg.get("max_risk_usdc") or 0) / cap * 100 if cap else cfg.get("risk_pct", 1.0)
    lut = ((state.get("arena") or {}).get("forma") or {}).get("lutadores") or {}
    out = []
    for k, r in qualified(state):
        f = lut.get(k) or {}
        rm = r_month(f)
        pct = rm * risk
        anos = (math.log(1_000_000 / cap) / math.log(1 + pct / 100) / 12) if cap and pct > 0 else None
        out.append({"id": k, "persona": arena.persona(k), "avg_r": r,
                    "ops_mes": round(min((f.get("n") or 0) / 3.0, LIVE_CAP), 1),
                    "r_mes": rm, "pct_mes": round(pct, 1), "anos": round(anos, 1) if anos else None})
    return out


# ---------- diversificacao por familia (decisao do Rui, 2026-10-14) ----------
# "Nao quero todos os analistas numa estrategia so": as familias agrupam os
# lutadores que reagem ao mesmo fenomeno de mercado e por isso ganham e perdem
# juntos. No maximo MAX_PER_FAMILY operacoes reais abertas da mesma familia.
MAX_PER_FAMILY = 1     # Rui, 20/10: uma de cada familia (as copias contam uma vez)
FAMILIAS = {"maiores": "Equipa das maiores (BTC, ETH, SOL)", "sobrevenda": "Sobrevenda a virar", "tendencia": "Tendência e rompimento",
            "volatilidade": "Volatilidade", "volume": "Volume anormal (acumulação)", "capitulacao": "Capitulação", "short": "Venda a descoberto"}


def family(k):
    import re
    b = re.sub(r"_R\d+$", "", k or "")
    if b.startswith("SHORT_"):
        return "short"
    if b in ("DIP_TREND", "TURTLE", "TURTLE_FORTES", "MOMENTUM", "TREND_DAILY", "BREAKOUT", "PULLBACK",
             "BRK_ESPACO", "RETESTE", "FIBO_RECUO"):
        return "tendencia"
    if b in ("SQUEEZE_BB",):
        return "volatilidade"
    if b in ("VOLUME_ACUMULACAO",):
        return "volume"
    if b in ("CAPITULACAO",):
        return "capitulacao"
    if b.startswith("MAIORES_"):
        return "maiores"
    return "sobrevenda"


def family_open(state):
    """{familia: operacoes reais abertas} (registo)."""
    out = {}
    for r in state.get("ledger") or []:
        if r.get("mode") == "REAL" and r.get("status") in ("OPEN", "WAITING") \
                and r.get("executed") is not False and r.get("user_result_r") is None \
                and not r.get("fora_programa"):
            f = family(r.get("strategy"))
            out[f] = out.get(f, 0) + 1
    return out


# ---------- prova real dos campeoes ----------
# Um campeao que no dinheiro real fica muito abaixo do que o combate previa
# perde a vez (suspenso) ate o real voltar a acompanhar o combate.
LIVE_MIN_N = 8


def live_record(state, k):
    """(n, R medio) das operacoes reais fechadas do lutador k."""
    rs = [r.get("result_r") for r in state.get("ledger") or []
          if r.get("strategy") == k and r.get("status") == "CLOSED" and r.get("result_r") is not None]
    return len(rs), (sum(rs) / len(rs) if rs else None)


def suspended(state, contas_mes=True):
    """{lutador: motivo} dos campeoes suspensos pela prova real (e, com
    contas_mes, pelas contas do mes no combate de 90 dias)."""
    out = {}
    lut = (((state.get("arena") or {}).get("forma") or {}).get("lutadores")) or {}
    for k, f in lut.items():
        n, r = live_record(state, k)
        if n >= LIVE_MIN_N and r is not None and (r <= -0.5 or r <= (f.get("avg_r") or 0) - 1.0):
            out[k] = (f"no dinheiro real: {r:+.2f}R em {n} operações, contra "
                      f"{(f.get('avg_r') or 0):+.2f}R previstos no combate")
        # diretriz do Rui (2026-10-15): so tem lugar no escritorio quem e
        # lucrativo e leva a carteira ao objetivo. Com 10 operacoes reais e
        # resultado medio negativo, perde o lugar ate provar de novo.
        elif n >= LUCRO_MIN_N and r is not None and r < 0:
            out[k] = f"não é lucrativo no dinheiro real: {r:+.2f}R em {n} operações (diretriz do objetivo)"
        elif contas_mes:
            conta = contas(f)
            if conta:
                out[k] = conta
    return out


# Contas do mes (Rui, 2026-10-18: "tem que ganhar dinheiro para poder pagar as
# contas; se nao conseguirem pagar as contas morrem"). As contas sao os custos
# reais de operar: comissoes, deslize e o spread real da Bybit UE. Um lutador
# que nos ultimos 30 dias do combate, depois de pagar tudo, fica no negativo
# perde o lugar no dinheiro real ate voltar a pagar as contas. Se continuar
# sem pagar, a arena acaba por mata-lo (veredicto MORTA).
CONTAS_MIN_N = 5


def contas(f):
    """Motivo se o lutador nao pagou as contas do mes, senao None."""
    fora = ((f or {}).get("validacao") or {}).get("fora") or {}
    n, liq = fora.get("n") or 0, fora.get("avg_r_liq")
    if n >= CONTAS_MIN_N and liq is not None and liq <= 0:
        return (f"não pagou as contas do mês: {n} operações nos últimos 30 dias, "
                f"{liq * n:+.2f}R depois de comissões e spread real")
    return None


LUCRO_MIN_N = 10


def contribution(state):
    """{lutador: {n, r, usdc}}: o que cada um ja deu a carteira com dinheiro
    real (so operacoes executadas; usdc = R x risco em USDC da operacao)."""
    out = {}
    for x in state.get("ledger") or []:
        if x.get("status") != "CLOSED" or x.get("executed") is False or x.get("mode") != "REAL":
            continue
        r = x["user_result_r"] if x.get("user_result_r") is not None else x.get("result_r")
        if r is None:
            continue
        t = out.setdefault(x.get("strategy"), {"n": 0, "r": 0.0, "usdc": 0.0})
        t["n"] += 1
        t["r"] = round(t["r"] + r, 2)
        t["usdc"] = round(t["usdc"] + r * (x.get("risk_usdc") or 0), 2)
    return out


# Ganho minimo no combate para operar com dinheiro real (decisao do Rui,
# 2026-10-18, auditoria): abaixo disto o spread e o deslize reais da Bybit UE
# comem a vantagem (DIP_TREND +0,08R deu -2,65R em 10 sinais repetidos).
REAL_MIN_R = 0.15


def regime_qualified(state, fase):
    """[(chave, R medio)] dos lutadores que provaram ganhar NESTA fase do mercado
    no ringue de um ano: pelo menos MIN_N operacoes nessa fase, R medio de pelo
    menos REAL_MIN_R e acima de 95% do acaso, as duas metades do ano a ganhar,
    e as duas metades do ano a ganhar, separadamente, nesta fase."""
    if not fase:
        return []
    ar = state.get("arena") or {}
    longo = (ar.get("longo") or {}).get("lutadores") or {}
    cl = (ar.get("longo") or {}).get("clones") or {}
    out = []
    for k, v in longo.items():
        if k in cl:                            # clone de um lutador melhor (21/10): so conta o original
            continue
        f = (v.get("por_regime") or {}).get(fase) or {}
        n, r, p95, met = f.get("n") or 0, f.get("avg_r"), f.get("acaso_p95"), f.get("metades")
        if n < MIN_N or r is None or r < REAL_MIN_R or p95 is None or r <= p95:
            continue
        if not met or min(met) <= 0:
            continue
        if (state.get("troca_filtro") or {}).get("ativo") == "novo" and not f.get("passa_novo"):
            continue                           # (21/10) filtro novo ativo pela troca automatica (engine/troca.py)
        # (19/10) sem o teste dos ultimos 30 dias: esses 30 dias podem ser de
        # outra fase (shorts num mes de subida perdem, como devem); a prova
        # fora da amostra aqui sao as duas metades do ano, nesta fase
        out.append((k, r))
    return sorted(out, key=lambda x: -x[1])


CONFIG_ESTUDO = {}          # {fase: [lutadores]} de config "campeoes_estudo" (scanner preenche)
SO_PAPEL_FAM = set()        # familias que nunca usam dinheiro real (config "familias_so_papel")
# (28/10, auditoria, OK do Rui) dinheiro real so para estrategias autorizadas pelo Rui depois do
# criterio unico (dois periodos, correcao para testes multiplos, custos a dobrar, 3 meses em papel).
# None = regra desligada (testes antigos); o scanner preenche com config "real_autorizados".
AUTORIZADOS = None
SEM_AUTORIZACAO = "em papel até passar o critério de 28/10 e ter a autorização do Rui"
DERIVA_LIMITE, DERIVA_MIN = -0.15, 80
RECENTE_MIN = 40              # (27/10, OK do Rui) bloco mais recente do ringue nesta fase


def deriva(state, k, fase):
    """(23/10, OK do Rui) um campeao por estudo cuja segunda metade do ringue de um ano, nesta
    fase, fica abaixo de -0,15R com pelo menos 80 operacoes nessa metade, passa a papel: a
    vantagem trata-se como perdida ate voltar. Devolve o motivo ou None."""
    f = ((((state.get("arena") or {}).get("longo") or {}).get("lutadores") or {}).get(k) or {}).get("por_regime", {}).get(fase) or {}
    met, n = f.get("metades"), f.get("n") or 0
    if met and len(met) == 2 and met[1] is not None and n / 2 >= DERIVA_MIN and met[1] < DERIVA_LIMITE:
        return f"deriva: 2.ª metade do ano na fase {fase} em {met[1]:+.2f}R ({n // 2} op.), abaixo de {DERIVA_LIMITE:+.2f}R"
    # regra mais rapida (27/10, OK do Rui): as operacoes mais recentes desta fase (bloco reservado
    # do ringue de um ano) abaixo do mesmo limite tambem passam a papel. O Ramiro estava com a
    # 2.a metade em -0,01R mas as 65 mais recentes em -0,27R e o combate de 90 dias em -0,78R.
    rec = (f.get("qualidade") or {}).get("reservado") or {}
    if (rec.get("n") or 0) >= RECENTE_MIN and rec.get("avg_r") is not None and rec["avg_r"] < DERIVA_LIMITE:
        return (f"deriva recente: últimas {rec['n']} operações na fase {fase} em {rec['avg_r']:+.2f}R, "
                f"abaixo de {DERIVA_LIMITE:+.2f}R")
    return None


def champions(state, disabled=(), fase=None, por_fase=False):
    """Lutadores que dao sinais reais agora, melhor primeiro (decisao do
    Rui, 2026-10-13: "nao quero perder oportunidades"): TODOS os
    qualificados com codigo revisto e ganho medio de pelo menos REAL_MIN_R.
    Com por_fase, tambem os campeoes da fase atual do mercado no ringue de
    um ano (regime_qualified), mesmo que o combate de 90 dias os tenha
    eliminado por terem sido testados noutra fase (ex.: shorts em subida)."""
    reg = registry()
    if por_fase and fase:
        # prova dupla (Rui, 20/10): com a fase do mercado conhecida, so opera
        # com dinheiro real quem provou ganhar NESTA fase no ringue de um ano
        # (R >= REAL_MIN_R, acima do acaso, as duas metades a ganhar). O
        # combate de 90 dias sozinho deixava entrar 8 copias da sobrevenda
        # que na fase lateral ficam perto de zero.
        sus_real = suspended(state, contas_mes=False)
        out = [k for k, _ in regime_qualified(state, fase)
               if k in reg and k in REAL_OK and k not in disabled and k not in sus_real]
        papel = {}
        # (21/10, OK do Rui) aprovados pelo estudo de dois periodos (H10/H10b):
        # SHORT_TURTLE na lateral ganha em 2021-24 e 2024-26, ja com o juro do
        # emprestimo; a vantagem e a queda das altcoins, nao o momento, por isso
        # nao bate o acaso do ringue. Mesma suspensao pela prova real.
        for k in (CONFIG_ESTUDO.get(fase) or []):
            if k not in out and k in reg and k in REAL_OK and k not in disabled and k not in sus_real:
                d = deriva(state, k, fase)
                if d:
                    papel[k] = d
                    continue
                out.append(k)
        # (23/10, OK do Rui) familias so em papel (a sobrevenda perde por dia nos dois periodos
        # testados): saem do dinheiro real e passam a ser medidas em papel
        for k in list(out):
            if family(k) in SO_PAPEL_FAM:
                out.remove(k)
                papel[k] = f"família «{FAMILIAS.get(family(k), family(k))}» só em papel (decisão do Rui, 23/10)"
        if AUTORIZADOS is not None:
            for k in list(out):
                if k not in AUTORIZADOS:
                    out.remove(k)
                    papel[k] = SEM_AUTORIZACAO
        state["so_papel"] = papel
        return out
    sus = suspended(state)
    out = [(k, r) for k, r in qualified(state)
           if r >= REAL_MIN_R and k in reg and k in REAL_OK and k not in disabled and k not in sus]
    if por_fase:
        # as contas do mes vem do combate de 90 dias, que pode ser de outra
        # fase: aqui so contam as suspensoes pelo dinheiro real
        sus_real = suspended(state, contas_mes=False)
        have = {k for k, _ in out}
        out += [(k, r) for k, r in regime_qualified(state, fase)
                if k not in have and k in reg and k in REAL_OK and k not in disabled and k not in sus_real]
    return [k for k, _ in out if family(k) not in SO_PAPEL_FAM
            and (AUTORIZADOS is None or k in AUTORIZADOS)]


def champion(state, disabled=()):
    """O melhor dos campeoes (ou None)."""
    c = champions(state, disabled)
    return c[0] if c else None


def plan_for(sig, px, cfg):
    """Plano completo (dimensao, alavancagem, USDC) para o sinal do campeao.
    Tres objetivos e tres parciais, como as outras operacoes reais."""
    stop, tps = sig["stop"], list(sig["tp"])
    lo, hi = px * 0.997, px * 1.002
    entry = hi
    if not (0 < stop < lo) or tps[0] <= entry:
        return None, "plano inválido ao preço atual"
    fee = cfg["fee_pct"] / 100
    ru = entry - stop + fee * (entry + stop)
    stop_pct = ru / entry * 100
    sz, why = risk.sizing(stop_pct, (entry - stop) / entry, entry, cfg)
    if sz is None:
        return None, why
    split = sz["partials"]                     # o que a corretora deixa partir
    if len(tps) == 1:
        tp3, parts = [tps[0]] * 3, [100, 0, 0]
    else:
        tp3 = [tps[0], tps[1], tps[1]]
        parts = [50, 50, 0] if split[1] > 0 else [100, 0, 0]   # sem divisao: tudo no TP1
    net = lambda tp: (tp - entry - fee * (tp + entry)) / ru
    atr = sig.get("atr") or (entry - stop)
    return {"leverage": sz["leverage"], **sz["usdc"],
            "entry_zone": [lo, hi], "entry_ref": entry, "stop": stop,
            "tp": tp3, "tp_projected": [], "partials": parts,
            "rr": round(net(tp3[-1]), 2), "rr_tp1": round(net(tp3[0]), 2),
            "rr_tp3": round(net(tp3[-1]), 2), "stop_pct": round(stop_pct, 2),
            "stop_atr": round((entry - stop) / atr, 2) if atr else None,
            "position_pct": round(sz["size_pct"], 1),
            "risk_pct": round(sz["size_pct"] * stop_pct / 100, 2),
            "breakeven": bool(sig.get("breakeven", True)),
            "max_hold_s": sig.get("hold_s"), "no_react_s": sig.get("no_react_s"),
            "trail_r": sig.get("trail_r"), "risk_reduced": bool(cfg.get("risk_reduced"))}, None


def short_plan_for(sig, px, cfg):
    """Plano de venda a descoberto (margem spot) em precos reais: stop acima,
    objetivos abaixo. Mesmo dimensionamento das compras (risk.sizing)."""
    stop, tps = sig["stop"], list(sig["tp"])
    lo, hi = px * 0.998, px * 1.003
    entry = lo                                  # pior preco para quem vende
    if not (stop > hi and tps[0] < entry):
        return None, "plano de short inválido ao preço atual"
    fee = cfg["fee_pct"] / 100
    ru = stop - entry + fee * (entry + stop)
    stop_pct = ru / entry * 100
    sz, why = risk.sizing(stop_pct, (stop - entry) / entry, entry, cfg, short=True)
    if sz is None:
        return None, why
    if len(tps) == 1:
        tp3, parts = [tps[0]] * 3, [100, 0, 0]
    else:
        tp3 = [tps[0], tps[1], tps[1]]
        parts = [50, 50, 0] if sz["partials"][1] > 0 else [100, 0, 0]
    net = lambda tp: (entry - tp - fee * (tp + entry)) / ru
    return {"side": "SHORT", "leverage": sz["leverage"], **sz["usdc"],
            "entry_zone": [lo, hi], "entry_ref": entry, "stop": stop,
            "tp": tp3, "tp_projected": [], "partials": parts,
            "rr": round(net(tp3[-1]), 2), "rr_tp1": round(net(tp3[0]), 2),
            "rr_tp3": round(net(tp3[-1]), 2), "stop_pct": round(stop_pct, 2),
            "stop_atr": None, "position_pct": round(sz["size_pct"], 1),
            "risk_pct": round(sz["size_pct"] * stop_pct / 100, 2),
            "breakeven": True, "max_hold_s": sig.get("hold_s"),
            "no_react_s": sig.get("no_react_s"), "trail_r": sig.get("trail_r")}, None


def decisions(state, rows, bars, cfg, now, champs, market_ok, block_for):
    """{ativo: decisao LONG} para os sinais frescos dos campeoes (o melhor
    campeao com sinal ganha a moeda). Cada vela de sinal so e usada uma vez
    por moeda. block_for(ativo) -> motivo ou None. Os sinais bloqueados por
    evento ficam em state["promo_lost"]."""
    if isinstance(champs, str):
        champs = [champs]
    champs = [k for k in (champs or []) if registry().get(k)]
    if not market_ok:                         # BTC abaixo da SMA200: so vendas a descoberto
        champs = [k for k in champs if arena_base(k).startswith("SHORT_")]
    if not champs:
        return {}
    seen = state.setdefault("promo_last", {})
    bar = state.setdefault("promo_bar", {"t": 0, "n": 0})
    set_context(rows, bars)
    try:
        from tools.arena_ringue import CTX
    except Exception:
        CTX = {}
    cands = []                                # (posicao do campeao, ativo, sinal, decisao)
    for r in rows:
        a, c4 = r.get("asset"), bars.get(r.get("asset"))
        d0 = r.get("decision") or {}
        if not c4 or d0.get("decision") in ("LONG", "SHORT"):
            continue
        # auditoria 18/10: os sinais em moedas sem liquidez na Bybit UE e os
        # que nao dao plano eram descartados em silencio; agora ficam
        # registados em promo_lost (continuam a nao ser executados)
        illiquid = not d0.get("venue")
        CTX["asset"] = a
        falhou = None                          # (campeao, t_sig, motivo) do 1.o plano recusado
        for rank, champ in enumerate(champs):
            try:
                sig = registry()[champ](c4, r["price"], cfg)
            except Exception:
                continue
            if not sig or now - sig["t_sig"] > TF or seen.get(a) == sig["t_sig"]:
                continue
            if illiquid:
                seen[a] = sig["t_sig"]
                lost(state, now, a, champ, "liquidez: " + (d0.get("reason") or "sem par negociável na Bybit UE"))
                break
            why = block_for(a)
            if why:
                seen[a] = sig["t_sig"]
                lost(state, now, a, champ, f"evento: {why}")
                break
            if sig.get("side") == "SHORT":
                if not cfg.get("shorts"):
                    continue
                mg = (state.get("margem_bybit") or {}).get("moedas")
                if mg and a not in mg:            # (22/10) a Bybit UE nao empresta esta moeda
                    falhou = falhou or (champ, sig["t_sig"], "sem margem na Bybit UE: a moeda não se pode vender a descoberto")
                    continue
                p, why = short_plan_for(sig, r["price"], cfg)
            else:
                p, why = plan_for(sig, r["price"], cfg)
            if not p:
                falhou = falhou or (champ, sig["t_sig"], why)
                continue
            vw = venue.vol_ordem(d0.get("venue"), p.get("position_usdc"), cfg)
            if vw:
                seen[a] = sig["t_sig"]
                lost(state, now, a, champ, "liquidez: " + vw)
                falhou = None
                break
            cands.append((rank, a, champ, sig, p, d0))
            break
        else:
            if falhou:                         # nenhum campeao conseguiu plano nesta moeda
                seen[a] = falhou[1]
                lost(state, now, a, falhou[0], f"plano: {falhou[2]}")
    out, ok = {}, []
    fam = family_open(state)
    for rank, a, champ, sig, p, d0 in sorted(cands, key=lambda x: x[0]):
        seen[a] = sig["t_sig"]
        f = family(champ)
        if fam.get(f, 0) >= MAX_PER_FAMILY:
            lost(state, now, a, champ, f"diversificação: já há {fam[f]} operações da família "
                 f"«{FAMILIAS[f]}» abertas (máximo {MAX_PER_FAMILY})")
            continue
        if bar["t"] != sig["t_sig"]:
            bar.update(t=sig["t_sig"], n=0, fam={})
        if bar["n"] >= MAX_PER_BAR:
            lost(state, now, a, champ, f"limite de {MAX_PER_BAR} entradas por vela de 4H "
                 "(proteção contra quedas em cadeia)")
            continue
        bar["n"] += 1
        fam[f] = fam.get(f, 0) + 1
        ok.append((rank, a, champ, sig, p, d0))
    # Uma so aposta (decisao do Rui, 2026-10-15): sinais da mesma familia na
    # mesma vela de 4H reagem ao mesmo movimento e ganham ou perdem juntos
    # (14/10: SOL, XRP, AAVE e BONK no stop no mesmo quarto de hora). Dividem
    # o risco de UMA operacao: com 2 sinais, cada um leva metade.
    grp = {}
    for x in ok:
        grp.setdefault((family(x[2]), x[3]["t_sig"]), []).append(x)
    bf = bar.setdefault("fam", {})
    for (f, t), xs in grp.items():
        k = len(xs) + bf.get(f, 0)               # inclui as ja emitidas nesta vela
        bf[f] = bf.get(f, 0) + len(xs)
        if k <= 1:
            continue
        c2 = dict(cfg, risk_pct=cfg["risk_pct"] / k,
                  max_risk_usdc=cfg.get("max_risk_usdc", float("inf")) / k)
        if c2.get("fixed_position_usdc"):
            c2["fixed_position_usdc"] = cfg["fixed_position_usdc"] / k
        # metade pequena demais para vender parte no TP1 (16/10, ENA): fica so
        # o melhor sinal, inteiro (continua a ser uma so aposta) e os outros saem
        x0 = sorted(xs, key=lambda x: x[0])[0]
        sh0 = x0[4].get("side") == "SHORT"
        q0, _ = (short_plan_for if sh0 else plan_for)(x0[3], x0[4]["entry_ref"] / (0.998 if sh0 else 1.002), c2)
        if bf[f] - len(xs) == 0 and x0[4].get("partials", [0, 0])[1] > 0 and \
                (not q0 or q0.get("partials", [100, 0])[1] == 0):
            for y in xs:
                if y is not x0:
                    lost(state, now, y[1], y[2], "uma só aposta: ficou só o melhor sinal da família nesta "
                         "vela, inteiro, para poder proteger o lucro no TP1")
            x0[4]["cluster"] = {"n": k, "familia": FAMILIAS.get(f, f), "melhor": True}
            ok = [y for y in ok if (family(y[2]), y[3]["t_sig"]) != (f, t)] + [x0]
            continue
        for i, (rank, a, champ, sig, p, d0) in enumerate(xs):
            short = p.get("side") == "SHORT"
            p2, _ = (short_plan_for if short else plan_for)(sig, sig.get("px") or p["entry_ref"] /
                                                          (0.998 if short else 1.002), c2)
            if p2:
                p2["cluster"] = {"n": k, "familia": FAMILIAS.get(f, f)}
                xs[i] = (rank, a, champ, sig, p2, d0)
            else:                                # metade nao cabe na ordem minima: fica de fora
                lost(state, now, a, champ, "risco dividido com outro sinal da mesma família "
                     "nesta vela não cabe na ordem mínima")
                xs[i] = None
        xs = [x for x in xs if x]
        ok = [y for y in ok if (family(y[2]), y[3]["t_sig"]) != (f, t)] + xs
    for rank, a, champ, sig, p, d0 in sorted(ok, key=lambda x: x[0]):
        short = p.get("side") == "SHORT"
        out[a] = {
            "decision": "SHORT" if short else "LONG", "side": "SHORT" if short else "LONG",
            "mode": "REAL", "validated": False,
            "strategy": champ, "state": "READY", "plan": p, "score": 75 - rank,
            "score_label": "campeão da arena", "confidence": "MÉDIA",
            "regime": d0.get("regime"), "regime_changed": False,
            "conflicts": [], "warnings": [], "venue": d0["venue"],
            "families": {"combate de 90 dias acima do acaso": 1.0,
                         "gatilho do campeão": 0.8},
            "notes": [f"Campeão da arena ({champ}): no combate dos últimos "
                      "90 dias bateu 95% das entradas ao acaso"]
                     + (["Venda a descoberto em margem spot: pedes a moeda emprestada, vendes "
                         "e recompras mais barato. Perda limitada pelo stop acima; pagas juros "
                         "pela moeda emprestada."] if short else []),
            "trigger": sig.get("gatilho") or "gatilho do campeão",
            "reason": "campeão da arena", "checks": d0.get("checks", []),
            "rejected": []}
    return out


def arena_base(k):
    import re
    return re.sub(r"_R\d+$", "", k or "")


def lost(state, now, asset, champ, why):
    """Regista uma oportunidade de um campeao que nao virou sinal."""
    lst = state.setdefault("promo_lost", [])
    lst.append({"t": int(now), "asset": asset, "strategy": champ, "reason": why})
    del lst[:-100]


def filtro_novo(state):
    """Relatorio do filtro novo (modo relatorio, OK do Rui 21/10): por fase, quem
    o filtro atual aprova, quem o novo aprovaria, e quantos lutadores ao acaso
    passam cada um. Nao muda quem opera."""
    lg = ((state.get("arena") or {}).get("longo") or {})
    lut, cl = lg.get("lutadores") or {}, lg.get("clones") or {}
    out = {"acaso": lg.get("acaso_filtro") or {}, "clones": len(cl), "fases": {}, "hipoteses": lg.get("hipoteses") or {},
           "lista_clones": cl, "estudo": {f: list(v) for f, v in CONFIG_ESTUDO.items()}}
    for rg in ("subida", "lateral", "queda"):
        atual, novo, quase = [], [], []
        for k, v in lut.items():
            if k in cl:
                continue
            r = (v.get("por_regime") or {}).get(rg) or {}
            q = r.get("qualidade") or {}
            if r.get("passa_atual"):
                atual.append(k)
                (novo if r.get("passa_novo") else quase).append(
                    {"id": k, "dias": q.get("dias"), "ic_inf": q.get("ic_inf"),
                     "reservado": q.get("reservado"), "sem_melhor_moeda": q.get("sem_melhor_moeda")})
        out["fases"][rg] = {"atual": atual, "novo": [x["id"] for x in novo], "detalhe": novo + quase}
    return out
