"""Meta do Rui (2026-10-14): levar o capital ao primeiro milhão.

So mostra o caminho com matematica honesta (crescimento composto) e os
marcos intermedios. Nao mexe no risco: a meta persegue-se com disciplina,
nunca com apostas maiores."""
import math

GOAL = 1_000_000
MARCOS = [100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000,
          250_000, 500_000, 1_000_000]


def progress(base, capital):
    if not capital or capital <= 0:
        return None
    marco = next((m for m in MARCOS if m > capital), GOAL)
    cen = []
    for r in (3, 5, 8, 10, 15):
        meses = math.log(GOAL / capital) / math.log(1 + r / 100) if capital < GOAL else 0
        cen.append((r, meses))
    return {"capital": round(capital, 2), "pct": capital / GOAL * 100, "marco": marco,
            "falta_marco": round(marco - capital, 2), "multiplicar": round(GOAL / capital, 1),
            "base": base, "cenarios": cen,
            "marcos": [{"valor": m, "feito": capital >= m} for m in MARCOS]}
