"""Deflated Sharpe Ratio (Bailey e Lopez de Prado, 2014, "The Deflated Sharpe Ratio: Correcting for Selection Bias,
Backtest Overfitting and Non-Normality", Journal of Portfolio Management 40(5)).

  SR      = media / desvio dos retornos (por observacao, NAO anualizado)
  PSR(SR*) = Phi( (SR - SR*) * sqrt(T - 1) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2) )      g3 assimetria, g4 curtose (normal = 3)
  SR0     = sqrt(V[SR_n]) * ( (1 - gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N e)) )   gamma = Euler-Mascheroni
  DSR     = PSR(SR0)

N e o numero de tentativas independentes que foram testadas para chegar a esta estrategia; V[SR_n] e a variancia do
Sharpe entre essas tentativas. Quando nao se conhece V[SR_n] usa-se a variancia do estimador sob a hipotese nula,
1/(T-1) (e o que o artigo usa como aproximacao; esta escolha fica registada no resultado).

Pressupostos: observacoes independentes e identicamente distribuidas (o erro do Sharpe vem de Mertens/Lo); com
retornos autocorrelacionados o erro esta subestimado. Usar por operacao (cada operacao e uma observacao) ou por dia.
"""
import json
import math
import os

from backtest.quant import estatistica as E

MIN_OBS = 30


def sharpe(r):
    s = E.desvio(r)
    return 0.0 if s == 0 else E.media(r) / s


def erro_sharpe(sr, t, g3, g4):
    v = (1 - g3 * sr + (g4 - 1) / 4 * sr * sr) / (t - 1)
    return math.sqrt(max(v, 1e-18))


def psr(sr, sr_ref, t, g3=0.0, g4=3.0):
    """Probabilidade de o Sharpe verdadeiro ser maior do que sr_ref."""
    return E.N01.cdf((sr - sr_ref) / erro_sharpe(sr, t, g3, g4))


def sr_max_esperado(n, var_sr):
    """Sharpe maximo esperado entre n tentativas sem vantagem nenhuma (todas com Sharpe verdadeiro zero)."""
    if n <= 1:
        return 0.0
    z = (1 - E.EULER) * E.N01.inv_cdf(1 - 1 / n) + E.EULER * E.N01.inv_cdf(1 - 1 / (n * math.e))
    return math.sqrt(var_sr) * z


def dsr(retornos, n_tentativas, var_sr=None, min_obs=MIN_OBS):
    """Devolve dict com SR, assimetria, curtose, SR0, DSR e o veredito. Com poucas observacoes: 'insuficiente'."""
    r = [float(x) for x in retornos if x is not None and math.isfinite(x)]
    t = len(r)
    out = {"t": t, "n_tentativas": int(n_tentativas), "min_obs": min_obs}
    if t < min_obs:
        return {**out, "estado": "insuficiente", "razao": f"{t} observacoes (minimo {min_obs})"}
    if E.desvio(r) == 0:
        return {**out, "estado": "insuficiente", "razao": "retornos sem variacao"}
    sr, g3, g4 = sharpe(r), E.assimetria(r), E.curtose(r)
    origem_var = "dada (Sharpe das tentativas)" if var_sr is not None else "aproximacao sob a nula: 1/(T-1)"
    v = var_sr if var_sr is not None else 1 / (t - 1)
    sr0 = sr_max_esperado(n_tentativas, v)
    d = psr(sr, sr0, t, g3, g4)
    return {**out, "estado": "calculado", "sr": sr, "assimetria": g3, "curtose": g4, "var_sr": v, "origem_var_sr": origem_var,
            "sr0": sr0, "psr_zero": psr(sr, 0.0, t, g3, g4), "dsr": d,
            "veredito": "vantagem provavel depois de descontar as tentativas" if d >= 0.95 else
                        "nao distinguivel da melhor de N tentativas ao acaso"}


# ---------------------------------------------------------------- contagem fundamentada das tentativas
RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contar_tentativas(forma=None):
    """Quantas hipoteses foram testadas contra os dados do CryptoScan, de onde vem cada parcela.

    minimo      = contador global do engine/hipoteses.py (afinacao + investigacao agendadas + estudos offline)
    conservador = minimo + hipoteses novas registadas (hipoteses_novas.json) + lutadores da arena (forma.json)
    O conservador pode contar duas vezes a mesma ideia (um lutador que tambem foi hipotese); por isso o DSR e
    apresentado com os dois. Cada variante de grelha conta como tentativa so quando o registo a contou."""
    import sys
    sys.path.insert(0, os.path.dirname(RAIZ))
    from engine import hipoteses as H
    g = H.contar()
    try:
        novas = len(json.load(open(os.path.join(RAIZ, "hipoteses_novas.json"), encoding="utf-8")))
    except (OSError, ValueError):
        novas = 0
    arena = len(((forma or {}).get("lutadores")) or {})
    return {"minimo": g["total"], "conservador": g["total"] + novas + arena,
            "partes": {"agendadas": g["agendadas"], "offline": g["offline"], "novas_registadas": novas, "lutadores_arena": arena}}
