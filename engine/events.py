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


def next_event(now):
    return next(({"name": n, "t": t} for n, t in ALL if t >= now), None)


def block(now):
    """Evento em curso: de 12h antes ate 2h depois. None se nao houver."""
    for n, t in ALL:
        if t - BEFORE_H * 3600 <= now <= t + AFTER_H * 3600:
            return {"name": n, "t": t}
    return None


def stale(now):
    """True se ja nao ha CPI agendado nos proximos 45 dias."""
    last_cpi = _ts(CPI[-1], 8, 30)
    return now > last_cpi - 5 * 86400 and not any(
        "CPI" in n and now <= t <= now + 45 * 86400 for n, t in ALL)
