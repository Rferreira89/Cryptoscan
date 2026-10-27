"""H19 (pre-registado a 27/10, antes de correr): carteiras semanais/diarias em spot, so compras.
Universo: as 25 moedas mais liquidas do historico (vies de sobrevivencia: moedas listadas hoje).
Custos 0,35% por lado sobre o valor trocado. Periodos A jun 2021-mai 2024, B jun 2024-out 2026.
  REF_BTC   BTC comprado e guardado
  REF_CAB   cabaz das 25 em pesos iguais (rebalanceado semanalmente)
  NUCLEO    BTC/ETH/SOL, cada um 1/3 so com fecho diario acima da media de 200 dias (regra atual)
  MOM3      segunda-feira: com o BTC acima da media de 200 dias, as 3 com maior retorno de 28 dias; 7 dias
  MOM5_56   igual, 5 moedas, retorno de 56 dias
  MISTO     70% NUCLEO + 30% MOM3
Criterio (antes de ver): positivo nos DOIS periodos e Sharpe semanal >= ao do BTC guardado nos dois.
"""
import gzip, glob, os, sys, math, statistics as S
sys.path.insert(0, "/home/claude/cryptoscan")
from engine import backtest as B
DAY = 86400
A0, A1, B1 = 1622505600, 1717200000, 1792022400
C = 0.0035
def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]
vol, C4 = {}, {}
for p in glob.glob("/tmp/claude-0/hist/*.csv.gz"):
    a = os.path.basename(p).split(".")[0]; c = load(p); C4[a] = c; vol[a] = sum(x["v"] * x["c"] for x in c[-180 * 6:])
moedas = sorted(vol, key=lambda a: -vol[a])[:25]
for m in ("BTC", "ETH", "SOL"):
    if m not in moedas: moedas.append(m)
D = {a: {x["t"] // DAY: x["c"] for x in B.daily(C4[a])} for a in moedas}
dias = sorted(D["BTC"])
fimd = min(B1 // DAY, dias[-1])
def sma(a, d, n):
    xs = [D[a].get(k) for k in range(d - n + 1, d + 1)]
    return None if any(x is None for x in xs) else sum(xs) / n
def ret(a, d, n):
    x0, x1 = D[a].get(d - n), D[a].get(d)
    return None if not x0 or not x1 else x1 / x0 - 1
def pesos(nome, d, ant):
    """pesos alvo decididos com o fecho do dia d (aplicados no dia seguinte)"""
    btc_up = (sma("BTC", d, 200) or 1e18) < D["BTC"][d]
    if nome == "REF_BTC": return {"BTC": 1.0}
    seg = (d + 4) % 7 == 0         # 01/01/1970 foi quinta: (d+4)%7==0 -> segunda
    if nome == "REF_CAB":
        if not seg and ant: return ant
        v = [a for a in moedas if D[a].get(d)]; return {a: 1 / len(v) for a in v}
    if nome == "NUCLEO":
        return {a: 1 / 3 for a in ("BTC", "ETH", "SOL") if D[a].get(d) and (sma(a, d, 200) or 1e18) < D[a][d]}
    if nome in ("MOM3", "MOM5_56"):
        if not seg and ant is not None: return ant
        if not btc_up: return {}
        k, n = (3, 28) if nome == "MOM3" else (5, 56)
        rk = sorted([(ret(a, d, n), a) for a in moedas if ret(a, d, n) is not None], reverse=True)[:k]
        return {a: 1 / k for _, a in rk}
    if nome == "MISTO":
        nu, mo = pesos("NUCLEO", d, None), pesos("MOM3", d, ant.get("_mo") if ant else None)
        w = {}
        for a, x in nu.items(): w[a] = w.get(a, 0) + 0.7 * x
        for a, x in mo.items(): w[a] = w.get(a, 0) + 0.3 * x
        w["_mo"] = mo; return w
def corre(nome, d0, d1):
    v, w, serie = 1.0, None, []
    for d in range(d0, d1):
        if d not in D["BTC"] or d + 1 not in D["BTC"]: continue
        alvo = pesos(nome, d, w)
        a_l = {k: x for k, x in alvo.items() if k != "_mo"}
        w_l = {k: x for k, x in (w or {}).items() if k != "_mo"}
        troca = sum(abs(a_l.get(k, 0) - w_l.get(k, 0)) for k in set(a_l) | set(w_l))
        v *= 1 - C * troca
        g = sum(x * ((D[k].get(d + 1) or D[k][d]) / D[k][d] - 1) for k, x in a_l.items() if D[k].get(d))
        v *= 1 + g
        # pesos derivam com os precos
        if a_l:
            tot = sum(x * (D[k].get(d + 1) or D[k][d]) / D[k][d] for k, x in a_l.items()) + (1 - sum(a_l.values()))
            novo = {k: x * (D[k].get(d + 1) or D[k][d]) / D[k][d] / tot for k, x in a_l.items()}
            if "_mo" in alvo: novo["_mo"] = alvo["_mo"]
            w = novo
        else: w = alvo
        serie.append((d, v))
    return serie
def stats(serie):
    v = [x[1] for x in serie]; tot = v[-1] / v[0] - 1; anos = (serie[-1][0] - serie[0][0]) / 365.25
    cagr = (v[-1] / v[0]) ** (1 / anos) - 1
    pk, dd = v[0], 0
    for x in v: pk = max(pk, x); dd = max(dd, 1 - x / pk)
    sem = [v[i] / v[i - 7] - 1 for i in range(7, len(v), 7)]
    sh = S.mean(sem) / S.pstdev(sem) * math.sqrt(52) if S.pstdev(sem) else 0
    return tot, cagr, dd, sh
print(f"Universo: {len(moedas)} moedas. Dados até {__import__('time').strftime('%d/%m/%Y', __import__('time').gmtime(fimd*DAY))}")
res = {}
for per, d0, d1 in (("A jun2021-mai2024", A0 // DAY, A1 // DAY), ("B jun2024-out2026", A1 // DAY, fimd)):
    print(per)
    for nome in ("REF_BTC", "REF_CAB", "NUCLEO", "MOM3", "MOM5_56", "MISTO"):
        s = corre(nome, d0, d1); t, c, dd, sh = stats(s); res[(per, nome)] = (t, sh)
        print(f"   {nome:<9} total {t*100:+8.1f}%  por ano {c*100:+7.1f}%  queda máx {dd*100:5.1f}%  Sharpe {sh:5.2f}")
pers = ("A jun2021-mai2024", "B jun2024-out2026")
for nome in ("NUCLEO", "MOM3", "MOM5_56", "MISTO"):
    ok = all(res[(p, nome)][0] > 0 and res[(p, nome)][1] >= res[(p, "REF_BTC")][1] for p in pers)
    print(nome, "PASSA" if ok else "CHUMBA")
