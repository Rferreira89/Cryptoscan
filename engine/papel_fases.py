"""Papel ao vivo das estrategias por fase do mercado (31/10, OK do Rui: "Sim quero. Agora tem de haver uma
para subida tambem"). So papel: nao envia ordens. Dinheiro real so com prova e OK do Rui.

Fase do mercado (como no H29/H30, so com dias fechados do BTC): SUBIDA = fecho > SMA200 e SMA50 a subir
face a 10 dias antes; QUEDA = fecho < SMA200 e SMA50 a descer; LATERAL = o resto.

1) LATERAL — short no minimo de 55 velas (H29: +0,08R/+0,10R, acima do acaso nos dois periodos, abaixo
   de +0,15R): na fase LATERAL, vela de 4H fecha abaixo do minimo das 55 anteriores -> short ao fecho,
   stop 2 ATR(42) acima, objetivo 2R, saida em 18 velas; 0,25%/lado e juro 20%/ano.
2) SUBIDA — comprado em BTC, ETH e SOL (1/3 cada) enquanto a fase for SUBIDA (H30: +303%/+79% contra
   +83%/+42% sempre comprado, queda maxima 25-35% contra 64-85%; nao chegou a significancia estatistica).
   Entra quando a fase passa a SUBIDA e sai quando deixa de ser; 0,25% por entrada e por saida.
"""
H4, DAY = 14400, 86400
N_MIN, ATR_N, HOLD = 55, 42, 18
FEE, JURO = 0.0025, 0.20
TRIO = ("BTC", "ETH", "SOL")
NOMES = {1: "subida", 0: "lateral", -1: "queda"}


def fase(diario, now):
    """1 / 0 / -1 com os dias fechados do BTC, ou None sem historico suficiente."""
    d = [x for x in (diario or []) if x["t"] + DAY <= now]
    if len(d) < 211:
        return None
    c = [x["c"] for x in d]
    s200 = sum(c[-200:]) / 200
    s50, s50_10 = sum(c[-50:]) / 50, sum(c[-60:-10]) / 50
    if c[-1] > s200 and s50 > s50_10:
        return 1
    if c[-1] < s200 and s50 < s50_10:
        return -1
    return 0


def _st(state):
    return state.setdefault("papel_fases", {"desde": None, "lateral": {"abertas": {}, "fechadas": [], "ultimo": {}},
                                            "subida": {"pos": None, "fechadas": [], "fator": 1.0}, "avisos": []})


def _aviso(st, txt):
    st.setdefault("avisos", []).append(txt)
    del st["avisos"][:-20]


def pop_avisos(state):
    st = state.get("papel_fases") or {}
    out, st["avisos"] = list(st.get("avisos") or []), []
    return out


def _atr(c4):
    trs = [max(c4[i]["h"], c4[i - 1]["c"]) - min(c4[i]["l"], c4[i - 1]["c"]) for i in range(len(c4) - ATR_N, len(c4))]
    return sum(trs) / ATR_N


def _r_short(e, px, risco, horas):
    return round(((e - px) - FEE * (e + px) - JURO * horas / 24 / 365 * e) / risco, 3)


