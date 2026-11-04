"""(04/11) H46 em papel ao vivo na OKX: recuo curto numa altcoin em tendencia de subida com o mercado a subir.
Rui: "temos de ter trades todas as semanas". No teste (backtest/estudos/h46_resultado.txt) a variante RSI<30 ficou
positiva nas duas metades mas por pouco (+0,048R e +0,147R; conta x1,03 e x1,43; sem as moedas retiradas): por isso
papel E, desde 04/11 com o OK do Rui ("Sim, real a 1% de risco"), dinheiro real na OKX com metade do risco (1%),
okx_config.json "recuo_real". A calibracao (metricas) mede se a vantagem se confirma.
Regra (igual ao teste; media de 50 dias diaria em vez da de 300 velas de 4H, a mesma janela):
  BTC: fecho diario acima da media de 50 dias e essa media a subir face a 10 dias antes;
  moeda: o mesmo, e RSI(14) de 4H abaixo de 30 na ultima vela fechada;
  compra limite 1% abaixo do fecho (2 velas), stop 2xATR42, objetivo 2R, saida as 72 h, custos de futuros."""
import time

import okx_agente as A
from engine import papel_panico as P

L_RSI, N_MEDIA, SUBIDA = 30, 50, 10


def rsi(c, n=14):
    if len(c) < n + 2:
        return None
    up = [max(0.0, c[i] - c[i - 1]) for i in range(1, len(c))]
    dn = [max(0.0, c[i - 1] - c[i]) for i in range(1, len(c))]
    au, ad = sum(up[:n]) / n, sum(dn[:n]) / n
    for i in range(n, len(up)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
    return 100 - 100 / (1 + au / max(ad, 1e-12))


def diario(inst):
    d = A.get(f"/api/v5/market/candles?instId={inst}&bar=1Dutc&limit=80")
    return [float(x[4]) for x in reversed(d) if len(x) > 8 and x[8] == "1"]


def tendencia(c):
    if len(c) < N_MEDIA + SUBIDA:
        return False
    m, m10 = sum(c[-N_MEDIA:]) / N_MEDIA, sum(c[-N_MEDIA - SUBIDA:-SUBIDA]) / N_MEDIA
    return c[-1] > m and m > m10


def atr(c4):
    trs = [max(c4[i]["h"], c4[i - 1]["c"]) - min(c4[i]["l"], c4[i - 1]["c"]) for i in range(len(c4) - P.ATR_N, len(c4))]
    return sum(trs) / P.ATR_N


def correr(st, radar, lista, now, diario_f=None):
    diario_f = diario_f or diario
    R = st.setdefault("recuo", {"pend": {}, "abertas": {}, "fechadas": [], "ultimo": {}})
    msgs = []
    btc_ok = "BTC" in lista and tendencia(diario_f(lista["BTC"]["inst"]))
    for a, info, c4 in radar:
        p = R["pend"].get(a)
        if p:
            for b in c4:
                if p["t_sig"] < b["t"] <= p["t_sig"] + P.VALIDA * A.H4 and b["l"] <= p["lim"]:
                    e = min(p["lim"], b["o"]); stop = e - 2 * p["atr"]
                    R["abertas"][a] = {**p, "entrada": e, "stop": stop, "alvo": e + 2 * (e - stop), "risco": e - stop,
                                       "t_fill": b["t"], "visto": b["t"] - 1}
                    R["pend"].pop(a)
                    break
            else:
                if c4[-1]["t"] >= p["t_sig"] + P.VALIDA * A.H4:
                    R["pend"].pop(a)
        op = R["abertas"].get(a)
        if op:
            fim = A.seguir(op, [b for b in c4 if b["t"] >= op["t_fill"]])
            if fim:
                R["fechadas"].append({"asset": a, "t_sig": op["t_sig"], "r": fim[0], "motivo": fim[1]})
                R["abertas"].pop(a)
                rs = [x["r"] for x in R["fechadas"]]
                msgs.append(f"📝 OKX papel (recuo na subida, H46) — {a} fechou ({fim[1]}): {fim[0]:+.2f}R. "
                            f"{len(rs)} operações, média {sum(rs) / len(rs):+.2f}R (30 com média positiva → proposta de dinheiro real).")
        if not btc_ok or a in R["pend"] or a in R["abertas"] or a == "BTC" or c4[-1]["t"] <= R["ultimo"].get(a, 0):
            continue
        R["ultimo"][a] = c4[-1]["t"]
        if len(c4) < P.ATR_N + 2:
            continue
        r = rsi([b["c"] for b in c4])
        if r is None or r >= L_RSI:
            continue
        if not tendencia(diario_f(info["inst"])):
            continue
        time.sleep(0.1)
        R["pend"][a] = {"t_sig": c4[-1]["t"], "lim": c4[-1]["c"] * (1 - P.OFFSET), "atr": atr(c4), "rsi": round(r, 1)}
        msgs.append(f"📝 OKX papel (recuo na subida, H46) — {a}: RSI {r:.0f} numa tendência de subida com o BTC a subir; "
                    f"compra limite {c4[-1]['c'] * (1 - P.OFFSET):.6g} (válida 8 h). Só papel.")
    rs = [x["r"] for x in R["fechadas"]]
    R["resumo"] = {"btc_em_subida": btc_ok, "pendentes": sorted(R["pend"]), "abertas": sorted(R["abertas"]),
                   "metricas": A.metricas(rs)}
    del R["fechadas"][:-1000]
    for k in [k for k in R["ultimo"] if k not in lista]:
        R["ultimo"].pop(k)
    return msgs
