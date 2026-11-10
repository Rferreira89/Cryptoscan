"""(10/11, ordem executiva do Rui) Vigia de DECAIMENTO: a estrategia ao vivo (real, papel ou sombra) continua a
comportar-se como a evidencia que a pos ali?

Ideia adaptada de sf-edge-watch (daviddme/claude-skills, MIT): comparar o resultado ao vivo com o do teste e com o
proprio passado recente. Aqui com estatistica em vez de limiares fixos:
  - media de R ao vivo com intervalo de 90% por reamostragem;
  - "morta"        : o intervalo de 90% fica todo abaixo de 0 (perde dinheiro com confianca);
  - "em_decaimento": o intervalo fica todo abaixo da expectativa de referencia (teste), mas ainda nao todo < 0;
  - "a_vigiar"     : a media das ultimas 10 e pior do que a de referencia em mais de 0,5R, ou PF ao vivo < metade do
                     PF de referencia (quando conhecido);
  - "viva"         : nenhum sinal acima;
  - "sem_dados"    : menos de 10 operacoes fechadas (nada se conclui).
So leitura e calculo: nao liga nem desliga nada. O que fazer com uma estrategia "morta" e decisao do Rui."""
import random
import statistics as st

N_MIN = 10

# Expectativa de referencia (R liquido por operacao) e de onde vem. So valores registados no repositorio.
REFERENCIAS = {
    "H40": {"media_R": 0.107, "fonte": "backtest B1 2021-26, 522 operacoes (investigacao.md H40)"},
    "PANICO_OKX": {"media_R": 0.107, "fonte": "= H40"},
    "H45": {"media_R": 0.12, "fonte": "backtest B1 Bybit (investigacao.md H45)"},
    "PANICO_BYBIT": {"media_R": 0.12, "fonte": "= H45"},
    "H46": {"media_R": 0.147, "fonte": "backtest 2023-26, 282 operacoes (investigacao.md H46)"},
    "TF-SHORT papel": {"media_R": 0.166, "fonte": "backtest TF-SHORT U2"},
    "TF-SHORT sombra": {"media_R": 0.166, "fonte": "backtest TF-SHORT U2"},
    "Kronos K1 sombra": {"media_R": -0.052, "fonte": "fora da amostra 08/2024-11/2026, 2936 sinais (k1_oos)"},
}


DIAS_MIN = 5


def _ic90(R, n=2000, semente=3, grupos=None):
    """Intervalo de 90% da media por reamostragem. Com `grupos` (ex.: dia de entrada), reamostra GRUPOS inteiros:
    operacoes abertas no mesmo dia no mesmo sentido sao quase a mesma aposta e nao contam como independentes."""
    rs = random.Random(semente)
    if grupos:
        blocos = {}
        for r, g in zip(R, grupos):
            blocos.setdefault(g, []).append(r)
        bl = list(blocos.values())
        meds = []
        for _ in range(n):
            amostra = [x for _ in bl for x in rs.choice(bl)]
            meds.append(st.mean(amostra))
        meds.sort()
        return meds[int(0.05 * n)], meds[int(0.95 * n) - 1]
    m = sorted(st.mean(rs.choice(R) for _ in R) for _ in range(n))
    return m[int(0.05 * n)], m[int(0.95 * n) - 1]


def _pf(R):
    g, p = sum(r for r in R if r > 0), -sum(r for r in R if r < 0)
    return round(g / p, 2) if p else None


def estado(R, ref=None, pf_ref=None, grupos=None):
    """R: lista de R liquidos por ordem de fecho. ref: expectativa de referencia (R). grupos: chave de dependencia de
    cada operacao (ex.: dia de entrada). Devolve dict com estado e porques."""
    if grupos is not None:
        pares = [(r, g) for r, g in zip(R, grupos) if r is not None]
        R, grupos = [r for r, _ in pares], [g for _, g in pares]
    R = [r for r in R if r is not None]
    out = {"n": len(R), "referencia_R": ref}
    n_ind = len(set(grupos)) if grupos is not None else len(R)
    if grupos is not None:
        out["dias_independentes"] = n_ind
    if len(R) < N_MIN or (grupos is not None and n_ind < DIAS_MIN):
        motivo = (f"so {len(R)} operacoes fechadas (minimo {N_MIN})" if len(R) < N_MIN else
                  f"{len(R)} operacoes mas so {n_ind} dia(s) de entrada independentes (minimo {DIAS_MIN})")
        out.update(estado="sem_dados", porques=[motivo])
        if R:
            out["media_R"] = round(st.mean(R), 3)
        return out
    lo, hi = _ic90(R, grupos=grupos)
    m, pf = st.mean(R), _pf(R)
    rec = st.mean(R[-10:])
    out.update(media_R=round(m, 3), ic90=[round(lo, 3), round(hi, 3)], pf=pf, media_ultimas10=round(rec, 3))
    porques = []
    if hi < 0:
        out["estado"] = "morta"
        porques.append("intervalo de 90% da media todo abaixo de 0")
    elif ref is not None and hi < ref:
        out["estado"] = "em_decaimento"
        porques.append(f"intervalo de 90% todo abaixo da referencia ({ref:+.3f}R)")
    else:
        out["estado"] = "viva"
        if ref is not None and rec < ref - 0.5:
            porques.append(f"ultimas 10: {rec:+.2f}R, mais de 0,5R abaixo da referencia")
        if pf_ref and pf is not None and pf < pf_ref / 2:
            porques.append(f"PF ao vivo {pf} < metade do PF de referencia {pf_ref}")
        if porques:
            out["estado"] = "a_vigiar"
    out["porques"] = porques
    return out


def vigiar(ops):
    """ops: registo unico (engine/registo.op). Agrupa por (estrategia, classe), so classes ao vivo
    (executada, papel, sombra), por ordem de fecho."""
    g = {}
    for o in ops:
        if o.get("classe") not in ("executada", "papel", "sombra") or o.get("R") is None:
            continue
        g.setdefault((o["estrategia"], o["classe"]), []).append(o)
    out = []
    for (est, cl), xs in g.items():
        xs.sort(key=lambda o: o.get("t_saida") or o.get("t_entrada") or 0)
        ref = (REFERENCIAS.get(est) or {}).get("media_R")
        e = estado([o["R"] for o in xs], ref, grupos=[int((o.get("t_entrada") or 0) // 86400) for o in xs])
        out.append({"estrategia": est, "classe": cl, **e,
                    "fonte_referencia": (REFERENCIAS.get(est) or {}).get("fonte")})
    ordem = {"morta": 0, "em_decaimento": 1, "a_vigiar": 2, "viva": 3, "sem_dados": 4}
    return sorted(out, key=lambda x: (ordem[x["estado"]], -x["n"]))
