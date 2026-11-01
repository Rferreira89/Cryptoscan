"""H35 (pre-registado 01/11, antes de correr). Rui: "BTC sem alavancagem traz pouco lucro... procurar melhores
operacoes em outras moedas". Rotacao de impulso nas altcoins, AO NIVEL DA CONTA (uma posicao, valor todo).
Universo: todas as moedas do ramo history MAIS as 184 delistadas (history-delistadas), sem stablecoins - para
nao haver vies de sobrevivencia. Dias fechados a partir das velas de 4H; decisao no fecho, execucao na abertura
seguinte; custos 0,35%/lado (0,25% comissao + 0,10% deslize; altcoins pequenas podem ter mais).
Liquidez minima: volume medio de 30 dias >= 2 M USD (coluna de volume em USD do 4H x preco se preciso).
Filtro de mercado: so com BTC acima da sua media de 50 dias (H33 V2); senao USDC.
  R1 diaria: a moeda com maior retorno em 30 dias, acima da sua media de 50 dias; so troca quando outra
     passa a liderar por mais de 10 pontos ou a atual perde a media de 50 / o filtro de mercado.
  R2 semanal (segunda-feira): a de maior retorno em 7 dias, acima da media de 20 dias; fica a semana inteira
     (sai antes so se o filtro de mercado desligar).
Metades H1 2021-08..2024-02, H2 2024-03..2026-10. Referencias: BTC guardado; tendencia BTC 50 dias (H33 V2);
acaso = mesmos dias no mercado, moeda escolhida ao acaso entre as elegiveis (60 repeticoes).
Criterio fixo (k=2): nas DUAS metades, conta a crescer a 1x, acima do percentil 97,5 do acaso, e melhor
retorno/queda do que a tendencia BTC 50 dias. Se passar: papel ao vivo; dinheiro real so com o OK do Rui."""
import gzip, glob, os, random, numpy as np
DAY = 86400
H1 = (1627776000, 1709251199); H2 = (1709251200, 1761350399)
CUSTO = 0.0035
STABLE = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "AEUR", "EUR", "EURI", "USDP", "PAX", "UST", "USDE",
          "PYUSD", "USD1", "GUSD", "SUSD", "XUSD", "BFUSD", "RLUSD", "USDS", "WBTC", "WETH", "WBETH", "BETH", "PAXG", "XAUT"}
fich = {}
for pasta in ("/tmp/claude-0/hist", "/tmp/claude-0/delist"):
    for f in glob.glob(f"{pasta}/*.csv.gz"):
        a = os.path.basename(f).split(".")[0]
        if a not in STABLE and a not in fich: fich[a] = f


