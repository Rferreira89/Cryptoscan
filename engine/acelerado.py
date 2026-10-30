"""Modo acelerado (30/10, OK do Rui: "Sim podes. Rumo ao objetivo do milhao o mais rapido possivel").

Preparado DESLIGADO. So muda alguma coisa quando as TRES condicoes se verificam:
  1. config "modo_acelerado" -> "ligado": true (OK final do Rui, dado depois da prova);
  2. a estrategia esta em config "real_autorizados" (passou o criterio unico de 28/10);
  3. a estrategia tem pelo menos "min_ops" operacoes fechadas no registo (papel ou real) e a
     media, mesmo descontando um erro-padrao, continua positiva.

O que faz: sobe o risco por operacao dessa estrategia para meio-Kelly (o tamanho que maximiza o
crescimento composto sem risco de ruina, a metade por prudencia), com teto em "teto_pct".
  Kelly para resultados em R: f* = m / E[R^2]  (fracao do capital arriscada por 1R)
  m usa o limite inferior (media - 1 erro-padrao): a estimativa e otimista por natureza.
Travao proprio: com a carteira 5% abaixo do maximo o acelerado passa a metade; a 10% desliga
(e o travao geral de engine/risco.py poe o risco reduzido). Nunca acelera com o risco reduzido
(prova por fazer, travao, 2 perdas seguidas). Nunca baixa o risco abaixo do normal.
"""
import math

from . import ledger

PADRAO = {"ligado": False, "teto_pct": 2.5, "fracao_kelly": 0.5, "min_ops": 60, "meio_dd": 0.05, "travao_dd": 0.10}


def opcoes(cfg):
    return {**PADRAO, **((cfg or {}).get("modo_acelerado") or {})}


def resultados(state, estrategia):
    """Rs das operacoes fechadas desta estrategia (registo do programa e papel ao vivo do panico)."""
    rs = []
    for r in (state or {}).get("ledger") or []:
        if r.get("strategy") != estrategia or r.get("fora_programa"):
            continue
        if r.get("status") == "CLOSED" or ledger.user_closed(r):
            R = ledger.user_r(r)
            if R is not None:
                rs.append(R)
    if estrategia == "PANICO_L10":
        rs += [x["r"] for x in ((state or {}).get("papel_panico") or {}).get("fechadas") or [] if x.get("r") is not None]
    return rs


def kelly(rs, fracao=0.5):
    """(pct do capital a arriscar por operacao, media, limite inferior) ou (None, ...) sem vantagem."""
    n = len(rs)
    if n < 2:
        return None, None, None
    m = sum(rs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (n - 1))
    lb = m - sd / math.sqrt(n)
    e2 = sum(x * x for x in rs) / n
    if lb <= 0 or e2 <= 0:
        return None, round(m, 3), round(lb, 3)
    return round(100 * fracao * lb / e2, 2), round(m, 3), round(lb, 3)


def risco_pct(estrategia, state, cfg):
    """Risco acelerado em % do capital, ou (None, motivo)."""
    o = opcoes(cfg)
    if not o["ligado"]:
        return None, "desligado"
    aut = (cfg or {}).get("real_autorizados")
    if not aut or estrategia not in aut:
        return None, "estratégia não autorizada"
    rq = (state or {}).get("risco") or {}
    if rq.get("reduzido") or (cfg or {}).get("risk_reduced"):
        return None, "risco reduzido em vigor"
    dd = rq.get("dd") or 0
    if dd >= o["travao_dd"]:
        return None, f"travão: carteira {dd:.0%} abaixo do máximo"
    rs = resultados(state, estrategia)
    if len(rs) < o["min_ops"]:
        return None, f"só {len(rs)}/{o['min_ops']} operações fechadas"
    pct, m, lb = kelly(rs, o["fracao_kelly"])
    if pct is None:
        return None, f"sem vantagem segura (média {m:+.2f}R, limite inferior {lb:+.2f}R)"
    pct = min(pct, o["teto_pct"])
    if dd >= o["meio_dd"]:
        pct /= 2
    base = (cfg or {}).get("risk_pct_of_capital") or 0
    if pct <= base:
        return None, f"meio-Kelly ({pct:.2f}%) não passa do risco normal"
    return round(pct, 2), f"meio-Kelly em {len(rs)} operações (média {m:+.2f}R)"


def cfg_para(estrategia, state, cfg):
    """cfg com o limite de perda por operacao acelerado para esta estrategia (ou o proprio cfg)."""
    pct, _ = risco_pct(estrategia, state, cfg)
    cap = (cfg or {}).get("capital_usdc")
    if pct is None or not cap:
        return cfg
    return dict(cfg, max_risk_usdc=round(cap * pct / 100, 2), acelerado_pct=pct)


def resumo(state, cfg):
    o = opcoes(cfg)
    linhas = {}
    for k in (cfg or {}).get("real_autorizados") or []:
        pct, why = risco_pct(k, state, cfg)
        linhas[k] = {"risco_pct": pct, "motivo": why}
    return {"ligado": bool(o["ligado"]), "teto_pct": o["teto_pct"], "min_ops": o["min_ops"],
            "estrategias": linhas,
            "regra": "meio-Kelly só para estratégias aprovadas, depois do OK final do Rui"}
