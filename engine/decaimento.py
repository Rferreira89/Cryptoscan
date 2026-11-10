"""(10/11, ordem executiva do Rui; revisto na ordem de 10/11 ponto 6) Vigia de DEGRADACAO: a estrategia ao vivo (real,
papel ou sombra) continua a comportar-se como a evidencia que a pos ali?

Ideia adaptada de sf-edge-watch (daviddme/claude-skills, MIT), com estatistica em vez de limiares fixos:
  - operacoes abertas no MESMO DIA sao quase a mesma aposta: o intervalo de 90% da media reamostra DIAS inteiros
    e a amostra conta-se tambem em dias independentes;
  - "evidencia_insuficiente": menos de 10 operacoes ou menos de 5 dias independentes - nada se conclui;
  - as conclusoes so sao DEFINITIVAS com pelo menos 30 operacoes em 10 dias; abaixo disso ficam "preliminares";
  - "morta"                 : intervalo todo abaixo de 0 (perde com confianca);
  - "abaixo_da_referencia"  : intervalo todo abaixo da expectativa do teste, mas nao todo abaixo de 0;
  - "positiva"              : intervalo todo acima de 0;
  - "inconclusiva"          : o intervalo contem 0 (e a referencia): o que se ve cabe na variabilidade normal;
  - aviso (nao muda o estado): ultimas 10 mais de 0,5R abaixo da referencia.
A referencia e sempre a do teste da MESMA variante (ex.: H40 panico isolado vs panico do mercado todo); quando o
teste so deu as duas metades, usa-se a pior (conservador). Real e papel comparam-se com a mesma referencia em R.
So leitura e calculo: nao liga nem desliga nada."""
import random
import statistics as st

N_MIN = 10

# Expectativa de referencia (R liquido por operacao) e de onde vem. So valores registados no repositorio.
REFERENCIAS = {
    "H40": {"media_R": 0.107, "fonte": "backtest B1 2021-26, 522 operacoes (investigacao.md H40)"},
    "H40 mercado": {"media_R": 0.17, "fonte": "backtest H40 so panico do mercado todo: +0,17R / +0,41R nas duas metades "
                                              "(registo de 04/11 em tools/okx_exec.py); usa a pior"},
    "H40 isolado": {"media_R": -0.126, "fonte": "backtest H40 panico isolado: -0,126R na metade recente (registo de 04/11 em "
                                               "tools/okx_exec.py)"},
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


N_FORTE, DIAS_FORTE = 30, 10


def estado(R, ref=None, pf_ref=None, grupos=None):
    """R: lista de R liquidos por ordem de fecho. ref: expectativa de referencia (R). grupos: chave de dependencia de
    cada operacao (ex.: dia de entrada). Devolve dict com estado, se e definitivo, e porques."""
    if grupos is not None:
        pares = [(r, g) for r, g in zip(R, grupos) if r is not None]
        R, grupos = [r for r, _ in pares], [g for _, g in pares]
    R = [r for r in R if r is not None]
    out = {"n": len(R), "referencia_R": ref}
    n_ind = len(set(grupos)) if grupos is not None else len(R)
    out["dias_independentes"] = n_ind
    if R:
        out["media_R"] = round(st.mean(R), 3)
    if len(R) < N_MIN or n_ind < DIAS_MIN:
        motivo = (f"so {len(R)} operacoes fechadas (minimo {N_MIN})" if len(R) < N_MIN else
                  f"{len(R)} operacoes mas so {n_ind} dia(s) de entrada independentes (minimo {DIAS_MIN})")
        out.update(estado="evidencia_insuficiente", definitivo=False, porques=[motivo])
        return out
    lo, hi = _ic90(R, grupos=grupos)
    pf = _pf(R)
    rec = st.mean(R[-10:])
    definitivo = len(R) >= N_FORTE and n_ind >= DIAS_FORTE
    out.update(ic90=[round(lo, 3), round(hi, 3)], pf=pf, media_ultimas10=round(rec, 3), definitivo=definitivo)
    porques = []
    if hi < 0:
        out["estado"] = "morta"
        porques.append("intervalo de 90% da media todo abaixo de 0")
    elif ref is not None and hi < ref:
        out["estado"] = "abaixo_da_referencia"
        porques.append(f"intervalo de 90% todo abaixo da referencia do teste ({ref:+.3f}R)")
    elif lo > 0:
        out["estado"] = "positiva"
        porques.append("intervalo de 90% da media todo acima de 0")
    else:
        out["estado"] = "inconclusiva"
        porques.append("o intervalo de 90% contem 0: cabe na variabilidade normal")
    if not definitivo:
        porques.append(f"preliminar: {len(R)} operacoes em {n_ind} dias (definitivo com {N_FORTE} em {DIAS_FORTE})")
    avisos = []
    if ref is not None and rec < ref - 0.5:
        avisos.append(f"ultimas 10: {rec:+.2f}R, mais de 0,5R abaixo da referencia")
    if pf_ref and pf is not None and pf < pf_ref / 2:
        avisos.append(f"PF ao vivo {pf} < metade do PF de referencia {pf_ref}")
    out["porques"], out["avisos"] = porques, avisos
    return out


def variante(o):
    """Nome da variante para escolher a referencia certa (a H40 tem duas com evidencia muito diferente)."""
    e = o["estrategia"]
    tipo = (o.get("bruto") or {}).get("tipo")
    if e in ("H40", "PANICO_OKX") and tipo in ("isolado", "mercado"):
        return f"H40 {tipo}"
    return e


def vigiar(ops):
    """ops: registo unico (engine/registo.op). Agrupa por (estrategia, classe), so classes ao vivo
    (executada, papel, sombra), por ordem de fecho."""
    g = {}
    for o in ops:
        if o.get("classe") not in ("executada", "papel", "sombra") or o.get("R") is None:
            continue
        g.setdefault((variante(o), o["classe"]), []).append(o)
    out = []
    for (est, cl), xs in g.items():
        xs.sort(key=lambda o: o.get("t_saida") or o.get("t_entrada") or 0)
        ref = (REFERENCIAS.get(est) or {}).get("media_R")
        e = estado([o["R"] for o in xs], ref, grupos=[int((o.get("t_entrada") or 0) // 86400) for o in xs])
        out.append({"estrategia": est, "classe": cl, **e,
                    "fonte_referencia": (REFERENCIAS.get(est) or {}).get("fonte")})
    ordem = {"morta": 0, "abaixo_da_referencia": 1, "inconclusiva": 2, "positiva": 3, "evidencia_insuficiente": 4}
    return sorted(out, key=lambda x: (ordem[x["estado"]], -x["n"]))