def lateral(st, c4s, fz, now):
    L = st.setdefault("lateral", {"abertas": {}, "fechadas": [], "ultimo": {}})
    ab, ult = L["abertas"], L.setdefault("ultimo", {})
    for a, c4 in (c4s or {}).items():
        if not c4 or len(c4) < max(N_MIN, ATR_N) + 2:
            continue
        op = ab.get(a)
        if op:
            for b in c4:
                if b["t"] <= op.get("visto", op["t"]):
                    continue
                op["visto"] = b["t"]
                horas = (b["t"] + H4 - op["t"]) / 3600
                fim = None
                if b["h"] >= op["stop"]:
                    fim = (op["stop"], "stop")
                elif b["l"] <= op["alvo"]:
                    fim = (op["alvo"], "objetivo")
                elif b["t"] >= op["t"] + (HOLD - 1) * H4:
                    fim = (b["c"], "tempo")
                if fim:
                    r = _r_short(op["entrada"], fim[0], op["risco"], horas)
                    L["fechadas"].append({"asset": a, "t": op["t"], "r": r, "motivo": fim[1], "t_fim": b["t"] + H4})
                    ab.pop(a)
                    rs = [x["r"] for x in L["fechadas"]]
                    _aviso(st, f"📝 Papel — short em mercado lateral em {a} fechado ({fim[1]}): {r:+.2f}R. "
                               f"Já vão {len(rs)} operações, média {sum(rs) / len(rs):+.2f}R.")
                    break
            continue
        b = c4[-1]
        if fz != 0 or b["t"] <= ult.get(a, 0):
            continue
        ult[a] = b["t"]
        minimo = min(x["l"] for x in c4[-N_MIN - 1:-1])
        if b["c"] < minimo:
            e = b["c"]
            stop = e + 2 * _atr(c4)
            ab[a] = {"t": b["t"] + H4, "visto": b["t"], "entrada": e, "stop": stop, "alvo": e - 2 * (stop - e),
                     "risco": stop - e}
            _aviso(st, f"📝 Papel — short em mercado lateral em {a} a {e:.6g} (quebrou o mínimo de 55 velas; "
                       f"stop {stop:.6g}, objetivo {e - 2 * (stop - e):.6g}). Só papel.")
    del L["fechadas"][:-500]


def subida(st, fz, precos, now):
    S = st.setdefault("subida", {"pos": None, "fechadas": [], "fator": 1.0})
    pos = S.get("pos")
    if fz == 1 and not pos and all(precos.get(a) for a in TRIO):
        S["pos"] = {"t": int(now), "precos": {a: precos[a] for a in TRIO}}
        _aviso(st, "📝 Papel — fase de SUBIDA: entra comprado em BTC, ETH e SOL (1/3 cada). Só papel.")
    elif pos and fz is not None and fz != 1 and all(precos.get(a) for a in TRIO):
        ret = sum(precos[a] / pos["precos"][a] - 1 for a in TRIO) / 3 - 2 * FEE
        S["fator"] = round(S.get("fator", 1.0) * (1 + ret), 4)
        S["fechadas"].append({"t": pos["t"], "t_fim": int(now), "ret_pct": round(100 * ret, 2)})
        S["pos"] = None
        _aviso(st, f"📝 Papel — a fase de SUBIDA acabou ({NOMES.get(fz)}): saída de BTC, ETH e SOL com "
                   f"{100 * ret:+.1f}%. Total desde o início: {100 * (S['fator'] - 1):+.1f}%.")


def update(state, c4s, diario_btc, precos, now):
    st = _st(state)
    st["desde"] = st.get("desde") or int(now)
    fz = fase(diario_btc, now)
    st["fase"] = fz
    lateral(st, c4s, fz, now)
    subida(st, fz, precos or {}, now)
    return resumo(st, precos)


def resumo(st, precos=None):
    L, S = st.get("lateral") or {}, st.get("subida") or {}
    rs = [x["r"] for x in L.get("fechadas") or []]
    pos = S.get("pos")
    aberto = None
    if pos and precos and all(precos.get(a) for a in TRIO):
        aberto = round(100 * (sum(precos[a] / pos["precos"][a] - 1 for a in TRIO) / 3), 2)
    return {"fase": NOMES.get(st.get("fase"), "sem dados"), "desde": st.get("desde"),
            "lateral": {"regra": "short no mínimo de 55 velas em mercado lateral (H29, só papel)", "n": len(rs),
                        "r_medio": round(sum(rs) / len(rs), 3) if rs else None,
                        "acerto_pct": round(100 * sum(1 for r in rs if r > 0) / len(rs)) if rs else None,
                        "abertas": sorted(L.get("abertas") or {}), "ultimas": (L.get("fechadas") or [])[-10:]},
            "subida": {"regra": "comprado em BTC, ETH e SOL na fase de subida (H30, só papel)",
                       "comprado": bool(pos), "aberto_pct": aberto, "total_pct": round(100 * (S.get("fator", 1.0) - 1), 1),
                       "ciclos": len(S.get("fechadas") or [])},
            "meta": "60 operações (lateral) ou 3 meses antes de qualquer proposta de dinheiro real"}
