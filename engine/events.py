"""Calendario de eventos de risco (News / Event Risk).

Datas oficiais, hora de Nova Iorque:
- FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm (decisao as
  14:00 do segundo dia)
- CPI: bls.gov/schedule/news_release/cpi.htm (08:30)
Consultadas em 2026-10-02. O PCE e os desbloqueios de tokens nao estao
incluidos: nao ha fonte gratuita fiavel. O calendario tem de ser
atualizado quando o BLS publicar as datas de 2027; ate la o sistema avisa
que esta desatualizado em vez de assumir que nao ha eventos.
"""
import datetime
import json
import os
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
FOMC = ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28",
        "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"]
CPI = ["2026-10-14", "2026-11-10", "2026-12-10"]
BEFORE_H, AFTER_H = 12, 2


def _ts(day, hh, mm):
    y, m, d = map(int, day.split("-"))
    return int(datetime.datetime(y, m, d, hh, mm, tzinfo=NY).timestamp())


ALL = sorted([("Decisão da Fed (FOMC)", _ts(d, 14, 0)) for d in FOMC]
             + [("Inflação dos EUA (CPI)", _ts(d, 8, 30)) for d in CPI],
             key=lambda e: e[1])


EXTRA_PATH = os.path.join(os.path.dirname(__file__), "events_extra.json")


def load_extra(path=None):
    """Eventos adicionais mantidos pelo agente de noticias (PCE, grandes
    desbloqueios de tokens, incidentes). Formato:
      {"updated": "AAAA-MM-DD", "events": [
         {"name": "...", "t": 1790000000, "assets": ["ALL"] ou ["SUI"],
          "before_h": 12, "source": "https://..."}]}
    Entradas mal formadas sao ignoradas: so pode tornar o sistema mais
    prudente, nunca o pode partir."""
    try:
        with open(path or EXTRA_PATH) as f:
            raw = json.load(f).get("events", [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for e in raw if isinstance(raw, list) else []:
        try:
            name, t = str(e["name"])[:80], int(e["t"])
            assets = [str(a).upper() for a in e.get("assets", ["ALL"])][:60]
            before = min(72, max(1, int(e.get("before_h", BEFORE_H))))
        except (KeyError, TypeError, ValueError):
            continue
        if name and t > 1_600_000_000 and assets:
            out.append({"name": name, "t": t, "assets": assets,
                        "before_h": before})
    return out


def _all(extra=None):
    ev = [{"name": n, "t": t, "assets": ["ALL"], "before_h": BEFORE_H}
          for n, t in ALL]
    return sorted(ev + (load_extra() if extra is None else extra),
                  key=lambda e: e["t"])


def next_event(now, extra=None):
    return next(({"name": e["name"], "t": e["t"]} for e in _all(extra)
                 if e["t"] >= now and "ALL" in e["assets"]), None)


def block(now, asset=None, extra=None):
    """Evento em curso para o mercado todo ou para um ativo. None se nao."""
    for e in _all(extra):
        if e["t"] - e["before_h"] * 3600 <= now <= e["t"] + AFTER_H * 3600 and \
                ("ALL" in e["assets"] or (asset and asset.upper() in e["assets"])):
            return {"name": e["name"], "t": e["t"]}
    return None


def stale(now):
    """True se ja nao ha CPI agendado nos proximos 45 dias."""
    last_cpi = _ts(CPI[-1], 8, 30)
    return now > last_cpi - 5 * 86400 and not any(
        "CPI" in n and now <= t <= now + 45 * 86400 for n, t in ALL)


def open_warnings(state, now, extra=None):
    """Aviso unico quando comeca a janela de risco de um evento especifico de
    um ativo (desbloqueio de tokens, incidente) e ha uma operacao ABERTA e
    executada nesse ativo. So informa: nao mexe no stop nem na posicao."""
    seen = state.setdefault("event_warned", {})
    for k in [k for k, t in seen.items() if now - t > 14 * 86400]:
        del seen[k]
    out = []
    evs = [e for e in _all(extra) if "ALL" not in e["assets"]
           and e["t"] - e["before_h"] * 3600 <= now <= e["t"]]
    for r in state.get("ledger", []):
        if r.get("status") != "OPEN" or r.get("executed") is not True:
            continue
        for e in evs:
            if r.get("asset", "").upper() not in e["assets"]:
                continue
            key = f"{r['id']}|{e['t']}"
            if key in seen:
                continue
            seen[key] = now
            out.append({"t": now, "event": "EVENT_OPEN", "id": r["id"],
                        "asset": r["asset"], "name": e["name"],
                        "event_t": e["t"], "stop": r.get("stop")})
    return out
