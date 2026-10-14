"""Mesa redonda: cada lutador vivo diz se a sua regra entrava numa moeda
agora e porque. Tudo vem das mesmas funcoes de sinal que o combate e o
motor ao vivo usam (tools/arena_ringue.py, SINAIS): o voto "entra" so
aparece quando a funcao de sinal devolve mesmo um plano. As razoes sao a
leitura dos mesmos dados (RSI de 4H, compradores agressivos, funding, OI,
BTC, macro), em linguagem simples.
"""
import time

H4, DAY = 14400, 86400


def _base(c4, lim):
    """(ok, texto) da condicao comum: RSI de 4H abaixo de lim nas ultimas 3
    velas e a virar, com fecho acima do maximo anterior."""
    from tools import arena_ringue as AR
    c, rs, _, _ = AR._ind(c4[-300:])
    k = len(c) - 1
    if k < 3 or rs[k] is None or rs[k - 2] is None:
        return False, "sem velas suficientes"
    low = min(rs[k - 2:k + 1])
    turn = c[k] > c4[-2]["h"] and rs[k] > rs[k - 1]
    if low >= lim:
        return False, f"RSI 4H a {rs[k]:.0f}: sem sobrevenda (preciso abaixo de {lim})"
    if not turn:
        return False, f"RSI 4H a {rs[k]:.0f}, em sobrevenda mas ainda sem virar"
    return True, f"RSI 4H esteve a {low:.0f} e virou"


def _base_short(c4):
    """(ok, texto) da condicao comum dos shorts em precos reais: RSI de 4H
    acima de 70 nas ultimas 3 velas e a virar para baixo."""
    from tools import arena_ringue as AR
    c, rs, _, _ = AR._ind(c4[-300:])
    k = len(c) - 1
    if k < 3 or rs[k] is None or rs[k - 2] is None:
        return False, "sem velas suficientes"
    hi = max(rs[k - 2:k + 1])
    turn = c[k] < c4[-2]["l"] and rs[k] < rs[k - 1]
    if hi <= 70:
        return False, f"RSI 4H a {rs[k]:.0f}: sem sobrecompra (preciso acima de 70)"
    if not turn:
        return False, f"RSI 4H a {rs[k]:.0f}, em sobrecompra mas ainda sem virar para baixo"
    return True, f"RSI 4H esteve a {hi:.0f} e virou para baixo"


def _filter(k, c4):
    """(ok, texto) do filtro proprio de cada lutador (None se nao tem)."""
    from tools import arena_ringue as AR
    t = c4[-1]["t"] + H4
    b = c4[-1]
    if k == "BOUNCE_FLUXO":
        sh = (b.get("tb") or 0) / b["v"] if b.get("v") else None
        return (sh is not None and sh >= .55,
                "compradores agressivos " + ("–" if sh is None else f"{sh:.0%} (preciso de 55%)"))
    if k == "BOUNCE_FORTE":
        if len(c4) < 181:
            return False, "sem 30 dias de histórico"
        mine = c4[-1]["c"] / c4[-181]["c"] - 1
        btc = AR._btc_ret(t, 180)
        return (btc is not None and mine > btc,
                f"30 dias: moeda {mine:+.0%} vs BTC {'–' if btc is None else f'{btc:+.0%}'}")
    if k == "BOUNCE_SQUEEZE":
        fr = (AR.CTX.get("funding") or {}).get(AR.CTX.get("asset")) or []
        v = fr[-1][1] if fr else None
        return (v is not None and v < 0,
                "funding " + ("–" if v is None else f"{v * 100:.4f}%") + " (preciso negativo)")
    if k == "BOUNCE_ISOLADA":
        btc = AR._btc_ret(t, 6)
        return (btc is not None and btc >= -0.02,
                "BTC 24h " + ("–" if btc is None else f"{btc:+.1%}") + " (preciso ≥ −2%)")
    if k == "BOUNCE_DESALAV":
        oi = (AR.CTX.get("oi") or {}).get(AR.CTX.get("asset")) or []
        if len(oi) < 7 or not oi[-7][1]:
            return False, "sem posições abertas da Binance"
        ch = oi[-1][1] / oi[-7][1] - 1
        return ch <= AR.OI_DROP, f"posições abertas {ch:+.0%} em 24h (preciso ≤ −5%)"
    if k in ("BOUNCE_MACRO", "BOUNCE_MEDO"):
        st = AR.macro_state(t)
        want = "favoravel" if k == "BOUNCE_MACRO" else "medo"
        nome = {"favoravel": "favorável", "neutro": "neutra", "medo": "medo"}.get(st, "sem dados")
        return st == want, f"macro {nome} (preciso {'favorável' if want == 'favoravel' else 'medo'})"
    if k == "BOUNCE_HORAS":
        g = time.gmtime(t)
        ok = g.tm_wday < 5 and g.tm_hour >= 6
        return ok, "hora líquida" if ok else "fim de semana ou madrugada UTC"
    if k == "BOUNCE_ABSORCAO":
        return AR.absorcao(c4)
    if k == "BOUNCE_LSR":
        return AR.lsr_ok(AR.CTX.get("asset"), t)
    return None


