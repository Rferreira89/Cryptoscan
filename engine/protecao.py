"""(ordem do Rui de 10/11, ponto 1) Confirmacao COMPLETA do stop de uma posicao: a verificacao atual do executor da
OKX (_tem_stop_na_okx) so confirma que existe algum stop pendente no contrato; nao confirma o lado, a quantidade nem
o preco. Esta funcao recebe o que a OKX devolve (orders-algo-pending e positions) e diz se o stop cobre a posicao
TODA, do lado certo e abaixo/acima da entrada. So leitura e calculo: nao esta ligada ao executor."""


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def stop_cobre(algos, pos, lado="LONG", entrada=None):
    """algos: lista de ordens algo pendentes da OKX (conditional/oco) desse contrato.
    pos: quantidade aberta (contratos). Devolve (ok, motivos)."""
    motivos = []
    q = _f(pos)
    if not q:
        return False, ["posicao sem quantidade"]
    fecho = "sell" if lado == "LONG" else "buy"
    validos, cobertura = [], 0.0
    for a in algos or []:
        sl = _f(a.get("slTriggerPx"))
        if not sl:
            continue
        if a.get("side") != fecho:
            motivos.append(f"stop do lado errado ({a.get('side')})"); continue
        if entrada and ((lado == "LONG" and sl >= entrada) or (lado == "SHORT" and sl <= entrada)):
            motivos.append("stop do lado errado da entrada"); continue
        if str(a.get("closeFraction") or "") == "1":
            cobertura = q
        else:
            cobertura += _f(a.get("sz")) or 0.0
        validos.append(a)
    if not validos:
        return False, motivos or ["sem stop ativo"]
    if cobertura + 1e-12 < q:
        return False, motivos + [f"stop cobre {cobertura:g} de {q:g} contratos"]
    return True, motivos
