"""H32 (pre-registado 01/11, antes de correr). Pergunta do Rui: "com ordens limite se calhar estamos a perder
oportunidades". PANICO_L10 (H23) com UMA conta e o valor todo, como no dinheiro real. Mesmos dados e metades
do H23 (B1 ate set/2025, B2 out/2025-out/2026), mesma execucao L10 (limite 1% abaixo do fecho, valido 2 velas,
stop 2 ATR42, objetivo 2R, 18 velas; 0,10% maker na entrada/alvo, 0,25% no stop/tempo).
Politicas comparadas:
  A  atual: uma ordem parada de cada vez. Com ordem pendente (ate 2 velas) ou posicao aberta, os sinais novos
     ficam a espera; ao ficar livre, usa o sinal ainda valido (se houver).
  B  vigiada: todos os sinais validos sao vigiados ao mesmo tempo e o dinheiro vai para o PRIMEIRO cujo
     preco toca o limite (empate na mesma vela: escolha ao acaso). Em tempo real = ordem colocada quando o
     preco chega perto do limite, as outras ficam so vigiadas.
  M  a mercado na abertura seguinte, uma de cada vez (para comparar: nunca falha a entrada).
  T  todas as operacoes (capital infinito), referencia.
Medidas por metade: operacoes, R medio, multiplo da conta com o valor todo a 1x e a 3x (retorno da conta por
operacao = retorno no preco x alavancagem, com os custos), queda maxima a 3x.
Decisao fixa: B passa a dinheiro real so se der MAIS operacoes, R medio >= ao de A - 0,02 e multiplo a 3x
maior do que A nas DUAS metades. Caso contrario fica como esta."""
import gzip, glob, os, random, numpy as np
H4, DAY, CUT = 14400, 86400, 1759276800
HIST = "/tmp/claude-0/hist"


def load(a, f):
    r = [l.split(",") for l in gzip.open(f, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6]) if a else \
        np.array([[float(z[0]), float(z[1])] for z in r if len(z) >= 2])


def trade(d, k0, e, i, entfee):
    """Desde a vela k0 (ja com entrada e): (ret_preco_liquido, R, vela_saida)."""
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]
    n = len(c)
    stop = e - 2 * atr[i]; risk = e - stop
    alvo = e + 2 * risk; px = None; fout = 0.0025
    for j in range(k0, min(n, k0 + 18)):
        if l[j] <= stop and (j > k0 or entfee > 0.002 or o[j] > stop): px = stop; break
        if h[j] >= alvo: px, fout = alvo, (0.0010 if entfee < 0.002 else 0.0025); break
    if px is None: j = min(n - 1, k0 + 17); px = c[j]
    ret = px / e - 1 - entfee - fout * px / e
    return ret, ((px - e) - (entfee * e + fout * px)) / risk, j


dados, sinais = {}, []
for p in sorted(glob.glob(f"{HIST}/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"{HIST}/{a}.csv.gz"): continue
    x, f = load(True, f"{HIST}/{a}.csv.gz"), load(False, p)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    d = dict(t=t, o=o, h=h, l=l, c=c, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)],
             idx={int(v): k for k, v in enumerate(t)})
    dados[a] = d
    ft, fv = f[:, 0], f[:, 1]
    for i in range(18, len(c) - 2):
        if t[i] < ft[0] + 90 * DAY: continue
        k = np.searchsorted(ft, t[i] + H4, side="right") - 1
        if k < 270: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10 and d["atr"][i]:
            sinais.append((int(t[i]), a, i))
sinais.sort()
print(f"{len(dados)} moedas, {len(sinais)} sinais")


def fill(a, i, k):
    d = dados[a]; lim = d["c"][i] * 0.99
    if k < len(d["c"]) and d["l"][k] <= lim: return min(lim, d["o"][k])
    return None


def politica(nome, rng):
    """Lista de (t_sinal, ret, R) da conta unica."""
    out, livre_t = [], 0
    if nome == "T":
        for ts, a, i in sinais:
            for k in (i + 1, i + 2):
                e = fill(a, i, k)
                if e:
                    r, R, j = trade(dados[a], k, e, i, 0.0010); out.append((ts, r, R)); break
        return out
    if nome == "M":
        for ts, a, i in sinais:
            if ts + H4 < livre_t: continue
            d = dados[a]
            if i + 1 >= len(d["c"]): continue
            r, R, j = trade(d, i + 1, d["o"][i + 1], i, 0.0025); out.append((ts, r, R)); livre_t = d["t"][j] + H4
        return out
    # A e B: avancar vela a vela (4H) no tempo global
    tempos = sorted({ts + H4 * s for ts, _, _ in sinais for s in (1, 2)})
    porT = {}
    for sg in sinais:
        for s_ in (1, 2): porT.setdefault(sg[0] + H4 * s_, []).append(sg)
    validos = lambda T: porT.get(T, [])
    ordem = None                            # politica A: sinal com ordem parada
    for T in tempos:
        if T < livre_t: continue
        cand = validos(T)
        if not cand: ordem = None; continue
        if nome == "A":
            if ordem not in cand:
                ordem = rng.choice(cand)
            ts, a, i = ordem
            k = dados[a]["idx"].get(T)
            e = fill(a, i, k) if k is not None else None
            if e:
                r, R, j = trade(dados[a], k, e, i, 0.0010); out.append((ts, r, R))
                livre_t = dados[a]["t"][j] + H4; ordem = None
        else:
            toc = []
            for ts, a, i in cand:
                k = dados[a]["idx"].get(T)
                e = fill(a, i, k) if k is not None else None
                if e: toc.append((ts, a, i, k, e))
            if toc:
                ts, a, i, k, e = rng.choice(toc)
                r, R, j = trade(dados[a], k, e, i, 0.0010); out.append((ts, r, R)); livre_t = dados[a]["t"][j] + H4
    return out


def medidas(ops, lev):
    m, pk, dd = 1.0, 1.0, 0.0
    for _, r, _ in ops:
        m *= max(0.0, 1 + lev * r); pk = max(pk, m); dd = max(dd, 1 - m / pk)
    return m, dd


print("H32 PANICO_L10 com uma conta e o valor todo")
res = {}
for nome in ("A", "B", "M", "T"):
    reps = 50 if nome in ("A", "B") else 1
    for per in ("B1", "B2"):
        ns, Rs, m1, m3, dd3 = [], [], [], [], []
        for s in range(reps):
            ops = [x for x in politica(nome, random.Random(32 + s)) if (x[0] < CUT) == (per == "B1")]
            ns.append(len(ops)); Rs.append(np.mean([x[2] for x in ops]) if ops else 0)
            a1, _ = medidas(ops, 1); a3, d3 = medidas(ops, 3); m1.append(a1); m3.append(a3); dd3.append(d3)
        res[(nome, per)] = (np.mean(ns), np.mean(Rs), np.median(m1), np.median(m3), np.median(dd3))
        print(f" {nome} {per}: ops {np.mean(ns):.0f}  R medio {np.mean(Rs):+.3f}  conta x{np.median(m1):.2f} (1x)  "
              f"x{np.median(m3):.2f} (3x)  queda max 3x {100*np.median(dd3):.0f}%")
ok = all(res[("B", p)][0] > res[("A", p)][0] and res[("B", p)][1] >= res[("A", p)][1] - 0.02
         and res[("B", p)][3] > res[("A", p)][3] for p in ("B1", "B2"))
print(f"Decisao: {'B (vigiada) MELHOR nas duas metades -> propor ao Rui' if ok else 'B nao passa: fica a politica A'}")
