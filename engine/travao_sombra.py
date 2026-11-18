"""(18/11, ordem final, prioridade 5) Travao do papel em modo SOMBRA: regista, ao lado da regra ativa, o que duas
regras alternativas decidiriam, SEM mudar nada (nao corta, nao reabre, nao avisa por Telegram).

Regra ativa (engine/paper_ring, inalterada): corta com R medio < 0 em >= 20 operacoes. Simulacao (backtest/
investigacao_18nov.md): corta 58-80% das estrategias com +0,05 a +0,10R em 150 operacoes.
Sombra:
  K4  t = media / (desvio / raiz(n)) < -2,33 com n >= 20;
  K8  probabilidade bayesiana de vantagem negativa > 0,90 com n >= 30 (prior N(0; 0,15^2) para a media).
Fica em state["travao_sombra"][estrategia]: as estatisticas da ultima volta e, para cada regra, a primeira vez que
cortaria (t, n, R medio). Para comparar decisoes reais das tres regras com o tempo."""
import math
import statistics

K4_N, K4_T = 20, -2.33
K8_N, K8_P, K8_PRIOR_SD = 30, 0.90, 0.15
ATIVA_N = 20


def estatisticas(rs):
    n = len(rs)
    if not n:
        return {"n": 0}
    m = sum(rs) / n
    sd = statistics.pstdev(rs) if n > 1 else 0.0
    out = {"n": n, "r_medio": round(m, 4), "desvio": round(sd, 4)}
    if n > 1 and sd > 0:
        out["t_stat"] = round(m / (sd / math.sqrt(n)), 3)
        var = sd ** 2
        prec = 1 / K8_PRIOR_SD ** 2 + n / var
        pm, psd = (n / var * m) / prec, math.sqrt(1 / prec)
        out["p_negativa"] = round(0.5 * (1 + math.erf((0 - pm) / (psd * math.sqrt(2)))), 4)
    return out


def decisoes(e):
    """{regra: corta?} para as estatisticas e."""
    n = e.get("n") or 0
    return {"ativa": n >= ATIVA_N and (e.get("r_medio") or 0) < 0,
            "K4": n >= K4_N and e.get("t_stat") is not None and e["t_stat"] < K4_T,
            "K8": n >= K8_N and e.get("p_negativa") is not None and e["p_negativa"] > K8_P}


def registar(state, k, closed, now):
    """Atualiza a sombra da estrategia k a partir das operacoes fechadas. Nunca levanta excecao para fora."""
    try:
        rs = [c["r"] for c in closed or [] if c.get("r") is not None]
        e = estatisticas(rs)
        d = decisoes(e)
        s = state.setdefault("travao_sombra", {}).setdefault(k, {})
        s.update(t=int(now), **{x: e.get(x) for x in ("n", "r_medio", "desvio", "t_stat", "p_negativa")}, decisoes=d)
        primeira = s.setdefault("primeiro_corte", {})
        for regra, corta in d.items():
            if corta and regra not in primeira:
                primeira[regra] = {"t": int(now), "n": e["n"], "r_medio": e.get("r_medio")}
        return s
    except Exception as ex:                    # noqa: BLE001 - a sombra nunca pode parar o papel
        return {"erro": str(ex)[:80]}
