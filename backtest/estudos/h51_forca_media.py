"""H51 (pre-registado 05/11 23:50, antes de correr). Dia impar: LONG em mercado a SUBIR ou LATERAL (BTC acima da media).
Logica economica: com o mercado acima da media de ~50 dias o dinheiro novo concentra-se nas moedas que lideram contra o
BTC (narrativa, fluxo de fundos); o impulso transversal persiste semanas. Comprar a quebra ja chumbou (H35, H41, TURTLE)
porque paga o pico e o deslize. Aqui a ordem de compra fica PARADA na media curta (20 velas de 4H, ~3 dias) a espera de
um recuo de quem realiza lucro (maker, 0,02%), e a saida e rapida. Espelho long da H48, no regime oposto.
Diferente da H46 (RSI<30 em qualquer moeda em tendencia: aqui a SELECAO e transversal pela forca contra o BTC e a entrada
e na media curta), H35 (rotacao com o valor todo na lider, entrada a mercado), H37 (recuos do BTC), H41 (quebras).
Universo: 69 moedas do ramo history + 186 retiradas (history-delistadas), sem estaveis; liquidez: volume das ultimas
6 velas >= 2 M USD. Periodo: velas de 4H 2021-01..2026-11 (o financiamento nao entra no sinal).
Regime (vela de 4H fechada): BTC acima da media de 300 velas (~50 dias) - subida ou lateral acima da media.
Forca: retorno de 30 dias (180 velas) da moeda menos o do BTC; a moeda tem de estar no topo Q da ordenacao entre as
moedas elegiveis nessa vela; e o fecho tem de estar pelo menos 2% acima da media de 20 velas (esticada).
Long: ordem limite na media de 20 velas (valor da vela do sinal), valida 6 velas (24 h); stop 2xATR42 abaixo da entrada.
Custos OKX futuros: 0,02% na entrada limite e no objetivo; 0,10% no stop e na saida por tempo; financiamento estimado
0,01%/8h CONTRA o long (conservador). Moeda que sai da bolsa com a posicao aberta: sai no ultimo fecho a 0,10%.
Variantes (k=4): Q in {10%, 20%} x saida in {2R/72h, 1R/36h (saida rapida)}.
Criterio da conta (fixo): conta de 20 USD, risco 2% por operacao com todos os sinais (teto 10x de exposicao) E uma
posicao com o valor todo (1x); a conta tem de crescer nas DUAS metades (2021-01..2023-10 e 2023-11..2026) nas duas
politicas, acima do percentil 97,5 do acaso (mesmas horas, moeda ao acaso do universo elegivel em regime, long na
abertura seguinte com o mesmo stop/objetivo/custos, 200 sorteios), >= 50 operacoes por metade, R medio > 0 sem as 5%
melhores operacoes e com custos a dobrar. Mede as operacoes em dias sem sinal da H40 (BTC -3% em 6 velas = proxy)."""
import gzip, glob, os, json, numpy as np
H4, DAY = 14400, 86400
CUT2 = 1698796800
HIST, HDEL = "/home/claude/hist", "/home/claude/hdel"
ESTAVEIS = {"AEUR", "EUR", "EURI", "FDUSD", "TUSD", "USDC", "BUSD", "USDP", "PAX", "DAI", "UST", "USTC", "SUSD", "PAXG",
            "XUSD", "USD1", "BFUSD", "WBTC", "WBETH", "BETH", "RLUSD", "USDE", "GBP", "AUD", "TRY", "BRL"}
rng = np.random.default_rng(51)


def load(f):
    r = [l.split(",") for l in gzip.open(f, "rt").read().split()]
    return np.array([[float(x) for x in z[:6]] for z in r if len(z) >= 6])


files = {os.path.basename(p)[:-7]: p for p in glob.glob(f"{HDEL}/*.csv.gz")}
files.update({os.path.basename(p)[:-7]: p for p in glob.glob(f"{HIST}/*.csv.gz")})
B = load(files.pop("BTC")); T = B[:, 0].astype(np.int64); NT = len(T); tix = {int(v): k for k, v in enumerate(T)}
M = {}
for a, p in sorted(files.items()):
    if a in ESTAVEIS: continue
    x = load(p)
    if len(x) < 400: continue
    lr = np.diff(np.log(x[:, 4]))
    if np.std(lr) < 0.004: continue                       # estavel / indexada
    arr = np.full((NT, 5), np.nan)
    for row in x:
        k = tix.get(int(row[0]))
        if k is not None: arr[k] = row[1:6]
    M[a] = arr
