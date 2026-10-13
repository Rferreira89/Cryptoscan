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
from . import risk

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
REAL_OK = ("BOUNCE_G0", "BOUNCE_V2", "BOUNCE_V3", "BOUNCE_X30", "DIP_TREND",
           "CAPITULACAO", "BOUNCE_FLUXO", "BOUNCE_FORTE", "BOUNCE_SQUEEZE",
           "BOUNCE_ISOLADA", "BOUNCE_NOREACT", "BOUNCE_TRAIL", "BOUNCE_HORAS")


EU = None            # dados do servidor europeu (scanner.run preenche)


def set_context(rows, bars):
    """Da as funcoes de sinal o BTC, o funding atual (Binance pelo servidor
    europeu, ou OKX) e o open interest da Binance de cada moeda."""
    try:
        from tools.arena_ringue import CTX
    except Exception:
        return
    CTX["btc"] = bars.get("BTC")
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
            out.append((k, r))
    return sorted(out, key=lambda x: -x[1])


def champions(state, disabled=()):
    """Lutadores que dao sinais reais agora, melhor primeiro (decisao do
    Rui, 2026-10-13: "nao quero perder oportunidades"): TODOS os
    qualificados com codigo revisto, nao so o primeiro."""
    reg = registry()
    return [k for k, _ in qualified(state)
            if k in reg and k in REAL_OK and k not in disabled]


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
        parts = [50, 50, 0] if split[0] > 0 else [0, 100, 0]
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


def decisions(state, rows, bars, cfg, now, champs, market_ok, block_for):
    """{ativo: decisao LONG} para os sinais frescos dos campeoes (o melhor
    campeao com sinal ganha a moeda). Cada vela de sinal so e usada uma vez
    por moeda. block_for(ativo) -> motivo ou None. Os sinais bloqueados por
    evento ficam em state["promo_lost"]."""
    if isinstance(champs, str):
        champs = [champs]
    champs = [k for k in (champs or []) if registry().get(k)]
    if not champs or not market_ok:
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
        if not c4 or not d0.get("venue") or d0.get("decision") in ("LONG", "SHORT"):
            continue
        CTX["asset"] = a
        for rank, champ in enumerate(champs):
            try:
                sig = registry()[champ](c4, r["price"], cfg)
            except Exception:
                continue
            if not sig or now - sig["t_sig"] > TF or seen.get(a) == sig["t_sig"]:
                continue
            why = block_for(a)
            if why:
                seen[a] = sig["t_sig"]
                lost(state, now, a, champ, f"evento: {why}")
                break
            p, why = plan_for(sig, r["price"], cfg)
            if not p:
                continue
            cands.append((rank, a, champ, sig, p, d0))
            break
    out = {}
    for rank, a, champ, sig, p, d0 in sorted(cands, key=lambda x: x[0]):
        seen[a] = sig["t_sig"]
        if bar["t"] != sig["t_sig"]:
            bar.update(t=sig["t_sig"], n=0)
        if bar["n"] >= MAX_PER_BAR:
            lost(state, now, a, champ, f"limite de {MAX_PER_BAR} entradas por vela de 4H "
                 "(proteção contra quedas em cadeia)")
            continue
        bar["n"] += 1
        out[a] = {
            "decision": "LONG", "mode": "REAL", "validated": False,
            "strategy": champ, "state": "READY", "plan": p, "score": 75 - rank,
            "score_label": "campeão da arena", "confidence": "MÉDIA",
            "regime": d0.get("regime"), "regime_changed": False,
            "conflicts": [], "warnings": [], "venue": d0["venue"],
            "families": {"combate de 90 dias acima do acaso": 1.0,
                         "gatilho do campeão": 0.8},
            "notes": [f"Campeão da arena ({champ}): no combate dos últimos "
                      "90 dias bateu 95% das entradas ao acaso"],
            "trigger": sig.get("gatilho") or "gatilho do campeão",
            "reason": "campeão da arena", "checks": d0.get("checks", []),
            "rejected": []}
    return out


def lost(state, now, asset, champ, why):
    """Regista uma oportunidade de um campeao que nao virou sinal."""
    lst = state.setdefault("promo_lost", [])
    lst.append({"t": int(now), "asset": asset, "strategy": champ, "reason": why})
    del lst[:-100]
