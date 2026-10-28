"""Copias publicas sem dinheiro (28/10, OK do Rui: o repositorio e publico).

Os ficheiros completos ficam cifrados (cofre_scan.json, cofre_state.json, cofre_audit.jsonl).
Os de sempre (scan.json, state.json, audit.jsonl) passam a ser copias com a mesma estrutura mas
sem nenhum valor que revele o dinheiro do Rui (saldos, capital, tamanhos, resultados em USDC,
depositos). Os agentes agendados (vigia, investigacao, auditoria, noticias, afinacao) continuam a
ler o que precisam: estados, sinais, precos, resultados em R, arena.
Remover a mais e aceitavel; deixar escapar um valor nao e.
"""
import re

MARCA = "_publico"

# chaves que revelam dinheiro em qualquer nivel (tamanhos, saldos, resultados em moeda)
DINHEIRO = re.compile(
    r"usdc|usd|capital|equity|pnl|saldo|lucro|qty|quantidade|valor|investido|deposit|fluxo|"
    r"pico|^g$|serie|^pts$|emprestad|collateral|borrowed|fundo|comiss|^ult$|por_confirmar|"
    r"livre|^falta|marco|multiplicar|cenarios|^reais$|preco_entrada|preco_saida",
    re.I)

SCAN_FORA = {"conta", "meta_base", "meta", "reais", "contributo", "nucleo", "evolucao", "liberdade",
             "execucao", "posmortem", "risco"}
STATE_FORA = {"capital", "capital_t", "capital_auto", "conta_livre", "conta_mov", "conta_saldos",
              "evolucao", "risco", "nucleo", "meta_base", "reconc", "saltos_avisados", "exec_abertas",
              "exec_req", "auto_ops", "chave_negociacao_expira"}


def limpar(x):
    """Copia sem as chaves de dinheiro, a qualquer profundidade."""
    if isinstance(x, dict):
        return {k: limpar(v) for k, v in x.items() if not (isinstance(k, str) and DINHEIRO.search(k))}
    if isinstance(x, list):
        return [limpar(v) for v in x]
    return x


def scan(res):
    out = limpar({k: v for k, v in (res or {}).items() if k not in SCAN_FORA})
    out[MARCA] = True
    return out


def state(st):
    out = limpar({k: v for k, v in (st or {}).items() if k not in STATE_FORA})
    out[MARCA] = True
    return out


def evento(e):
    return limpar(e)


def e_publico(obj):
    return isinstance(obj, dict) and bool(obj.get(MARCA))
