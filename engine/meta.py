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
        "Cada um paga as suas contas: comissões, deslize e spread real. Quem nos últimos 30 dias não as paga com o que ganha perde o lugar no dinheiro real; quem continua sem pagar morre na arena.",
        "Cada entrada passa pelo Diretor de Trading, com evidência verificável.",
        "Máximo empenho em cada operação: proteger o lucro logo que aparece (TP1) e nunca deixar um ganho virar perda.",
        "Trabalhar como se a vida dependesse disso: rigor total em cada entrada, cada stop e cada saída — e, por isso mesmo, nunca uma aposta maior. Sobrevive quem não perde o capital.",
    ]


# codigo de conduta: a forma de pensar da equipa (decisao do Rui, 2026-10-16).
# Cada principio esta ligado a regras que o programa cumpre (nao e so texto).
CODIGO = [
    ("Primeiro proteger, depois ganhar",
     "Stop antes de entrar, risco sempre igual e pequeno; depois do TP1 a operação já não pode dar perda."),
    ("Pensar em probabilidades, não em certezas",
     "Nem sempre se acerta, e isso faz parte; mas a missão é multiplicar o capital sem o perder: "
     "perdas pequenas e raras, ganhos maiores e protegidos. Contam 100 operações, não uma."),
    ("Só entrar com vantagem provada",
     "Sem palpites: só campeões que batem o acaso, com evidência verificável e histórico positivo nesta fase do mercado."),
    ("Paciência: esperar pela bola certa",
     "Entra-se quando o gatilho vira, nunca enquanto o preço cai. Ficar parado também é uma decisão."),
    ("Cortar as perdas depressa, deixar os ganhos correr",
     "O stop sai sem discussão; depois do TP1 o resto segue para o objetivo final."),
    ("Humildade: o mercado muda",
     "Quem perde a forma sai do ringue; quem não é lucrativo no dinheiro real perde o lugar."),
    ("Aprender com cada operação",
     "Quem acerta, o que o Diretor rejeitou e porquê, e as lições de cada semana."),
    ("Disciplina acima da emoção",
     "Nada de vingança depois de perder nem de euforia depois de ganhar; nunca mais risco para recuperar."),
]


def codigo():
    return [{"n": i + 1, "titulo": t, "texto": x} for i, (t, x) in enumerate(CODIGO)]