def diario(f):
    dias = {}
    for l in gzip.open(f, "rt").read().split():
        z = l.split(",")
        if len(z) < 6: continue
        t, o, h, lo, c, v = (float(x) for x in z[:6])
        d = int(t // DAY * DAY)
        q = dias.get(d)
        vu = v * c
        if q is None: dias[d] = [o, h, lo, c, vu]
        else: q[1] = max(q[1], h); q[2] = min(q[2], lo); q[3] = c; q[4] += vu
    ks = sorted(dias)[:-1]
    return {k: dias[k] for k in ks}


DD = {a: diario(f) for a, f in fich.items()}
DD = {a: d for a, d in DD.items() if len(d) >= 60}
T = sorted(set().union(*[set(d) for d in DD.values()]))
T = [t for t in T if t >= H1[0] - 210 * DAY]
print(f"{len(DD)} moedas (com delistadas)")
# matrizes
A = sorted(DD); ia = {a: k for k, a in enumerate(A)}; it = {t: k for k, t in enumerate(T)}
O = np.full((len(A), len(T)), np.nan); C = O.copy(); V = O.copy()
for a, d in DD.items():
    for t, q in d.items():
        if t in it: O[ia[a], it[t]], C[ia[a], it[t]], V[ia[a], it[t]] = q[0], q[3], q[4]


def media(M, n):
    out = np.full_like(M, np.nan)
    cs = np.nancumsum(np.nan_to_num(M), axis=1); cnt = np.cumsum(~np.isnan(M), axis=1)
    out[:, n:] = (cs[:, n:] - cs[:, :-n]) / n
    ok = np.zeros_like(M, bool); ok[:, n:] = (cnt[:, n:] - cnt[:, :-n]) == n
    out[~ok] = np.nan
    return out


S50, S20, V30 = media(C, 50), media(C, 20), media(V, 30)
R30 = np.full_like(C, np.nan); R30[:, 30:] = C[:, 30:] / C[:, :-30] - 1
R7 = np.full_like(C, np.nan); R7[:, 7:] = C[:, 7:] / C[:, :-7] - 1
b = ia["BTC"]
mercado = C[b] > S50[b]


def eleg(i, var):
    m = (V30[:, i] >= 2e6) & ~np.isnan(C[:, i])
    if var == "R1": m &= C[:, i] > S50[:, i]; f = R30[:, i]
    else: m &= C[:, i] > S20[:, i]; f = R7[:, i]
    m &= ~np.isnan(f)
    return m, f


def sinal(var, rng=None):
    pos = [None] * len(T); cur = None
    for i in range(60, len(T)):
        if not mercado[i]: cur = None; pos[i] = None; continue
        m, f = eleg(i, var)
        cand = np.nonzero(m)[0]
        if not len(cand): cur = None; pos[i] = None; continue
        if var == "R1":
            best = cand[np.argmax(f[cand])]
            if cur is None or not m[cur] or f[best] > f[cur] + 0.10:
                cur = int(rng.choice(list(cand))) if rng else int(best)
        else:
            if cur is not None and np.isnan(C[cur, i]): cur = None
            if cur is None or (T[i] // DAY + 3) % 7 == 0:     # segunda-feira
                cur = int(rng.choice(list(cand))) if rng else int(cand[np.argmax(f[cand])])
        pos[i] = cur
    return pos


def conta(pos, per):
    m = pk = 1.0; dd = 0.0; ant = None; tr = 0
    for i in range(len(T) - 2):
        if not (per[0] <= T[i + 1] <= per[1]): continue
        p = pos[i]
        if p != ant:
            m *= (1 - CUSTO) ** ((ant is not None) + (p is not None)); tr += 1
        if p is not None:
            a0, a1 = O[p, i + 1], O[p, i + 2]
            if np.isnan(a1): a1 = C[p, i + 1]
            if np.isnan(a1) or np.isnan(a0): a1 = a0 = 1.0          # moeda deixou de negociar: fica (raro)
            m *= max(0.0, a1 / a0)
        ant = p; pk = max(pk, m); dd = max(dd, 1 - m / pk)
    anos = (per[1] - per[0]) / (365 * DAY)
    return m, m ** (1 / anos) - 1, dd, tr


btc50 = [b if mercado[i] else None for i in range(len(T))]
for nome, per in (("H1", H1), ("H2", H2)):
    m, a, d, tr = conta(btc50, per)
    print(f" tendencia BTC 50d {nome}: {100*a:+.0f}%/ano queda {100*d:.0f}% x{m:.2f} trocas {tr}")
rng = random.Random(35)
for var in ("R1", "R2"):
    pos = sinal(var); ok = True
    for nome, per in (("H1", H1), ("H2", H2)):
        m, a, d, tr = conta(pos, per)
        ac = [conta(sinal(var, random.Random(rng.random())), per)[0] for _ in range(60)]
        pv = sum(x >= m for x in ac) / len(ac)
        mb, ab, db, _ = conta(btc50, per)
        print(f" {var} {nome}: {100*a:+.0f}%/ano queda {100*d:.0f}% x{m:.2f} trocas {tr} | acaso mediana x{np.median(ac):.2f} p={pv:.3f}")
        ok &= m > 1 and pv < 0.025 and (a / d if d else 0) > (ab / db if db else 0)
    print(f"   {var}: {'PASSA -> PAPEL' if ok else 'CHUMBA'}")
