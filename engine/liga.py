"""Liga semanal dos lutadores (decisao do Rui, 2026-10-13: mais competicao
no escritorio). Tudo sai do combate de hora a hora: posicao pelo R medio
nos ultimos 90 dias, subidas e descidas desde o inicio da semana, zona de
morte (perto das regras que matam) e lutador da semana. Nao mexe em nada
do que opera: so mostra."""
import datetime
from zoneinfo import ZoneInfo

from . import arena

TZ = ZoneInfo("Europe/Lisbon")


def week_of(now):
    y, w, _ = datetime.datetime.fromtimestamp(now, TZ).isocalendar()
    return f"{y}-S{w:02d}"


def danger(n, r):
    """True se esta perto de uma das regras de morte da arena."""
    if r is None:
        return False
    return ((n >= arena.FAST_N - 3 and r <= arena.FAST_R + 0.15)
            or (n >= arena.MIN_DEATH - 5 and r <= arena.DEATH_R + 0.1)
            or (n >= arena.LOSER_N - 10 and r < 0.02))


def update(state, rows, champs, now):
    alive = []
    for b in rows or []:
        f = b.get("forma") or {}
        if b.get("estado") == "MORTA" or b.get("morte"):
            continue
        alive.append((f.get("avg_r"), f.get("n") or 0, b))
    alive.sort(key=lambda x: (-(x[0] if x[0] is not None and x[1] >= 5 else -9), -x[1]))
    order = [b["id"] for _, _, b in alive]
    lg = state.setdefault("liga", {})
    wk = week_of(now)
    if lg.get("semana") != wk:
        if lg.get("semana"):
            lg["anterior"] = {"semana": lg["semana"], "final": lg.get("atual") or [],
                              "destaque": lg.get("destaque")}
        lg.update(semana=wk, inicio=order, desde=int(now))
    start = {k: i for i, k in enumerate(lg.get("inicio") or [])}
    champs = set(champs or [])
    tab = []
    for i, (r, n, b) in enumerate(alive):
        k = b["id"]
        tab.append({"id": k, "persona": b.get("persona") or arena.persona(k),
                    "nome": b.get("name"), "pos": i + 1,
                    "mov": (start[k] - i) if k in start else None,
                    "avg_r": r, "n": n, "campeao": k in champs,
                    "perigo": danger(n, r)})
    climbers = [t for t in tab if (t["mov"] or 0) > 0]
    best = max(climbers, key=lambda t: (t["mov"], t["avg_r"] or -9), default=None) or \
        next((t for t in tab if t["campeao"]), None)
    lg["atual"] = order
    lg["destaque"] = best and {"id": best["id"], "persona": best["persona"],
                               "motivo": (f"subiu {best['mov']} lugar{'es' if best['mov'] > 1 else ''}"
                                          if (best["mov"] or 0) > 0 else "lidera entre os campeões")}
    return {"semana": wk, "tabela": tab, "destaque": lg["destaque"],
            "anterior": lg.get("anterior")}


def text(lg):
    """Resumo para o Telegram (domingo a noite)."""
    if not lg or not lg.get("tabela"):
        return None
    L = [f"🏆 Liga dos lutadores — semana {lg['semana']}", ""]
    for t in lg["tabela"][:10]:
        mv = "" if t["mov"] is None else (f" ▲{t['mov']}" if t["mov"] > 0 else
                                          f" ▼{-t['mov']}" if t["mov"] < 0 else " =")
        r = "–" if t["avg_r"] is None else f"{t['avg_r']:+.2f}R"
        L.append(f"{t['pos']}. {'🏆' if t['campeao'] else '⚔️'} {t['persona']} {r} em {t['n']}{mv}"
                 + (" ⚠️ zona de morte" if t["perigo"] else ""))
    d = lg.get("destaque")
    if d:
        L += ["", f"⭐ Lutador da semana: {d['persona']} ({d['motivo']})."]
    dz = [t["persona"] for t in lg["tabela"] if t["perigo"]]
    if dz:
        L.append(f"⚠️ Em perigo de morte: {', '.join(dz)}.")
    return "\n".join(L)
