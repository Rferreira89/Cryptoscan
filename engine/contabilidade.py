"""(11/11, auditoria P4) Contabilidade das operacoes REAIS: PnL bruto e liquido, comissoes, funding, deslize, R,
drawdown, profit factor, taxa de acerto e custos medios, por operacao, estrategia, corretora e ativo.

Funcoes puras (sem rede). Os dados chegam de leitores so de leitura:
  - OKX: tools/okx_contabilidade.py (positions-history + fills-history + o registo publico do executor);
  - Bybit: engine/account.agregar (ja calcula comissoes, juros e risco por operacao a partir das execucoes).

Privacidade: `registo_privado` tem valores em dinheiro e so pode ser gravado cifrado (engine.cifra).
`publico` devolve apenas contagens, R e percentagens; tem um verificador (`sem_dinheiro`) que os testes usam.

Convencoes (long ou short, por operacao):
  risco por unidade      = |entrada - stop|                        (stop do plano, nao o deslizado)
  R bruto (preco)        = (saida - entrada) / risco por unidade    (sinal invertido nos shorts)
  R liquido              = R bruto x PnL liquido / PnL de preco      (sem precisar do tamanho do contrato)
                           ou PnL liquido / risco em dinheiro, quando o risco em dinheiro e conhecido
  deslize no stop (R)    = R bruto - (-1), so quando a saida foi pelo stop (negativo = pior do que o plano)
  deslize na entrada (R) = (entrada - limite) / risco por unidade, sinal do lado (positivo = pior)"""
import math

CAMPOS_DINHEIRO = ("pnl_preco", "pnl_liquido", "comissoes", "funding", "risco_dinheiro", "penalizacao")


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def operacao(corretora, estrategia, ativo, lado, entrada, saida, stop, pnl_preco=None, pnl_liquido=None,
             comissoes=None, funding=None, risco_dinheiro=None, limite=None, motivo=None, t_abertura=None,
             t_fecho=None, penalizacao=None):
    """Registo normalizado de UMA operacao fechada. Campos em falta ficam None (nunca inventados)."""
    entrada, saida, stop = _f(entrada), _f(saida), _f(stop)
    s = -1.0 if str(lado).upper() in ("SHORT", "SELL") else 1.0
    risco_u = abs(entrada - stop) if entrada and stop else None
    r_bruto = s * (saida - entrada) / risco_u if risco_u and saida is not None else None
    pnl_preco, pnl_liquido = _f(pnl_preco), _f(pnl_liquido)
    comissoes, funding, risco_dinheiro = _f(comissoes), _f(funding), _f(risco_dinheiro)
    r_liq, metodo = None, None
    if pnl_liquido is not None and risco_dinheiro:
        r_liq, metodo = pnl_liquido / risco_dinheiro, "risco_dinheiro"
    elif r_bruto is not None and pnl_liquido is not None and pnl_preco and abs(pnl_preco) > 1e-12:
        r_liq, metodo = r_bruto * pnl_liquido / pnl_preco, "proporcao_pnl"
    custo_r = None
    if r_liq is not None and r_bruto is not None:
        custo_r = r_bruto - r_liq                          # positivo = custos (comissoes + funding pago)
    pelo_stop = motivo == "stop" or (motivo in (None, "stop ou objetivo") and r_bruto is not None and r_bruto < 0)
    desl_stop = (r_bruto + 1.0) if pelo_stop and r_bruto is not None else None
    limite = _f(limite)
    desl_ent = s * (entrada - limite) / risco_u if limite and risco_u else None
    return {"corretora": corretora, "estrategia": estrategia or "?", "ativo": ativo, "lado": "SHORT" if s < 0 else "LONG",
            "entrada": entrada, "saida": saida, "stop": stop, "limite": limite, "motivo": motivo,
            "t_abertura": t_abertura, "t_fecho": t_fecho,
            "r_bruto": _r(r_bruto), "r_liquido": _r(r_liq), "metodo_r": metodo, "custo_r": _r(custo_r),
            "deslize_stop_r": _r(desl_stop), "deslize_entrada_r": _r(desl_ent),
            "ret_preco_pct": _r(100 * s * (saida / entrada - 1)) if entrada and saida else None,
            "pnl_preco": pnl_preco, "pnl_liquido": pnl_liquido, "comissoes": comissoes, "funding": funding,
            "risco_dinheiro": risco_dinheiro, "penalizacao": _f(penalizacao),
            "completa": r_liq is not None}


def _r(x, n=4):
    return None if x is None else round(x, n)


def _dd(rs):
    """Maior queda acumulada em R e maior sequencia de perdas."""
    pico = acum = 0.0
    dd = 0.0
    seq = pior = 0
    for r in rs:
        acum += r
        pico = max(pico, acum)
        dd = min(dd, acum - pico)
        seq = seq + 1 if r < 0 else 0
        pior = max(pior, seq)
    return round(dd, 4), pior


