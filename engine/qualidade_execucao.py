"""(11/11, auditoria P5 e Execution Intelligence) Instrumentacao da qualidade de execucao. So mede: nao decide
entradas, nao filtra sinais, nao muda executores.

Origem do pedido: PARTI (10/11) fechou 2,57% abaixo do stop (deslize de -0,22R). Um caso nao chega para um filtro de
liquidez. Este modulo junta, por operacao e por instantaneo do livro, o que e preciso para o estudar:
  - spread, profundidade a 0,5% / 1% / 2%, desequilibrio, volume 24 h, volatilidade (ATR %);
  - deslize PREVISTO para uma ordem a mercado de um dado valor, dos dois lados (reutiliza engine.liquidity.book_metrics
    para a compra e acrescenta a venda, que e o lado do stop de um long);
  - deslize REALIZADO (de engine.contabilidade: no stop e na entrada, em R);
  - previsto contra realizado, por ativo, mercado e tipo de ordem.
`recomendacao` so sugere um limite quando ha AMOSTRA_MIN operacoes realizadas e a diferenca entre grupos de liquidez
tem intervalo de confianca que nao cruza zero; abaixo disso devolve "amostra insuficiente"."""
import math

from engine.liquidity import book_metrics

AMOSTRA_MIN = 30
NIVEIS = (0.005, 0.01, 0.02)


def _andar(niveis, valor):
    """Preco medio de executar `valor` (moeda de cotacao) contra os niveis [(preco, qtd)]; None se o livro nao chega."""
    falta, custo, qtd = valor, 0.0, 0.0
    for p, q in niveis:
        t = min(q, falta / p)
        custo += t * p
        qtd += t
        falta -= t * p
        if falta <= 1e-9:
            return custo / qtd
    return None


def livro(bids, asks, valor=1000.0, ct_val=1.0):
    """Instantaneo do livro. bids/asks [(preco, contratos)] do topo para baixo; ct_val converte contratos em moeda."""
    b = [(float(p), float(q) * ct_val) for p, q in bids if float(p) > 0]
    a = [(float(p), float(q) * ct_val) for p, q in asks if float(p) > 0]
    if not b or not a:
        return None
    mid = (b[0][0] + a[0][0]) / 2
    out = {"mid": mid, "spread_bps": round((a[0][0] - b[0][0]) / mid * 1e4, 2)}
    for n in NIVEIS:
        out[f"prof_{n * 100:g}pct"] = round(sum(p * q for p, q in b if p >= mid * (1 - n)) +
                                            sum(p * q for p, q in a if p <= mid * (1 + n)), 2)
    bm = book_metrics(b, a, order_usd=valor) or {}
    out["desequilibrio"] = bm.get("imbalance")
    compra = _andar(a, valor)
    venda = _andar(b, valor)
    out["deslize_compra_bps"] = None if compra is None else round((compra / mid - 1) * 1e4, 2)
    out["deslize_venda_bps"] = None if venda is None else round((1 - venda / mid) * 1e4, 2)
    out["valor_teste"] = valor
    return out


def previsto_em_r(inst_livro, entrada, stop, lado="LONG"):
    """Deslize previsto de uma saida a mercado no stop, em R (negativo = pior). Usa o lado contrario a posicao."""
    if not inst_livro or not entrada or not stop:
        return None
    bps = inst_livro.get("deslize_venda_bps" if lado == "LONG" else "deslize_compra_bps")
    if bps is None:
        return None
    risco = abs(entrada - stop) / entrada
    return round(-(bps / 1e4) * (stop / entrada) / risco, 4) if risco else None


def registo(op, inst_livro=None, vol24h=None, atr_pct=None, mercado=None, tipo_ordem=None):
    """Junta uma operacao de engine.contabilidade (ou do papel) com o instantaneo do livro mais proximo."""
    return {"ativo": op.get("ativo"), "corretora": op.get("corretora"), "estrategia": op.get("estrategia"),
            "mercado": mercado or op.get("corretora"), "tipo_ordem": tipo_ordem or "stop_mercado",
            "spread_bps": (inst_livro or {}).get("spread_bps"), "prof_1pct": (inst_livro or {}).get("prof_1pct"),
            "vol24h": vol24h, "atr_pct": atr_pct,
            "previsto_stop_r": previsto_em_r(inst_livro, op.get("entrada"), op.get("stop"), op.get("lado", "LONG")),
            "realizado_stop_r": op.get("deslize_stop_r"), "realizado_entrada_r": op.get("deslize_entrada_r")}


def _media_ic(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else None), None
    m = sum(xs) / n
    dp = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, (m - 1.96 * dp / math.sqrt(n), m + 1.96 * dp / math.sqrt(n))


def analise(registos, chave="ativo"):
    """Deslize realizado no stop por grupo, com o previsto ao lado e o erro da previsao."""
    g = {}
    for r in registos:
        if r.get("realizado_stop_r") is None:
            continue
        g.setdefault(r.get(chave) or "?", []).append(r)
    out = {}
    for k, rs in sorted(g.items()):
        real = [r["realizado_stop_r"] for r in rs]
        prev = [r["previsto_stop_r"] for r in rs if r.get("previsto_stop_r") is not None]
        m, ic = _media_ic(real)
        out[k] = {"n": len(rs), "deslize_medio_r": round(m, 4), "ic95": [round(x, 4) for x in ic] if ic else None,
                  "pior_r": round(min(real), 4), "previsto_medio_r": round(sum(prev) / len(prev), 4) if prev else None,
                  "n_com_previsao": len(prev)}
    return out


def recomendacao(registos, corte_prof=None):
    """So recomenda um minimo de profundidade com amostra suficiente e diferenca significativa entre os grupos."""
    rs = [r for r in registos if r.get("realizado_stop_r") is not None and r.get("prof_1pct") is not None]
    if len(rs) < AMOSTRA_MIN:
        return {"decisao": "amostra insuficiente", "n": len(rs), "minimo": AMOSTRA_MIN}
    profs = sorted(r["prof_1pct"] for r in rs)
    corte = corte_prof or profs[len(profs) // 2]
    fino = [r["realizado_stop_r"] for r in rs if r["prof_1pct"] < corte]
    fundo = [r["realizado_stop_r"] for r in rs if r["prof_1pct"] >= corte]
    if len(fino) < 10 or len(fundo) < 10:
        return {"decisao": "amostra insuficiente por grupo", "n_fino": len(fino), "n_fundo": len(fundo)}
    mf, _ = _media_ic(fino)
    mg, _ = _media_ic(fundo)
    vf = sum((x - mf) ** 2 for x in fino) / (len(fino) - 1)
    vg = sum((x - mg) ** 2 for x in fundo) / (len(fundo) - 1)
    ep = math.sqrt(vf / len(fino) + vg / len(fundo))
    dif = mg - mf
    lo, hi = dif - 1.96 * ep, dif + 1.96 * ep
    sig = lo > 0
    return {"decisao": "diferenca significativa: estudar filtro (decisao do Rui)" if sig else "sem diferenca significativa",
            "corte_prof_1pct": corte, "deslize_fino_r": round(mf, 4), "deslize_fundo_r": round(mg, 4),
            "diferenca_r": round(dif, 4), "ic95": [round(lo, 4), round(hi, 4)], "n_fino": len(fino), "n_fundo": len(fundo)}
