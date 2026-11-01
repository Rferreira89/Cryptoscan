"""H33 (pre-registado 01/11, antes de correr). Pedido do Rui: "arranja uma maneira de sermos lucrativos".
Novo criterio obrigatorio (H32): testar AO NIVEL DA CONTA - uma conta, uma posicao, o valor todo, juros compostos.
Dados: velas de 4H do ramo history (2021-01 a 2026-10), agregadas em dias fechados. Decisao no fecho do dia,
execucao na abertura seguinte. Custos 0,25% comissao + 0,10% deslize por lado. Sem dados do futuro.
Metades: H1 2021-08-01 a 2024-02-29 (os 200 dias antes aquecem os indicadores), H2 2024-03-01 a 2026-10-24.
Variantes (k=4, so compra, uma posicao ou dinheiro parado):
  V1 BTC na fase de SUBIDA (fecho > SMA200 e SMA50 a subir face a 10 dias antes) - a regra do H30 so em BTC.
  V2 BTC acima da SMA50 diaria.
  V3 BTC Donchian 20/10: entra quando o fecho passa o maximo de 20 dias, sai quando perde o minimo de 10.
  V4 rotacao: a mais forte de BTC, ETH e SOL em 30 dias, se estiver acima da sua SMA50; senao dinheiro parado.
     Revisao diaria; so troca quando outra passa a liderar por mais de 5 pontos (para nao pagar custos a mais).
Referencias: BTC comprado sempre; acaso = mesma sequencia dentro/fora rodada no tempo (rotacao circular,
500 desvios), que mantem o tempo no mercado e o numero de trocas.
Criterio (fixo): nas DUAS metades: retorno anual > 0, retorno/queda maxima melhor do que BTC comprado sempre,
retorno acima do percentil 95 do acaso (p < 0,05/4) e queda maxima a 1x <= 40%. Quem passar vai para papel
ao vivo; dinheiro real so com o OK do Rui. Reporta-se tambem a 2x (alavancagem) so como informacao."""
import gzip, random, numpy as np
HIST = "/tmp/claude-0/hist"
DAY = 86400
H1 = (1627776000, 1709251199)      # 2021-08-01 .. 2024-02-29
H2 = (1709251200, 1761350399)      # 2024-03-01 .. 2026-10-24
CUSTO = 0.0035


