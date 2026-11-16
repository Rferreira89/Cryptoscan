"""Papel ao vivo automatico para os lutadores qualificados no combate
(decisao do Rui, 2026-10-13). Cada qualificado com funcao de sinal em
tools/arena_ringue.SINAIS que nao tenha papel proprio (o Bounce ja tem o
seu em engine/paper_bounce.py) passa a operar em papel aqui, sem mais
nenhuma intervencao. As operacoes fechadas entram na arena como operacoes
ao vivo desse lutador. Nunca gera ordens nem mensagens de compra.

(15/11, Rui): kill automatico se R medio < 0 com >= KILL_N operacoes;
avisos Telegram em abertura, fecho e retirada do papel.
(16/11): anti-repeticao Telegram por (tipo, estrategia, moeda, t_sig).
(16/11): SHORT_SOBRECOMPRA_X70V25 via tools.sig_short_sobrecompra.ensure().
Venue deste motor: Bybit (o OKX tem caminhos proprios).
"""
from . import promo, trade

TF = 14400
MAX_POS = 6
FEE_PCT, SLIP_PCT = 0.25, 0.1
OWN_PAPER = ("BOUNCE_G0", "BOUNCE_V1", "BOUNCE_V2", "BOUNCE_V3")
KILL_N = 20
VENUE = "Bybit"


def _tg(state, key, txt):
    sent = state.setdefault("papel_tg", {})
    if key in sent:
        return False
    try:
        from . import alerts
        if alerts.configured():
            alerts.send(txt)
        sent[key] = True
        if len(sent) > 500:
            for k in list(sent)[: len(sent) - 400]:
                del sent[k]
        return True
    except Exception:
        return False


def _r_medio(closed):
    rs = [c["r"] for c in closed if c.get("r") is not None]
    if not rs:
        return 0, None
    return len(rs), round(sum(rs) / len(rs), 3)


