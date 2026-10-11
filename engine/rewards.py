"""Recompensas do escritorio (decisao do Rui, 2026-10-11).

Cada conquista REAL desbloqueia um espaco novo no escritorio 3D. So conta
o que aconteceu de verdade (operacoes executadas pelo Rui, a arena, o
capital); nada e desbloqueado por promessas ou simulacoes. Uma conquista
desbloqueada fica para sempre (guardada no estado com a data) e da um
aviso no Telegram.
"""
import time

from . import ledger

# (id, espaco desbloqueado, condicao em texto)
ITEMS = [
    ("WIN1", "Mesa de bilhar", "a primeira operação tua fechada com lucro"),
    ("WIN3", "Bar no terraço", "3 operações tuas fechadas com lucro"),
    ("PEAK", "Troféu dourado", "o capital acima do valor de partida"),
    ("WEEK", "Máquina de arcade", "uma semana positiva (2 ou mais operações tuas)"),
    ("ARENA", "Hall da Fama", "um analista da arena ganhar o direito a dinheiro real"),
]


def _mine(led):
    return [r for r in led if r.get("executed") is True
            and r.get("status") == "CLOSED"]


def check(state, result, now):
    """{id: True/False} das condicoes neste momento."""
    led = state.get("ledger", [])
    mine = _mine(led)
    wins = sum(1 for r in mine if (ledger.user_r(r) or 0) > 0)
    week = [r for r in mine if (r.get("closed_at") or 0) >= now - 7 * 86400]
    week_r = sum(ledger.user_r(r) or 0 for r in week)
    cfg = result.get("config") or {}
    cap, base = cfg.get("capital_usdc"), cfg.get("capital_base")
    board = (result.get("arena") or {}).get("classificacao") or []
    return {"WIN1": wins >= 1, "WIN3": wins >= 3,
            "PEAK": bool(cap and base and cap > base),
            "WEEK": len(week) >= 2 and week_r > 0,
            "ARENA": any(b.get("estado") == "SOBE" for b in board)}


def update(state, result, now=None):
    """Devolve (lista para a pagina, eventos de desbloqueio)."""
    now = int(now or time.time())
    got = state.setdefault("rewards", {})
    ok = check(state, result, now)
    ev, out = [], []
    for rid, name, cond in ITEMS:
        if ok.get(rid) and rid not in got:
            got[rid] = now
            ev.append({"t": now, "event": "REWARD", "id": f"reward-{rid}",
                       "name": name, "cond": cond, "real": False})
        out.append({"id": rid, "name": name, "cond": cond,
                    "unlocked": rid in got, "at": got.get(rid)})
    return out, ev