A = sorted(M); NA = len(A)
O = np.stack([M[a][:, 0] for a in A], 1); Hh = np.stack([M[a][:, 1] for a in A], 1)
L = np.stack([M[a][:, 2] for a in A], 1); C = np.stack([M[a][:, 3] for a in A], 1)
V = np.stack([M[a][:, 4] for a in A], 1) * C
print(f"{NA} moedas (com retiradas), {NT} velas de 4H", flush=True)


def roll_mean(x, n):
    o = np.full_like(x, np.nan); cs = np.nancumsum(np.r_[np.zeros((1,) + x.shape[1:]), np.nan_to_num(x)], 0)
    cnt = np.cumsum(np.r_[np.zeros((1,) + x.shape[1:]), ~np.isnan(x)], 0)
    s = cs[n:] - cs[:-n]; c = cnt[n:] - cnt[:-n]
    o[n - 1:] = np.where(c == n, s / n, np.nan); return o


bc = B[:, 4]; bs = roll_mean(bc[:, None], 300)[:, 0]
regime = np.zeros(NT, bool); regime[360:] = bc[360:] > bs[360:]
h40p = np.zeros(NT, bool); h40p[6:] = bc[6:] / bc[:-6] - 1 <= -0.03
dia_h40 = {int(T[k]) // DAY for k in np.where(h40p)[0]}
S20 = roll_mean(C, 20)
pc = np.vstack([C[:1], C[:-1]]); TR = np.fmax(Hh, pc) - np.fmin(L, pc)
ATR = roll_mean(TR, 42)
VOL6 = roll_mean(V, 6) * 6
rel = np.full((NT, NA), np.nan); rel[180:] = np.log(C[180:] / C[:-180]) - np.log(bc[180:] / bc[:-180])[:, None]
eleg = ~np.isnan(rel) & (VOL6 >= 2e6) & ~np.isnan(ATR) & ~np.isnan(S20)
rank = np.full((NT, NA), np.nan)
for k in np.where(regime)[0]:
    e = eleg[k]
    if e.sum() < 10: continue
    r = rel[k, e]; rank[k, np.where(e)[0]] = (np.argsort(np.argsort(-r)) + 0.5) / len(r)
ultima = np.array([np.max(np.where(~np.isnan(C[:, j]))[0]) for j in range(NA)])
print(f"velas em regime BTC acima da media: {regime.sum()} ({100*regime.mean():.0f}%)", flush=True)


def trade(j, k0, e, i, nR, nmax, cm=1.0):
    """Long desde a vela k0 (entrada e na vela k0). Devolve (ret liquido no preco, R, vela de saida)."""
    stop = e - 2 * ATR[i, j]; risk = e - stop; alvo = e + nR * risk; fout = 0.0010 * cm; px = None
    fim = min(ultima[j], k0 + nmax - 1)
    for q in range(k0, fim + 1):
        if L[q, j] <= stop: px = min(stop, O[q, j]) if q > k0 else stop; break
        if q > k0 and Hh[q, j] >= alvo: px, fout = max(alvo, O[q, j]), 0.0002 * cm; break
    if px is None:
        q = fim
        while np.isnan(C[q, j]) and q > k0: q -= 1     # buraco nos dados: ultimo fecho conhecido
        px = C[q, j] if not np.isnan(C[q, j]) else e
    fund = 0.0001 * cm * (q - k0 + 1) * 4 / 8
    ret = (px - e) / e - 0.0002 * cm - fout * px / e - fund
    return ret, ret * e / risk, q


def gerar(Q, nR, nmax, cm=1.0):
    out = []
    for j in range(NA):
        livre = -1
        for i in np.where(rank[:, j] <= Q)[0]:
            if i <= livre or i + 1 > ultima[j]: continue
            if not C[i, j] >= 1.02 * S20[i, j]: continue
            lim = S20[i, j]
            for k in range(i + 1, min(i + 7, ultima[j] + 1)):
                if L[k, j] <= lim:
                    e = min(lim, O[k, j]); r, R, q = trade(j, k, e, i, nR, nmax, cm)
                    out.append((int(T[k]), int(T[q]) + H4, r, R, int(T[i]), A[j], e / (2 * ATR[i, j]))); livre = q; break
            else:
                livre = i + 6
    out.sort(); return out


def conta(ev, modo):
    eq = 20.0; pk = eq; dd = 0; ab = []; livre = 0
    for x in ev:
        for o in sorted([o for o in ab if o[0] <= x[0]]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
        if eq <= 0.5: return 0.0, 1.0
        if modo == "todo":
            if ab: continue
            ab.append((x[1], eq * x[2]))
        else:
            notional = min(0.02 * eq * x[6], 10 * eq)       # x[6] = e/risco: valor para arriscar 2%
            if sum(o[2] for o in ab) + notional > 10 * eq: continue
            ab.append((x[1], notional * x[2], notional))
    for o in ab: eq += o[1]
    return eq / 20.0, dd


def acaso(ev, nR, nmax, n=200):
    """Mesmas horas de sinal, moeda ao acaso elegivel, long na abertura seguinte com a mesma geometria e custos."""
    res = {"risco": [], "todo": []}
    for _ in range(n):
        fake = []
        for x in ev:
            i = tix[x[4]]; cands = np.where(eleg[i] & (ultima > i + 1))[0]
            j = cands[rng.integers(len(cands))]; k = i + 1
            if np.isnan(O[k, j]): continue
            r, R, q = trade(j, k, O[k, j], i, nR, nmax)
            fake.append((int(T[k]), int(T[q]) + H4, r, R, x[4], A[j], O[k, j] / (2 * ATR[i, j])))
        fake.sort()
        for m in res: res[m].append(conta(fake, m)[0])
    return {m: np.percentile(v, 97.5) for m, v in res.items()}


linhas = []
def out(s): print(s, flush=True); linhas.append(s)


for Q in (0.10, 0.20):
    for nR, nmax, nome in ((2, 18, "2R/72h"), (1, 9, "1R/36h")):
        tudo = gerar(Q, nR, nmax); duplo = gerar(Q, nR, nmax, 2.0)
        passa = True
        for meta, f in (("2021-23", lambda t: t < CUT2), ("2023-26", lambda t: t >= CUT2)):
            ev = [x for x in tudo if f(x[4])]; ev2 = [x for x in duplo if f(x[4])]
            if not ev: out(f"H51 Q{int(Q*100)} {nome} {meta}: 0 ops"); passa = False; continue
            Rs = np.array([x[3] for x in ev]); Rs2 = np.array([x[3] for x in ev2])
            sem5 = np.sort(Rs)[:int(len(Rs) * 0.95)].mean()
            cr, ddr = conta(ev, "risco"); ct, ddt = conta(ev, "todo"); c2, _ = conta(ev2, "risco")
            p = acaso(ev, nR, nmax)
            sem_h40 = sum(1 for x in ev if x[0] // DAY not in dia_h40)
            ok = cr > 1 and ct > 1 and cr > p["risco"] and ct > p["todo"] and len(ev) >= 50 and sem5 > 0 and Rs2.mean() > 0 and c2 > 1
            passa &= ok
            out(f"H51 Q{int(Q*100)} {nome} {meta}: ops {len(ev)} R {Rs.mean():+.3f} acerto {100*np.mean(Rs>0):.0f}% "
                f"sem5% {sem5:+.3f} custos2x {Rs2.mean():+.3f} | risco2% x{cr:.2f} (queda {100*ddr:.0f}%, acaso p97.5 x{p['risco']:.2f}) "
                f"custos2x x{c2:.2f} | valor todo x{ct:.2f} (queda {100*ddt:.0f}%, acaso x{p['todo']:.2f}) | "
                f"em dias sem H40 {sem_h40}/{len(ev)} | moedas retiradas {sum(1 for x in ev if x[5] not in os.listdir(HIST) and x[5]+'.csv.gz' not in os.listdir(HIST))} | {'OK' if ok else 'falha'}")
        out(f"H51 Q{int(Q*100)} {nome}: {'PASSA' if passa else 'CHUMBA'}")
open("backtest/estudos/h51_resultado.txt", "w").write("\n".join(linhas) + "\n")
