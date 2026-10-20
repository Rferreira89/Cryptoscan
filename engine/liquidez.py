"""Historico diario da liquidez da Bybit UE (Rui, 2026-10-20, contra-auditoria).

A arena julga o passado com as moedas que estao liquidas HOJE (enviesamento
de sobrevivencia). Para o corrigir e preciso saber que moedas eram
negociaveis em cada dia, e esse historico so existe a partir do dia em que se
comeca a guardar. Uma amostra por hora; ao mudar o dia, fica a mediana de
cada par (volume em USD, spread em %, fracao de amostras com preco parado).
Ficheiro liquidez.json no ramo `data`. So guarda: nao decide nada.
"""
import time

AMOSTRA_S = 3600


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def fechar_dia(hoje):
    out = {}
    for b, am in (hoje.get("amostras") or {}).items():
        out[b] = [_med([a[0] for a in am]), _med([a[1] for a in am]),
                  round(sum(1 for a in am if a[2]) / len(am), 2) if am else None]
    return out


def atualizar(hist, snap, now):
    """hist = conteudo de liquidez.json (ou {}); snap = {par: [vol, spread, parado]}."""
    hist = hist or {}
    if not snap:
        return hist
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    hoje = hist.get("hoje") or {}
    if hoje.get("dia") and hoje["dia"] != dia:
        hist.setdefault("dias", {})[hoje["dia"]] = fechar_dia(hoje)
        hoje = {}
    if not hoje:
        hoje = {"dia": dia, "amostras": {}, "ultima": 0}
    if now - (hoje.get("ultima") or 0) >= AMOSTRA_S:
        for b, v in snap.items():
            hoje["amostras"].setdefault(b, []).append(v)
        hoje["ultima"] = int(now)
    hist["hoje"] = hoje
    return hist
