"""Selecao simples por regime para papel (investigacao-agressivo).

Nao substitui o motor real. Apenas ajuda a priorizar em papel:
- subida / bull: preferir LONG
- descida / bear: preferir SHORT
- lateral / range: ambos
- desconhecido: ambos

Nao altera risco, capital nem producao.
"""

def prefer(fase, side):
    """Devolve True se o lado e adequado ao regime (ou se regime desconhecido)."""
    if not fase:
        return True
    f = str(fase).lower()
    s = (side or "LONG").upper()
    if any(x in f for x in ("subida", "bull", "alta", "up")):
        return s == "LONG"
    if any(x in f for x in ("descida", "bear", "baixa", "down")):
        return s == "SHORT"
    return True  # lateral, range, desconhecido: ambos