def _why_turtle(c4):
    from engine import backtest as B
    d = [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]
    if len(d) < 22:
        return "sem 20 dias de histórico"
    hi = max(x["h"] for x in d[-21:-1])
    gap = (hi / c4[-1]["c"] - 1) * 100
    return (f"máximo de 20 dias em {hi:.6g}: " + (f"faltam {gap:.1f}% para o rompimento" if gap > 0
                                                 else "já acima, à espera de um rompimento novo"))


def _why_squeeze(c4):
    c = [x["c"] for x in c4[-140:]]
    if len(c) < 140:
        return "sem velas suficientes"

    def w(k):
        x = c[k - 19:k + 1]
        m = sum(x) / 20
        return 4 * (sum((v - m) ** 2 for v in x) / 20) ** 0.5 / m
    ws = sorted(w(k) for k in range(len(c) - 121, len(c) - 1))
    p = 100 * sum(1 for v in ws if v < w(len(c) - 1)) / len(ws)
    return f"largura das bandas no percentil {p:.0f} de 20 dias (preciso de aperto ≤ 10 e rompimento com volume)"


def _why_momentum(c4):
    from tools import arena_ringue as AR
    t = c4[-1]["t"] + H4
    rank = AR.momentum_rank(AR.CTX.get("bars") or {}, t)
    a = AR.CTX.get("asset")
    pos = rank.index(a) + 1 if a in rank else None
    return (f"{pos}.ª de {len(rank)} em força a 30 dias" if pos else "sem 30 dias de histórico") + \
        f" (compra as {AR.MOM_TOP} primeiras, só à segunda-feira 00h UTC)"


TREND = {"TURTLE": _why_turtle, "SQUEEZE_BB": _why_squeeze, "MOMENTUM": _why_momentum}


BASE = {"BOUNCE_G0": 25, "BOUNCE_V2": 25, "BOUNCE_V3": 25, "DIP_TREND": 35}


