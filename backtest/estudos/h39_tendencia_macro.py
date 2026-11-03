"""H39 (pre-registado 03/11, antes de correr). Pedido do Rui: estrategia para a OKX (futuros: cripto, acoes,
ouro, petroleo) com LONGS e SHORTS e alavancagem ate 10x. Teste da regra classica de seguir a tendencia
(comprado acima da media, VENDIDO abaixo) ao nivel da conta, com os dados publicos disponiveis aqui
(datasets do GitHub): petroleo WTI e Brent diarios (desde 1986/1987), ouro e S&P 500 mensais.
Custos: 0,10% por lado (0,05% taker + 0,05% deslize) e financiamento estimado de 5%/ano contra a posicao.
Variantes: diarias medias de 50 e 200 dias; mensais media de 10 meses. Alavancagem 1x, 2x, 3x, 5x, 10x.
Metades: diarios 2000-2012 e 2013-2026; mensais 1975-1999 e 2000-2026.
Referencia: comprar e guardar. Criterio: conta a crescer nas DUAS metades e queda maxima <= 50% para a
alavancagem ser considerada aceitavel. So informa: nada liga ao vivo sem papel e OK do Rui."""
import csv, math
D = "backtest/dados_externos/"
def serie(f, col=1):
    out = []
    for r in list(csv.reader(open(D + f)))[1:]:
        try: out.append((r[0], float(r[col])))
        except (ValueError, IndexError): pass
    return [x for x in out if x[1] > 0]
def conta(s, n, ini, fim, lev, por_ano, short=True):
    m = pk = 1.0; dd = 0.0; ant = 0; anos = 0
    px = [p for _, p in s]
    for i in range(n, len(s) - 1):
        d = s[i + 1][0]
        if not (ini <= d < fim): continue
        sma = sum(px[i - n + 1:i + 1]) / n
        pos = 1 if px[i] > sma else (-1 if short else 0)
        if pos != ant: m *= 1 - 0.001 * lev * abs(pos - ant)
        ret = px[i + 1] / px[i] - 1
        m *= max(0.0, 1 + lev * pos * ret - (0.05 / por_ano) * lev * abs(pos))
        ant = pos; pk = max(pk, m); dd = max(dd, 1 - m / pk); anos += 1 / por_ano
        if m <= 0: break
    return (m ** (1 / anos) - 1 if m > 0 and anos else -1.0), dd
def guardar(s, ini, fim, por_ano):
    v = [p for d, p in s if ini <= d < fim]; anos = len(v) / por_ano
    return (v[-1] / v[0]) ** (1 / anos) - 1
casos = [("WTI diario", serie("oil-prices_main_data_wti-daily.csv"), (50, 200), 252, ("2000", "2013", "2026-12")),
         ("Brent diario", serie("oil-prices_main_data_brent-daily.csv"), (50, 200), 252, ("2000", "2013", "2026-12")),
         ("Ouro mensal", serie("gold-prices_main_data_monthly.csv"), (10,), 12, ("1975", "2000", "2026-12")),
         ("S&P 500 mensal", serie("s-and-p-500_main_data_data.csv"), (10,), 12, ("1975", "2000", "2026-12"))]
print("H39 tendencia com longs e shorts (retorno anual | queda maxima)")
for nome, s, ns, pa, (a, b, c) in casos:
    print(f"{nome}: guardar {100*guardar(s, a, b, pa):+.0f}%/ano | {100*guardar(s, b, c, pa):+.0f}%/ano  (ultimo {s[-1][0]})")
    for n in ns:
        for short in (True, False):
            linha = []
            for lev in (1, 2, 3, 5, 10):
                r1, d1 = conta(s, n, a, b, lev, pa, short); r2, d2 = conta(s, n, b, c, lev, pa, short)
                linha.append(f"{lev}x {100*r1:+.0f}%/{100*r2:+.0f}% q{100*max(d1,d2):.0f}%")
            print(f"   media {n} {'long+short' if short else 'so long  '}: " + " | ".join(linha))