def resumo(ops, campo="r_liquido"):
    """Metricas de um grupo de operacoes (por ordem de fecho). Usa so as operacoes com o campo conhecido."""
    ops = sorted(ops, key=lambda o: o.get("t_fecho") or 0)
    rs = [o[campo] for o in ops if o.get(campo) is not None]
    n_tot = len(ops)
    if not rs:
        return {"n": n_tot, "n_com_dados": 0, "campo": campo}
    ganhos = sum(r for r in rs if r > 0)
    perdas = -sum(r for r in rs if r < 0)
    dd, seq = _dd(rs)
    custos = [o["custo_r"] for o in ops if o.get("custo_r") is not None]
    desl = [o["deslize_stop_r"] for o in ops if o.get("deslize_stop_r") is not None]
    media = sum(rs) / len(rs)
    dp = (sum((r - media) ** 2 for r in rs) / (len(rs) - 1)) ** 0.5 if len(rs) > 1 else None
    return {"n": n_tot, "n_com_dados": len(rs), "campo": campo,
            "soma_r": round(sum(rs), 4), "expectativa_r": round(media, 4),
            "erro_padrao_r": round(dp / len(rs) ** 0.5, 4) if dp is not None else None,
            "acerto_pct": round(100 * sum(1 for r in rs if r > 0) / len(rs), 1),
            "profit_factor": round(ganhos / perdas, 3) if perdas > 0 else None,
            "drawdown_r": dd, "pior_sequencia_perdas": seq,
            "custo_medio_r": round(sum(custos) / len(custos), 4) if custos else None,
            "deslize_stop_medio_r": round(sum(desl) / len(desl), 4) if desl else None,
            "pior_deslize_stop_r": round(min(desl), 4) if desl else None}


def agrupar(ops, chave):
    g = {}
    for o in ops:
        g.setdefault(o.get(chave) or "?", []).append(o)
    return g


def relatorio(ops):
    """Relatorio completo: total, por corretora, estrategia e ativo; R liquido e, a parte, R bruto."""
    out = {"total": resumo(ops), "total_bruto": resumo(ops, "r_bruto"),
           "incompletas": sum(1 for o in ops if not o.get("completa"))}
    for chave in ("corretora", "estrategia", "ativo"):
        out[f"por_{chave}"] = {k: resumo(v) for k, v in sorted(agrupar(ops, chave).items())}
    return out


def registo_privado(ops):
    """Tudo, incluindo dinheiro: so para gravar cifrado."""
    tot = {k: round(sum(o.get(k) or 0.0 for o in ops), 6) for k in CAMPOS_DINHEIRO if any(o.get(k) is not None for o in ops)}
    return {"operacoes": ops, "totais_dinheiro": tot, "relatorio": relatorio(ops)}


def publico(ops):
    """So contagens, R e percentagens; nenhum preco, quantidade, identificador nem valor em dinheiro."""
    linhas = [{"corretora": o["corretora"], "estrategia": o["estrategia"], "ativo": o["ativo"], "lado": o["lado"],
               "motivo": o.get("motivo"), "dia_fecho": int(o["t_fecho"] // 86400 * 86400) if o.get("t_fecho") else None,
               "r_bruto": o["r_bruto"], "r_liquido": o["r_liquido"], "custo_r": o["custo_r"],
               "deslize_stop_r": o["deslize_stop_r"], "deslize_entrada_r": o["deslize_entrada_r"],
               "ret_preco_pct": o["ret_preco_pct"], "completa": o["completa"]} for o in ops]
    return {"operacoes": linhas, "relatorio": relatorio(ops)}


PROIBIDOS_PUBLICO = set(CAMPOS_DINHEIRO) | {"entrada", "saida", "stop", "limite", "ordId", "clOrdId", "inst", "sz",
                                            "contratos", "equity", "saldo", "t_abertura", "t_fecho"}


def sem_dinheiro(obj, caminho=""):
    """Lista de caminhos com chaves proibidas num objeto publico (vazia = seguro)."""
    maus = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PROIBIDOS_PUBLICO:
                maus.append(f"{caminho}.{k}")
            maus += sem_dinheiro(v, f"{caminho}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            maus += sem_dinheiro(v, f"{caminho}[{i}]")
    return maus


def de_bybit(reg, res):
    """Uma operacao fechada da Bybit a partir do registo do ledger e do resultado de engine/account.agregar."""
    if not res or not res.get("fechada"):
        return None
    pnl = res.get("pnl_usdc") if res.get("pnl_usdc") is not None else res.get("pnl_usdc_sem_juros")
    custos = res.get("comissoes_usdc")
    bruto = (pnl + custos) if pnl is not None and custos is not None else None
    return operacao("bybit", reg.get("strategy"), reg.get("asset"), reg.get("side") or "LONG", res.get("preco_entrada"),
                    res.get("preco_saida"), reg.get("stop"), pnl_preco=bruto, pnl_liquido=pnl,
                    comissoes=-custos if custos is not None else None, funding=None,
                    risco_dinheiro=res.get("risco_usdc"), motivo=(reg.get("reason") or "").lower() or None,
                    t_abertura=reg.get("opened_at"), t_fecho=reg.get("closed_at"))
