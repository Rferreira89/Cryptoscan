"""(11/11) Viabilidade economica com o capital REAL: o risco que os minimos de ordem e a distancia do stop impoem.

Funcoes puras, sem rede e sem efeito em ordens (nao ligado ao executor). Respondem a "com este capital, quanto
arrisco DE FACTO se esta estrategia entrar aqui?", em vez de um risco percentual teorico que a ordem minima
nao deixa cumprir. Os custos entram no risco: comissao e spread de entrada e saida, deslize no stop e juro
(short em margem) ou funding (perpetuos)."""

BYBIT_COMISSAO = 0.0025          # por lado, taxa unica da Bybit UE desde 05/10/2026 (fonte secundaria)
BYBIT_DESLIZE = 0.001            # por lado (o mesmo da arena e do papel)
OKX_COMISSAO = 0.0005            # taker por lado
OKX_DESLIZE = 0.001


def risco_real(capital, nocional, stop_frac, comissao, deslize, spread=0.0, juro_total=0.0):
    """Perda em USDC se o stop for tocado, com custos. stop_frac = |stop/entrada - 1|."""
    if capital <= 0 or nocional <= 0 or stop_frac <= 0:
        return None
    perda = nocional * (stop_frac + 2 * (comissao + deslize) + spread + juro_total)
    return {"perda_usdc": round(perda, 4), "perda_pct": round(perda / capital * 100, 3)}


def bybit_min(capital, stop_frac, min_ordem=5.0, risco_pct_alvo=0.5, spread=0.001, juro_dia_pct=None, dias=8.7,
              teto_pct=None):
    """Posicao na Bybit UE: a do risco-alvo, ou a ordem minima se esta for maior. Diz o risco REAL e se cabe no teto."""
    alvo = capital * risco_pct_alvo / 100 / stop_frac if stop_frac > 0 else 0
    noc = max(alvo, min_ordem)
    juro = (juro_dia_pct or 0) / 100 * dias
    r = risco_real(capital, noc, stop_frac, BYBIT_COMISSAO, BYBIT_DESLIZE, spread, juro)
    if r is None:
        return None
    imposto = noc > alvo + 1e-12
    out = {"nocional": round(noc, 4), "forcado_pela_ordem_minima": imposto, **r,
           "risco_alvo_pct": risco_pct_alvo, "juro_confirmado": juro_dia_pct is not None,
           "cabe_no_capital": noc <= capital}
    if teto_pct is not None:
        out["cabe_no_teto"] = r["perda_pct"] <= teto_pct + 1e-9
    return out


def stop_max_para(capital, teto_pct, min_ordem=5.0, spread=0.001):
    """Maior distancia de stop que mantem a ordem minima dentro do teto de perda (com custos)."""
    custos = 2 * (BYBIT_COMISSAO + BYBIT_DESLIZE) + spread
    return max(0.0, capital * teto_pct / 100 / min_ordem - custos)


def okx_contrato(capital, peso, preco, ct_val, min_sz, lote, stop_frac, funding_total=0.0):
    """TF-SHORT na OKX: nocional = capital x peso, arredondado ao lote; abaixo do minimo do contrato nao entra
    (nunca sobe para caber). Devolve o risco REAL no stop."""
    import math
    alvo = capital * peso
    n = math.floor(alvo / (ct_val * preco) / lote + 1e-9) * lote
    if n < min_sz or n <= 0:
        return {"entra": False, "motivo": "abaixo do minimo do contrato", "minimo_usd": round(min_sz * ct_val * preco, 4),
                "capital_minimo": round(min_sz * ct_val * preco / peso, 2) if peso else None}
    noc = n * ct_val * preco
    r = risco_real(capital, noc, stop_frac, OKX_COMISSAO, OKX_DESLIZE, 0.0, max(0.0, -funding_total))
    return {"entra": True, "contratos": n, "nocional": round(noc, 4), **r}


def agregado(riscos_pct, correlacao=1.0):
    """Risco agregado de posicoes simultaneas. correlacao=1 (o caso dos shorts do mesmo dia num mercado
    lateral, que perdem juntos) soma; 0 da a raiz da soma dos quadrados. Devolve os dois extremos se pedido."""
    soma = sum(riscos_pct)
    raiz = sum(x * x for x in riscos_pct) ** 0.5
    return round(correlacao * soma + (1 - correlacao) * raiz, 3)
