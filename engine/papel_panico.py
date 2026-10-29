"""Papel ao vivo da "compra no panico com ordem limite" (H23, 29/10; OK do Rui: "so em papel").

Regra exatamente como no estudo (backtest/estudos/h23_ordens_limite.py, variante L10):
  sinal (fecho de vela de 4H): o ultimo financiamento ja pago e negativo e esta no percentil 5 ou abaixo
  dos 270 anteriores (~90 dias), e a moeda caiu 10% ou mais em 3 dias (18 velas).
  ordem limite 1% abaixo do fecho do sinal, valida 2 velas (8 h); sem execucao, nao ha operacao.
  stop 2 ATR (media de 42 velas), objetivo 2R, saida ao fim de 18 velas.
  custos: 0,10% na entrada e no objetivo (ordem limite), 0,25% no stop e na saida por tempo.
No historico de 2024-26 deu +0,08R por operacao nas duas metades (acima do acaso, p=0,000), mas nao
passou o criterio de +0,15R. Por isso: SO PAPEL. Nao envia ordens nem mensagens. Dinheiro real so com
o criterio unico de 28/10 cumprido e autorizacao do Rui.
"""
H4 = 14400
OFFSET, VALIDA, HOLD, ATR_N = 0.01, 2, 18, 42
F_LIM, F_MKT = 0.0010, 0.0025


def _pct5(hist):
    s = sorted(hist)
    k = 0.05 * (len(s) - 1)
    i = int(k)
    return s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (k - i)     # como numpy.percentile (linear)


def sinal(c4, funding):
    """Plano pendente para a ultima vela fechada, ou None. funding: [(t_s, taxa)] por ordem."""
    if not c4 or len(c4) < max(ATR_N, 19) + 1 or not funding:
        return None
    b = c4[-1]
    conhecidos = [f for f in funding if f[0] <= b["t"] + H4]
    if len(conhecidos) < 271:
        return None
    fv = conhecidos[-1][1]
    if fv is None or fv >= 0 or fv > _pct5([f[1] for f in conhecidos[-271:-1]]):
        return None
    if b["c"] / c4[-19]["c"] - 1 > -0.10:
        return None
    trs = [max(c4[i]["h"], c4[i - 1]["c"]) - min(c4[i]["l"], c4[i - 1]["c"]) for i in range(len(c4) - ATR_N, len(c4))]
    return {"t_sig": b["t"], "lim": b["c"] * (1 - OFFSET), "atr": sum(trs) / ATR_N, "funding": fv,
            "queda_3d_pct": round((b["c"] / c4[-19]["c"] - 1) * 100, 1)}


def _r(e, px, risk, fout):
    return round(((px - e) - (F_LIM * e + fout * px)) / risk, 3)


def _seguir(op, barras):
    """Avanca uma operacao aberta pelas velas novas. Devolve (R, motivo) quando fecha."""
    for b in barras:
        if b["t"] <= op.get("visto", 0):
            continue
        op["visto"] = b["t"]
        primeira = b["t"] == op["t_fill"]
        if b["l"] <= op["stop"] and (not primeira or b["o"] > op["stop"]):
            return _r(op["entrada"], op["stop"], op["risco"], F_MKT), "stop"
        if b["h"] >= op["alvo"]:
            return _r(op["entrada"], op["alvo"], op["risco"], F_LIM), "objetivo"
        if b["t"] >= op["t_fill"] + (HOLD - 1) * H4:
            return _r(op["entrada"], b["c"], op["risco"], F_MKT), "tempo"
    return None


def update(state, c4s, eu, now):
    st = state.setdefault("papel_panico", {"pend": {}, "abertas": {}, "fechadas": [], "perdidas": 0, "desde": int(now)})
    pend, ab = st["pend"], st["abertas"]
    for a, c4 in (c4s or {}).items():
        if not c4:
            continue
        # ordem pendente: executa se o minimo tocar no limite nas 2 velas seguintes
        p = pend.get(a)
        if p:
            for b in c4:
                if p["t_sig"] < b["t"] <= p["t_sig"] + VALIDA * H4 and b["l"] <= p["lim"]:
                    e = min(p["lim"], b["o"])
                    stop = e - 2 * p["atr"]
                    if e - stop > 0:
                        ab[a] = {"entrada": e, "stop": stop, "alvo": e + 2 * (e - stop), "risco": e - stop,
                                 "t_sig": p["t_sig"], "t_fill": b["t"], "funding": p["funding"],
                                 "queda_3d_pct": p["queda_3d_pct"]}
                    pend.pop(a)
                    break
            else:
                if c4[-1]["t"] >= p["t_sig"] + VALIDA * H4:
                    pend.pop(a)
                    st["perdidas"] = st.get("perdidas", 0) + 1
        op = ab.get(a)
        if op:
            fim = _seguir(op, [b for b in c4 if b["t"] >= op["t_fill"]])
            if fim:
                st["fechadas"].append({"asset": a, "t_sig": op["t_sig"], "t_fill": op["t_fill"], "entrada": op["entrada"],
                                       "r": fim[0], "motivo": fim[1], "t_fim": op.get("visto")})
                ab.pop(a)
        if a not in pend and a not in ab and c4[-1]["t"] > st.setdefault("ultimo", {}).get(a, 0):
            s = sinal(c4, ((eu or {}).get("moedas") or {}).get(a, {}).get("funding"))
            if s:
                pend[a] = s
                st["ultimo"][a] = s["t_sig"]
    del st["fechadas"][:-500]
    return resumo(st)


def resumo(st):
    fc = (st or {}).get("fechadas") or []
    rs = [x["r"] for x in fc]
    return {"regra": "compra no pânico com ordem limite 1% abaixo (H23, só papel)", "desde": (st or {}).get("desde"),
            "n": len(rs), "r_medio": round(sum(rs) / len(rs), 3) if rs else None,
            "acerto_pct": round(100 * sum(1 for r in rs if r > 0) / len(rs)) if rs else None,
            "abertas": sorted((st or {}).get("abertas") or {}), "pendentes": sorted((st or {}).get("pend") or {}),
            "ordens_nao_executadas": (st or {}).get("perdidas", 0), "ultimas": fc[-10:],
            "meta": "60 operações ou 3 meses com média positiva antes de qualquer proposta de dinheiro real"}