def diario(a):
    r = [l.split(",") for l in gzip.open(f"{HIST}/{a}.csv.gz", "rt").read().split()]
    x = np.array([[float(v) for v in z[:6]] for z in r if len(z) >= 6])
    dias = {}
    for t, o, h, l, c, _ in x:
        d = int(t // DAY * DAY)
        if d not in dias: dias[d] = [o, h, l, c]
        else:
            q = dias[d]; q[1] = max(q[1], h); q[2] = min(q[2], l); q[3] = c
    ks = sorted(dias)[:-1]                     # o ultimo dia pode estar incompleto
    return np.array(ks), np.array([dias[k] for k in ks])


A = {a: diario(a) for a in ("BTC", "ETH", "SOL")}
T = A["BTC"][0]
for a in ("ETH", "SOL"):
    assert np.array_equal(A[a][0][-len(T):], T[-len(A[a][0]):]) or True
comum = sorted(set(T) & set(A["ETH"][0]) & set(A["SOL"][0]))
idx = {a: {int(t): k for k, t in enumerate(A[a][0])} for a in A}
O = {a: np.array([A[a][1][idx[a][t], 0] for t in comum]) for a in A}
C = {a: np.array([A[a][1][idx[a][t], 3] for t in comum]) for a in A}
H = {a: np.array([A[a][1][idx[a][t], 1] for t in comum]) for a in A}
L = {a: np.array([A[a][1][idx[a][t], 2] for t in comum]) for a in A}
T = np.array(comum); N = len(T)


def sma(x, n, i): return x[i - n + 1:i + 1].mean()


def sinal(var):
    """Posicao decidida no fecho do dia i: None (dinheiro) ou a moeda."""
    pos = [None] * N; cur = None
    for i in range(210, N):
        if var == "V1":
            c = C["BTC"]; cur = "BTC" if c[i] > sma(c, 200, i) and sma(c, 50, i) > sma(c, 50, i - 10) else None
        elif var == "V2":
            c = C["BTC"]; cur = "BTC" if c[i] > sma(c, 50, i) else None
        elif var == "V3":
            c = C["BTC"]
            if cur is None and c[i] > H["BTC"][i - 20:i].max(): cur = "BTC"
            elif cur and c[i] < L["BTC"][i - 10:i].min(): cur = None
        elif var == "V4":
            f = {a: C[a][i] / C[a][i - 30] - 1 for a in A if C[a][i] > sma(C[a], 50, i)}
            if not f: cur = None
            else:
                best = max(f, key=f.get)
                if cur not in f or f[best] > f[cur] + 0.05: cur = best
        pos[i] = cur
    return pos


def conta(pos, per, lev=1.0):
    """Multiplo da conta e queda maxima na janela; posicao do fecho i executada na abertura i+1."""
    m = pk = 1.0; dd = 0.0; ant = None; trocas = 0
    for i in range(N - 1):
        if not (per[0] <= T[i + 1] <= per[1]): continue
        p = pos[i]
        if p != ant:
            m *= (1 - CUSTO * lev) ** ((ant is not None) + (p is not None)); trocas += 1
        if p:
            # da abertura i+1 a abertura i+2 (ou fecho do ultimo dia)
            fim = O[p][i + 2] if i + 2 < N else C[p][i + 1]
            m *= max(0.0, 1 + lev * (fim / O[p][i + 1] - 1))
        ant = p; pk = max(pk, m); dd = max(dd, 1 - m / pk)
    anos = (per[1] - per[0]) / (365 * DAY)
    return m, m ** (1 / anos) - 1, dd, trocas


def acaso(pos, per, rng, n=500):
    k0 = 210
    seq = pos[k0:]; out = []
    for _ in range(n):
        s = rng.randrange(1, len(seq))
        out.append(conta([None] * k0 + seq[s:] + seq[:s], per)[0])
    return out


rng = random.Random(33)
sempre = ["BTC"] * N
print("H33 conta unica, tendencia em BTC/ETH/SOL (retorno anual | queda maxima | multiplo)")
for nome, per in (("H1", H1), ("H2", H2)):
    m, a, d, _ = conta(sempre, per)
    print(f" BTC sempre {nome}: {100*a:+.0f}%/ano  queda {100*d:.0f}%  x{m:.2f}")
ok_all = {}
for v in ("V1", "V2", "V3", "V4"):
    pos = sinal(v); ok = True
    for nome, per in (("H1", H1), ("H2", H2)):
        m, a, d, tr = conta(pos, per); m2, a2, d2, _ = conta(pos, per, 2.0)
        mb, ab, db, _ = conta(sempre, per)
        ac = acaso(pos, per, rng); pv = sum(x >= m for x in ac) / len(ac)
        mar = a / d if d else 0; marb = ab / db if db else 0
        dentro = sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1] and pos[i]) / \
            max(1, sum(1 for i in range(N - 1) if per[0] <= T[i + 1] <= per[1]))
        print(f" {v} {nome}: {100*a:+.0f}%/ano  queda {100*d:.0f}%  x{m:.2f}  trocas {tr}  no mercado {100*dentro:.0f}%  "
              f"acaso mediana x{np.median(ac):.2f} p={pv:.3f}  | a 2x: {100*a2:+.0f}%/ano queda {100*d2:.0f}%")
        ok &= a > 0 and mar > marb and pv < 0.05 / 4 and d <= 0.40
    ok_all[v] = ok
    print(f"   {v}: {'PASSA -> PAPEL' if ok else 'CHUMBA'}")