def update(state, rows, bars, now, market_ok=True):
    st = state.setdefault("paper_ring", {})
    killed = state.setdefault("papel_kill", {})
    # (16/11) SHORT_SOBRECOMPRA_X70V25 em papel
    extra_estudo, extra_fase, extra_nmin = (), {}, {}
    try:
        from tools import sig_short_sobrecompra as SS
        meta = SS.ensure()
        extra_estudo = (meta["name"],)
        extra_fase = {meta["name"]: meta["papel_fase"]}
        extra_nmin = {meta["name"]: meta["n_min"]}
    except Exception:
        pass
    reg = promo.registry()
    active = [k for k, _ in promo.qualified(state)
              if k in reg and k not in OWN_PAPER and k not in promo.REAL_OK]
    try:
        from tools.arena_ringue import PAPEL_ESTUDO, PAPEL_FASE
    except Exception:
        PAPEL_ESTUDO, PAPEL_FASE = (), {}
    PAPEL_ESTUDO = tuple(PAPEL_ESTUDO) + tuple(x for x in extra_estudo if x not in PAPEL_ESTUDO)
    PAPEL_FASE = dict(PAPEL_FASE, **extra_fase)
    try:
        from tools.arena_ringue import PAPEL_SEM_FILTRO_BTC
    except Exception:
        PAPEL_SEM_FILTRO_BTC = ()
    active += [k for k in PAPEL_ESTUDO if k in reg and k not in active and k not in promo.REAL_OK]
    active += [k for k in (state.get("so_papel") or {}) if k in reg and k not in active]
    active = [k for k in active if k not in killed]
    fase = (state.get("mercado") or {}).get("regime")
    for k in set(st) | set(active):
        b = st.setdefault(k, {"open": {}, "closed": [], "last": {}})
        for a in list(b["open"]):
            pos, c4 = b["open"][a], bars.get(a)
            if not c4:
                continue
            for x in c4:
                if x["t"] < pos["next_t"] or pos["closed"]:
                    continue
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
                pos["next_t"] = x["t"] + TF
            if pos["closed"]:
                rec = {
                    "asset": a, "opened_at": pos["opened_at"],
                    "closed_at": pos.get("closed_at") or now, "r": round(pos["r"], 3),
                    "reason": pos["exit_reason"], "entry": pos["entry"],
                    "stop": pos["stop0"], "tp": list(pos["tps"]),
                    "partials": list(pos["partials"]),
                    "breakeven": pos.get("breakeven", True), "fase": pos.get("fase"),
                    "side": pos.get("side", "LONG"), "venue": VENUE}
                b["closed"] = (b["closed"] + [rec])[-300:]
                del b["open"][a]
                lado = rec.get("side") or "LONG"
                t_key = rec.get("opened_at") or now
                _tg(state, f"FECHO|{k}|{a}|{t_key}",
                    f"[{VENUE}] PAPEL FECHO {k} {lado} {a} R={rec['r']:+.2f} "
                    f"motivo={rec.get('reason') or '?'} entrada={rec.get('entry')}")
        if k not in killed:
            n, rm = _r_medio(b["closed"])
            if n >= KILL_N and rm is not None and rm < 0:
                killed[k] = {"t": int(now), "n": n, "r": rm, "venue": VENUE,
                             "motivo": f"R medio {rm} em {n} op. de papel"}
                _tg(state, f"KILL|{k}|{n}|{rm}",
                    f"[{VENUE}] PAPEL KILL {k}: {n} op., R medio={rm}. Fora do papel. "
                    f"Nao reabre ate ordem manual.")
                if k in active:
                    active = [x for x in active if x != k]
                continue
        short_k = k.startswith("SHORT_")
        if k not in active or k in killed or (
                not market_ok and not short_k and k not in PAPEL_SEM_FILTRO_BTC):
            continue
        promo.set_context(rows, bars)
        try:
            from tools.arena_ringue import CTX
        except Exception:
            CTX = {}
        for r in rows:
            a, c4 = r.get("asset"), bars.get(r.get("asset"))
            CTX["asset"] = a
            if not c4 or a in b["open"] or len(b["open"]) >= MAX_POS:
                continue
            try:
                sig = reg[k](c4, r["price"], None)
            except Exception:
                continue
            if not sig or now - sig["t_sig"] > TF or b["last"].get(a) == sig["t_sig"]:
                continue
            b["last"][a] = sig["t_sig"]
            lado = "SHORT" if sig.get("side") == "SHORT" else "LONG"
            ok = (sig["tp"][0] < r["price"] < sig["stop"]) if lado == "SHORT" else (
                sig["stop"] < r["price"] < sig["tp"][0])
            if not ok:
                continue
            pos = trade.open_position(sig, r["price"], sig["t_sig"], FEE_PCT, SLIP_PCT,
                                      breakeven=sig.get("breakeven", True), side=lado)
            pos["next_t"] = c4[-1]["t"] + TF
            pos["fase"] = fase
            pos["side"] = lado
            pos["venue"] = VENUE
            if sig.get("hold_s"):
                pos["max_hold"] = sig["hold_s"]
            b["open"][a] = pos
            _tg(state, f"ABRE|{k}|{a}|{sig['t_sig']}",
                f"[{VENUE}] PAPEL ABRE {k} {lado} {a} @ {r['price']} "
                f"stop={sig.get('stop')} tp={sig.get('tp')}")
    out = {k: {"n": len(v["closed"]), "open": sorted(v["open"])} for k, v in st.items()}
    try:
        from tools.arena_ringue import PAPEL_N_MIN
    except Exception:
        PAPEL_N_MIN = {}
    PAPEL_N_MIN = dict(PAPEL_N_MIN, **extra_nmin)
    for k in PAPEL_ESTUDO:
        if k in out:
            out[k]["prova"] = prova_estudo(
                st[k]["closed"], PAPEL_FASE.get(k, "subida"),
                n_min=PAPEL_N_MIN.get(k, 20))
            if k in killed:
                out[k]["prova"]["estado"] = "chumbado"
                out[k]["kill"] = killed[k]
    return out


def prova_estudo(closed, fase="subida", n_min=20, r_min=0.15):
    rs = [c["r"] for c in closed if (fase is None or c.get("fase") == fase) and c.get("r") is not None]
    n = len(rs)
    r = round(sum(rs) / n, 3) if n else None
    h = n // 2
    met = [round(sum(rs[:h]) / h, 3), round(sum(rs[h:]) / (n - h), 3)] if h else None
    if n < n_min:
        estado = "a medir"
    elif r >= r_min and met and min(met) > 0:
        estado = "aprovado: pede o OK do Rui"
    elif r is not None and r < 0:
        estado = "chumbado"
    else:
        estado = "a medir"
    return {"fase": fase, "n": n, "n_min": n_min, "r": r, "metades": met, "estado": estado}
