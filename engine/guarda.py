"""(10/11, ordem executiva do Rui) Guarda antes da ordem: verificacoes puras (sem rede) que um executor chama antes de
enviar uma entrada. Nunca envia nem cancela nada: devolve (pode, motivos).

Adaptado de ideias de repositorios de referencia (licenca MIT):
  - risk-guard (daviddme/claude-skills): veto sem excecoes antes de cada ordem;
  - drawdown-circuit-breaker (tradermonty/claude-trading-skills): pausa depois de uma sequencia de perdas;
  - desk-risk-limits (galleonlabs/hypergrok-trading-desk): limite por grupo de ativos correlacionados e stop
    obrigatorio na corretora.
O Cryptoscan ja tinha: ids de ordem deterministas (sem duplicados apos falhas), stop anexado, travao da conta, teto de
risco aberto (OKX, 08/11). Esta guarda acrescenta o que faltava, com cada limite DESLIGADO por omissao (0): ligar um
limite e uma alteracao de risco que so o Rui autoriza.

Limites (cfg["guarda"]):
  max_ordens_dia        - maximo de entradas novas por corretora em 24 h (0 = sem limite)
  perdas_seguidas_max   - depois de N perdas reais seguidas, pausa de `pausa_h` horas (0 = desligado)
  pausa_h               - duracao da pausa (omissao 24)
  max_por_grupo         - maximo de posicoes no mesmo grupo correlacionado (0 = desligado); grupos em cfg["grupos"]
  idade_max_s           - idade maxima do sinal (0 = desligado)
Sempre ligado (nao e um limite de risco, e sanidade): stop presente, do lado certo e a menos de 50% da entrada."""

H = 3600


def stop_valido(lado, entrada, stop):
    if not entrada or not stop or entrada <= 0 or stop <= 0:
        return False, "sem stop"
    d = (entrada - stop) / entrada if lado == "LONG" else (stop - entrada) / entrada
    if d <= 0:
        return False, "stop do lado errado"
    if d >= 0.5:
        return False, "stop a mais de 50% da entrada"
    return True, None


def perdas_seguidas(fechadas):
    """Numero de perdas consecutivas no fim do historico (fechadas por ordem de fecho; cada uma com 'resultado' < 0
    ou > 0). Resultados desconhecidos (None) interrompem a contagem: nao se inventa uma perda."""
    n = 0
    for f in reversed(fechadas):
        r = f.get("resultado")
        if r is None or r >= 0:
            break
        n += 1
    return n


def verificar(cfg, *, lado, entrada, stop, ativo, t_sinal, agora, entradas_24h=0, fechadas=(), abertas=()):
    """cfg: configuracao do executor (usa cfg['guarda'] e cfg['grupos']). fechadas: [{'resultado', 't'}] reais por ordem
    de fecho. abertas: ativos com posicao ou ordem pendente. Devolve (pode, [motivos])."""
    g = (cfg or {}).get("guarda") or {}
    motivos = []
    ok, m = stop_valido(lado, entrada, stop)
    if not ok:
        motivos.append(m)
    if ativo in abertas:
        motivos.append("ja ha posicao ou ordem neste ativo")
    if g.get("idade_max_s") and agora - t_sinal > g["idade_max_s"]:
        motivos.append("sinal velho demais")
    if g.get("max_ordens_dia") and entradas_24h >= g["max_ordens_dia"]:
        motivos.append(f"limite de {g['max_ordens_dia']} entradas em 24 h")
    if g.get("perdas_seguidas_max"):
        n = perdas_seguidas(list(fechadas))
        ult = max((f.get("t") or 0 for f in fechadas), default=0)
        if n >= g["perdas_seguidas_max"] and agora - ult < float(g.get("pausa_h", 24)) * H:
            motivos.append(f"{n} perdas seguidas: pausa ate {g.get('pausa_h', 24)} h depois da ultima")
    if g.get("max_por_grupo"):
        grupos = (cfg or {}).get("grupos") or {}
        meu = grupos.get(ativo)
        if meu is not None and sum(1 for a in abertas if grupos.get(a) == meu) >= g["max_por_grupo"]:
            motivos.append(f"grupo correlacionado '{meu}' no maximo ({g['max_por_grupo']})")
    return not motivos, motivos


def grupos_por_correlacao(retornos, limiar=0.75):
    """retornos: {ativo: [r1, r2, ...]} alinhados no tempo. Liga ativos com correlacao >= limiar (componentes ligadas).
    Devolve {ativo: nome_do_grupo}. Ativos sem dados suficientes (menos de 48 pontos) ficam fora."""
    import math
    nomes = [a for a, r in retornos.items() if len(r) >= 48]

    def corr(a, b):
        x, y = retornos[a], retornos[b]
        n = min(len(x), len(y)); x, y = x[-n:], y[-n:]
        mx, my = sum(x) / n, sum(y) / n
        sx = math.sqrt(sum((v - mx) ** 2 for v in x)); sy = math.sqrt(sum((v - my) ** 2 for v in y))
        return sum((p - mx) * (q - my) for p, q in zip(x, y)) / (sx * sy) if sx and sy else 0.0
    pai = {a: a for a in nomes}

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]; a = pai[a]
        return a
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            if corr(a, b) >= limiar:
                pai[raiz(a)] = raiz(b)
    return {a: raiz(a) for a in nomes}
