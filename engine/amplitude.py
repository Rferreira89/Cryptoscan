"""Amplitude do mercado (Rui, 2026-10-18: "a analise ao mercado no seu todo
esta a ser bem feita?"). A fase do mercado era medida so pelo BTC; uma queda
geral das altcoins com o BTC parado nao aparecia. Este medidor olha para
todas as moedas analisadas: quantas caem forte, o RSI de 4H mediano e
quantas estao em sobrevenda. So informa (painel, Diretor, investigacao):
nao decide entradas.
"""
HIST_MAX = 7 * 24 * 12          # ~7 dias de scans de 5 minutos (amostra de hora a hora abaixo)


def _med(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def medir(rows):
    """{n, queda_forte_pct, chg_mediana, rsi_mediano, sobrevenda_pct, sobrecompra_pct, btc_chg, estado}."""
    chg, rsi, btc = [], [], None
    for r in rows or []:
        a4 = ((r.get("analysis") or {}).get("4h") or {})
        if r.get("chg_24h") is not None:
            chg.append(r["chg_24h"])
            if r.get("asset") == "BTC":
                btc = r["chg_24h"]
        if a4.get("ok") and a4.get("rsi") is not None:
            rsi.append(a4["rsi"])
    if len(rsi) < 10:
        return None
    n = len(rsi)
    out = {"n": n,
           "queda_forte_pct": round(100 * sum(1 for x in chg if x <= -5) / max(1, len(chg)), 1),
           "chg_mediana": round(_med(chg), 2) if chg else None,
           "rsi_mediano": round(_med(rsi), 1),
           "sobrevenda_pct": round(100 * sum(1 for x in rsi if x < 30) / n, 1),
           "sobrecompra_pct": round(100 * sum(1 for x in rsi if x > 70) / n, 1),
           "btc_chg": None if btc is None else round(btc, 2)}
    out["estado"] = estado(out)
    return out


def estado(m):
    if m["sobrevenda_pct"] >= 25 or (m["queda_forte_pct"] >= 40 and m["rsi_mediano"] < 40):
        return "capitulação geral"
    if (m["chg_mediana"] or 0) <= -4 and (m["btc_chg"] is None or m["btc_chg"] > -2):
        return "queda das altcoins com o BTC parado"
    if (m["chg_mediana"] or 0) <= -4:
        return "queda geral"
    if m["sobrecompra_pct"] >= 25:
        return "euforia"
    return "normal"


def atualizar(state, rows, now):
    """Mede, guarda uma amostra por hora (7 dias) e diz se o estado mudou."""
    m = medir(rows)
    if not m:
        return None
    st = state.setdefault("amplitude", {"hist": []})
    h = st.setdefault("hist", [])
    if not h or now - h[-1][0] >= 3600:
        h.append([int(now), m["rsi_mediano"], m["sobrevenda_pct"], m["queda_forte_pct"]])
        del h[:-7 * 24]
    antes = st.get("estado")
    st["estado"] = m["estado"]
    m["mudou"] = antes is not None and antes != m["estado"]
    m["hist"] = h[-48:]
    # (24/10, Rui: avisos repetidos) o estado oscilava entre "queda das altcoins" e "capitulacao
    # geral" a cada 5 minutos (perto dos 40%). Agora so avisa quando entra num grupo novo
    # (queda -> normal -> queda), quando o estado novo se mantem 30 minutos, e no maximo 1 vez em 12 horas.
    if "grupo_pendente" not in st and antes in QUEDA:              # so na passagem do sistema antigo
        st["grupo_avisado"], st["avisado_t"] = "queda", int(now)   # ja avisado pelo sistema antigo
    grupo = "queda" if m["estado"] in QUEDA else m["estado"]
    if grupo != st.get("grupo_pendente"):
        st["grupo_pendente"], st["desde_pendente"] = grupo, int(now)
    m["avisar"] = (grupo == "queda" and st.get("grupo_avisado") != "queda"
                   and now - st.get("desde_pendente", now) >= ESTAVEL_S
                   and (st.get("avisado_t") is None or now - st["avisado_t"] >= MIN_ENTRE_S))
    if m["avisar"]:
        st["grupo_avisado"], st["avisado_t"] = grupo, int(now)
    elif grupo != "queda" and now - st.get("desde_pendente", now) >= ESTAVEL_S:
        st["grupo_avisado"] = grupo           # o mercado normalizou: a proxima queda volta a avisar
    return m


QUEDA = ("capitulação geral", "queda das altcoins com o BTC parado", "queda geral")
ESTAVEL_S, MIN_ENTRE_S = 30 * 60, 12 * 3600


def aviso(m):
    if not m or not m.get("avisar"):
        return None
    return (f"🌊 Amplitude do mercado: <b>{m['estado']}</b>. {m['queda_forte_pct']:.0f}% das moedas a cair 5% ou mais "
            f"em 24h (mediana {m['chg_mediana']:+.1f}%, BTC {m['btc_chg']:+.1f}%), RSI 4H mediano {m['rsi_mediano']:.0f}. "
            "É o terreno do Ramiro: shorts nas moedas que quebram o mínimo de 20 dias (um de cada vez). "
            "Não volto a avisar enquanto a queda durar.")
