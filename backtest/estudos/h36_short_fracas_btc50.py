"""H36 (pre-registado 01/11/2026 a noite, pelo cacador noturno, ANTES de correr).
Hipotese: com o BTC abaixo da sua media de 50 dias (dia fechado), o dinheiro sai primeiro das altcoins fracas:
as que mais perdem contra o BTC continuam a perder (impulso relativo para baixo, menos compradores, risco de
retirada da bolsa). Short das mais fracas, saida rapida.
Diferente de: H29 (shorts por quebra/RSI de cada moeda, sem comparacao entre moedas), H17b (short das que
mais SOBEM, reversao), H35 (compra das mais fortes, com BTC > SMA50), H22 (short por funding).
Universo: ramo history + as 184 delistadas (sem vies de sobrevivencia), sem stablecoins; velas diarias feitas
das de 4H; so dias fechados; liquidez: volume medio de 30 dias >= 2 M USD; pelo menos 60 dias de historia.
Sinal no fecho do dia i (BTC fecho < SMA50): a moeda ENTRA no grupo das 3 mais fracas por RS_n =
ret_n(moeda) - ret_n(BTC) (nao estava no dia anterior) e fecha abaixo da sua SMA20.
Operacao: short na abertura do dia i+1; stop = entrada + 2 ATR14 diario (se a abertura salta o stop, sai na
abertura); sai no fecho ao fim de H dias ou no fecho do dia em que o BTC volta acima da SMA50; se a moeda deixa
de negociar, sai no ultimo fecho. Custos 0,25% + 0,10% deslize por lado; juro dos shorts 20%/ano.
Grelha (4 variantes): n em {7, 30} dias x H em {3, 10} dias.
Metades (data de entrada): M1 2021-08..2024-02, M2 2024-03..2026-10.
Contas: A = uma conta, 1 posicao com o valor todo (1x), sinais simultaneos escolhidos ao acaso (60 repeticoes,
mediana); B = todos os sinais, risco de 1% da conta por operacao (nocional ate 1x da conta por operacao).
Acaso: para cada sinal real, a mesma data com uma moeda elegivel ao acaso (regime ligado, liquidez), mesmas
saidas; 200 repeticoes.
CRITERIO (fixo, nas DUAS metades): conta A e conta B a crescer; R medio e multiplo da conta B acima do
percentil 97,5 do acaso; >= 50 operacoes; R medio > 0 sem as 5% melhores; R medio > 0 com custos a dobrar;
retorno/queda maxima da conta A melhor do que BTC comprado sempre (criterio da conta). Passa -> papel ao vivo
pela entrada no ringue; dinheiro real so com 30 operacoes em papel positivas (autorizacao do Rui).
AVISO declarado a priori: nao ha verificacao de que cada moeda (sobretudo as delistadas) tinha futuros perpetuos
para fazer short; o resultado e um limite superior nesse ponto."""
import gzip, glob, os, random, sys, numpy as np
DAY = 86400
M1 = (1627776000, 1709251199); M2 = (1709251200, 1793318399)
STABLE = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "AEUR", "EUR", "EURI", "USDP", "PAX", "UST", "USDE",
          "PYUSD", "USD1", "GUSD", "SUSD", "XUSD", "BFUSD", "RLUSD", "USDS", "WBTC", "WETH", "WBETH", "BETH", "PAXG", "XAUT"}
HIST, DEL = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("/tmp/claude-0/hist", "/tmp/claude-0/delist")
JURO = 0.20 / 365
fich = {}
for pasta in (HIST, DEL):
    for f in glob.glob(f"{pasta}/*.csv.gz"):
        a = os.path.basename(f).split(".")[0]
        if a not in STABLE and a not in fich: fich[a] = f