def votes(asset, c4, px, alive):
    """[{id, persona, voto, razao}] dos lutadores vivos (alive: ids)."""
    from tools import arena_ringue as AR
    from . import arena
    AR.CTX["asset"] = asset
    out = []
    for k in sorted(alive):
        fn = AR.SINAIS.get(k)
        if not fn:
            continue
        kb = arena.base_key(k)                 # regressos usam as regras da familia
        try:
            sig = fn(c4, px)
        except Exception:
            sig = None
        if kb.startswith("SHORT_"):
            ok_b, why = _base_short(c4)
            f = None
            if kb == "SHORT_TURTLE":
                from engine import backtest as B
                d = [x for x in B.daily(c4) if x["t"] + DAY <= c4[-1]["t"] + H4]
                lo = min(x["l"] for x in d[-21:-1]) if len(d) > 21 else None
                why, ok_b = ((f"mínimo de 20 dias em {lo:.6g}: faltam "
                              f"{(c4[-1]['c'] / lo - 1) * 100:.1f}% para a quebra") if lo else
                             "sem 20 dias de histórico"), False
            elif kb == "SHORT_SQUEEZE":
                fr = (AR.CTX.get("funding") or {}).get(asset) or []
                v = fr[-1][1] if fr else None
                f = (v is not None and v >= 0.0002,
                     "funding " + ("–" if v is None else f"{v * 100:.4f}%") + " (preciso ≥ 0,02%)")
            elif kb == "SHORT_ISOLADA":
                b = AR._btc_ret(c4[-1]["t"] + H4, 6)
                f = (b is not None and b <= 0.02, "BTC 24h " + ("–" if b is None else f"{b:+.1%}") + " (preciso ≤ +2%)")
            elif kb == "SHORT_FLUXO":
                x = c4[-1]
                sh = 1 - (x.get("tb") or 0) / x["v"] if x.get("v") and x.get("tb") is not None else None
                f = (sh is not None and sh >= .55, "vendedores agressivos " + ("–" if sh is None else f"{sh:.0%}") + " (preciso de 55%)")
            if f is not None and ok_b:
                why = f"{why}; {f[1]}"
        elif kb in TREND:
            why, ok_b, f = TREND[kb](c4), False, None
        elif kb == "CAPITULACAO":
            v = c4[-1]["v"] / max(1e-12, sum(x["v"] for x in c4[-21:-1]) / 20)
            why = f"volume {v:.1f}× o normal (preciso de 3× com pavio longo)"
        else:
            ok_b, why = _base(c4, BASE.get(kb, 30))
            f = _filter(kb, c4)
            if f is not None and ok_b:
                why = f"{why}; {f[1]}"
            elif f is not None and not ok_b and f[0]:
                why = f"{why} ({f[1]}: ok)"
        if sig:
            why = sig.get("gatilho") or why
        elif not kb.startswith("SHORT_") and kb not in TREND and kb != "CAPITULACAO" and ok_b and (f is None or f[0]):
            why += ("; a tendência diária não é forte o suficiente" if kb == "DIP_TREND"
                    else "; o plano não tem margem até ao objetivo")
        out.append({"id": k, "persona": arena.persona(k),
                    "voto": ("vende" if kb.startswith("SHORT_") else "entra") if sig else "não",
                    "razao": why})
    out.sort(key=lambda x: (x["voto"] == "não", x["persona"]))
    return out


def table(rows, c4s, state, limit=None):
    """Mesa redonda para as moedas: guarda em cada linha row['debate'] e
    devolve as mais quentes (mais votos a favor, depois RSI mais baixo)."""
    ar = state.get("arena") or {}
    mortos = set((ar.get("mortos") or {}).keys())
    st = ar.get("status") or {}
    alive = {k for k in ((ar.get("forma") or {}).get("lutadores") or {})
             if k not in mortos and st.get(k) != "MORTA"}
    hot = []
    for r in rows:
        c4 = c4s.get(r["asset"])
        if not c4 or len(c4) < 60:
            continue
        try:
            v = votes(r["asset"], c4, r["price"], alive)
        except Exception:
            continue
        r["debate"] = v
        yes = sum(1 for x in v if x["voto"] != "não")
        rsi = ((r.get("analysis") or {}).get("4h") or {}).get("rsi") or 99
        hot.append((-yes, rsi, r["asset"], yes, len(v)))
    hot.sort()
    return [{"asset": a, "a_favor": y, "votantes": n, "rsi": round(rsi, 1)}
            for _, rsi, a, y, n in hot[:limit or 6]]
