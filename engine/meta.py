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
    dep = []                                  # o atalho legitimo: juntar capital todos os meses
    for r in (3, 5):
        for d in (100, 300):
            c, m = capital, 0
            while c < GOAL and m < 1200:
                c, m = c * (1 + r / 100) + d, m + 1
            dep.append((r, d, m))
    return {"capital": round(capital, 2), "depositos": dep, "pct": capital / GOAL * 100, "marco": marco,
            "falta_marco": round(marco - capital, 2), "multiplicar": round(GOAL / capital, 1),
            "base": base, "cenarios": cen,
            "marcos": [{"valor": m, "feito": capital >= m} for m in MARCOS]}


# diretrizes de toda a equipa (decisao do Rui, 2026-10-15)
def diretrizes(m):
    alvo = f"{m['marco']:,} USDC".replace(",", " ") if m else "o próximo marco"
    falta = f" (faltam {m['falta_marco']:.2f} USDC)" if m else ""
    return [
        f"O objetivo é para ser atingido: levar a carteira a {alvo}{falta}, e depois ao seguinte, até ao primeiro milhão.",
        "Só tem lugar no escritório quem é lucrativo: para entrar, bater o acaso no ringue (20 ou mais operações, resultado positivo).",
        "No dinheiro real tem de continuar lucrativo: com 10 operações reais e resultado médio negativo, perde o lugar até provar de novo.",
        "Sem atalhos: nunca mais risco para chegar mais depressa. Uma perda grande atrasa o objetivo mais do que qualquer ganho o adianta.",
        "Cada entrada passa pelo Diretor de Trading, com evidência verificável.",
    ]