def diario(f):
    dias = {}
    for l in gzip.open(f, "rt").read().split():
        z = l.split(",")
        if len(z) < 6: continue
        t, o, h, lo, c, v = (float(x) for x in z[:6])
        d = int(t // DAY * DAY); q = dias.get(d)
        if q is None: dias[d] = [o, h, lo, c, v * c]
        else: q[1] = max(q[1], h); q[2] = min(q[2], lo); q[3] = c; q[4] += v * c
    ks = sorted(dias)[:-1]
    return {k: dias[k] for k in ks}


DD = {a: diario(f) for a, f in fich.items()}
DD = {a: d for a, d in DD.items() if len(d) >= 60}
T = sorted(set().union(*[set(d) for d in DD.values()]))
T = [t for t in T if t >= M1[0] - 210 * DAY]
A = sorted(DD); ia = {a: k for k, a in enumerate(A)}; it = {t: k for k, t in enumerate(T)}
O = np.full((len(A), len(T)), np.nan); H = O.copy(); L = O.copy(); C = O.copy(); V = O.copy()
for a, d in DD.items():
    for t, q in d.items():
        if t in it: j = it[t]; O[ia[a], j], H[ia[a], j], L[ia[a], j], C[ia[a], j], V[ia[a], j] = q


def media(M, n):
    out = np.full_like(M, np.nan)
    cs = np.nancumsum(np.nan_to_num(M), axis=1); cnt = np.cumsum(~np.isnan(M), axis=1)
    out[:, n:] = (cs[:, n:] - cs[:, :-n]) / n
    ok = np.zeros_like(M, bool); ok[:, n:] = (cnt[:, n:] - cnt[:, :-n]) == n
    out[~ok] = np.nan
    return out


PC = np.concatenate([C[:, :1], C[:, :-1]], axis=1)
TR = np.fmax(H, PC) - np.fmin(L, PC)
ATR, S20, S50, V30, S60 = media(TR, 14), media(C, 20), media(C, 50), media(V, 30), media(C, 60)
b = ia["BTC"]
REG = C[b] < S50[b]                       # regime no fecho do dia i
NA, NT = C.shape


def rs(n):
    R = np.full_like(C, np.nan); R[:, n:] = C[:, n:] / C[:, :-n] - 1
    return R - R[b]


def elegiveis(i):
    m = (V30[:, i] >= 2e6) & ~np.isnan(C[:, i]) & ~np.isnan(S60[:, i]) & ~np.isnan(ATR[:, i]) & ~np.isnan(S20[:, i])
    m[b] = False
    return m


ELEG = [elegiveis(i) for i in range(NT)]


def sinais(n):
    R = rs(n); out = []; prev = set()
    for i in range(60, NT - 1):
        m = ELEG[i] & ~np.isnan(R[:, i])
        cand = np.nonzero(m)[0]
        if len(cand) < 10: prev = set(); continue
        fr = set(int(x) for x in cand[np.argsort(R[cand, i])[:3]])
        if REG[i]:
            for k in fr - prev:
                if C[k, i] < S20[k, i]: out.append((i, k))
        prev = fr
    return out


def operacao(i, k, hd, custo):
    e = O[k, i + 1]
    if np.isnan(e) or e <= 0: return None
    s = e + 2 * ATR[k, i]; px = None; j = i + 1; last = j
    while j < NT:
        if np.isnan(C[k, j]): break
        last = j
        if H[k, j] >= s: px = max(s, O[k, j]); break
        if j - i >= hd or not REG[j]: px = C[k, j]; break
        j += 1
    if px is None: px = C[k, last]; j = last
    dias = j - i
    ret = (e - px) / e - custo - custo * px / e - JURO * dias
    return dict(i=i, k=k, j=j, ret=max(ret, -1.0), r=ret / ((s - e) / e))


def na_metade(ops, per): return [o for o in ops if per[0] <= T[o["i"] + 1] <= per[1]]


def conta_A(ops, rng):
    pord = {}
    for o in ops: pord.setdefault(o["i"], []).append(o)
    m = pk = 1.0; dd = 0.0; livre = -1; n = 0
    for i in sorted(pord):
        if i < livre: continue
        o = rng.choice(pord[i]); m *= 1 + o["ret"]; n += 1; livre = o["j"] + 1
        pk = max(pk, m); dd = max(dd, 1 - m / pk)
    return m, dd, n


def conta_B(ops):
    ev = sorted(ops, key=lambda o: o["i"]); eq = 1.0; pk = 1.0; dd = 0.0; abertas = []
    for o in ev:
        for a in [x for x in abertas if x[0]["j"] < o["i"] + 1]:
            eq += a[1]; abertas.remove(a); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
        dist = o["ret"] / o["r"] if o["r"] else 1.0
        noc = min(0.01 * eq / max(dist, 1e-6), eq)
        abertas.append((o, noc * o["ret"]))
    for a in sorted(abertas, key=lambda x: x[0]["j"]):
        eq += a[1]; pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
    return max(eq, 0.0), dd


def btc_hold(per):
    js = [j for j in range(NT) if per[0] <= T[j] <= per[1]]
    c = C[b, js]; pk = np.maximum.accumulate(c)
    return c[-1] / c[0], float(np.max(1 - c / pk))


def anual(m, per): return m ** (365 * DAY / (per[1] - per[0])) - 1 if m > 0 else -1.0


def corre(n, hd, linhas):
    sig = sinais(n)
    ops = [x for x in (operacao(i, k, hd, 0.0035) for i, k in sig) if x]
    ops2 = {(x["i"], x["k"]): x for x in (operacao(i, k, hd, 0.0070) for i, k in sig) if x}
    rng = random.Random(36 + n + hd)
    # acaso: mesmas datas, moeda elegivel ao acaso
    acaso = []
    for rep in range(200):
        ac = []
        for i, k in sig:
            cand = np.nonzero(ELEG[i])[0]
            x = operacao(i, int(rng.choice(list(cand))), hd, 0.0035)
            if x: ac.append(x)
        acaso.append(ac)
    passa = True
    for nome, per in (("M1", M1), ("M2", M2)):
        op = na_metade(ops, per); rr = np.array([o["r"] for o in op])
        if len(rr) == 0: linhas.append(f"  {nome}: sem operacoes"); passa = False; continue
        top = np.sort(rr)[:-max(1, int(round(0.05 * len(rr))))]
        r2 = np.mean([ops2[(o["i"], o["k"])]["r"] for o in op if (o["i"], o["k"]) in ops2])
        As = [conta_A(op, random.Random(rep)) for rep in range(60)]
        mA = float(np.median([a[0] for a in As])); ddA = float(np.median([a[1] for a in As])); nA = int(np.median([a[2] for a in As]))
        mB, ddB = conta_B(op)
        acR = [np.mean([o["r"] for o in na_metade(ac, per)]) for ac in acaso]
        acB = [conta_B(na_metade(ac, per))[0] for ac in acaso]
        pR, pB = np.percentile(acR, 97.5), np.percentile(acB, 97.5)
        mb, ddb = btc_hold(per)
        rdA = anual(mA, per) / ddA if ddA > 0 else 0; rdb = anual(mb, per) / ddb
        ok = (mA > 1 and mB > 1 and rr.mean() > pR and mB > pB and len(rr) >= 50 and top.mean() > 0 and r2 > 0 and rdA > rdb)
        passa &= ok
        linhas.append(f"  {nome}: ops {len(rr)} | R medio {rr.mean():+.3f} (acaso p97,5 {pR:+.3f}, mediana {np.median(acR):+.3f}) "
                      f"| sem top5% {top.mean():+.3f} | custos x2 {r2:+.3f} | ganhas {100*np.mean(rr>0):.0f}%")
        linhas.append(f"       conta A (1 posicao, valor todo): x{mA:.2f} ({100*anual(mA,per):+.0f}%/ano) queda {100*ddA:.0f}% ops {nA}"
                      f" | conta B (risco 1%): x{mB:.2f} queda {100*ddB:.0f}% (acaso p97,5 x{pB:.2f})")
        linhas.append(f"       BTC comprado sempre: x{mb:.2f} ({100*anual(mb,per):+.0f}%/ano) queda {100*ddb:.0f}% | ret/queda A {rdA:.2f} vs BTC {rdb:.2f} | {'OK' if ok else 'falha'}")
    return passa


if __name__ == "__main__":
    out = [f"H36 short das altcoins mais fracas contra o BTC com BTC < SMA50 | {len(A)} moedas (com delistadas)",
           f"dias com regime ligado: {int(REG.sum())} de {NT}"]
    res = {}
    for n in (7, 30):
        for hd in (3, 10):
            out.append(f"\nVariante RS{n} H{hd}d:")
            res[(n, hd)] = corre(n, hd, out)
            out.append(f"  -> {'PASSA (papel ao vivo)' if res[(n, hd)] else 'CHUMBA'}")
    out.append("\nVeredicto: " + ("PASSA: " + ", ".join(f"RS{n}_H{h}" for (n, h), v in res.items() if v) if any(res.values()) else "CHUMBA (nenhuma das 4 variantes cumpre o criterio nas duas metades)"))
    print("\n".join(out))
