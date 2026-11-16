"""Piloto experimental TURTLE LONG (autorizacao Rui, 2026-11-16).

Mesma logica nas duas exchanges: rompimento do maximo de 20 dias.
Limites do piloto (mais restritivos que os globais):
- risco maximo 0,5% do capital da conta por operacao
- 1 posicao simultanea por exchange
- suspensao se acumular -3R no piloto
- so instrumentos negociaveis em real (nao acoes/metais informativos)
- nao aumenta capital, alavancagem nem limites globais

Nao abre ordens por si. O executor real so usa isto se a sizing
confirmar que o risco real da ordem minima fica <= 0,5%.
Se a ordem minima ultrapassar 0,5%, a exchange e recusada.
"""

NOME = "TURTLE"
RISCO_MAX_PCT = 0.5
MAX_POS_POR_EXCHANGE = 1
PERDA_MAX_R = -3.0
EXCHANGES = ("Bybit EU", "OKX")


def pode_abrir(ops_piloto, exchange, risco_real_pct):
    """Devolve (ok, motivo).
    ops_piloto: lista de dicts com keys exchange, r, aberto.
    """
    if exchange not in EXCHANGES:
        return False, f"exchange {exchange} nao autorizada neste piloto"
    abertas = sum(1 for o in ops_piloto or []
                  if o.get("exchange") == exchange and o.get("aberto"))
    if abertas >= MAX_POS_POR_EXCHANGE:
        return False, f"ja ha {abertas} posicao aberta em {exchange}"
    soma = sum(float(o.get("r") or 0) for o in ops_piloto or [])
    if soma <= PERDA_MAX_R:
        return False, f"piloto suspenso: {soma:+.2f}R (limite {PERDA_MAX_R}R)"
    if risco_real_pct is None or risco_real_pct > RISCO_MAX_PCT + 1e-9:
        return False, f"risco real {risco_real_pct}% ultrapassa o teto {RISCO_MAX_PCT}%"
    return True, "ok"


def resumo(ops_piloto):
    """Agrega e separa por exchange."""
    out = {"total": {"n": 0, "soma_r": 0.0}, "por_exchange": {}}
    for e in EXCHANGES:
        out["por_exchange"][e] = {"n": 0, "soma_r": 0.0, "abertas": 0}
    for o in ops_piloto or []:
        e = o.get("exchange")
        if e not in out["por_exchange"]:
            continue
        r = float(o.get("r") or 0)
        out["total"]["n"] += 1
        out["total"]["soma_r"] = round(out["total"]["soma_r"] + r, 3)
        out["por_exchange"][e]["n"] += 1
        out["por_exchange"][e]["soma_r"] = round(out["por_exchange"][e]["soma_r"] + r, 3)
        if o.get("aberto"):
            out["por_exchange"][e]["abertas"] += 1
    return out
