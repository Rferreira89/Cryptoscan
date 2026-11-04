"""H41 (pre-registado 04/11, antes de correr). Pedido do Rui: "quando o mercado sobe tem de haver uma estrategia".
Compra de quebras nas altcoins SO em mercado de subida, com custos de futuros (OKX), ao nivel da conta.
Universo: history + 184 delistadas (sem vies de sobrevivencia), dias fechados, liquidez >= 2 M USD/dia (30 dias).
Mercado de subida: BTC fecha acima da media de 50 dias e essa media sobe face a 10 dias antes.
Entrada: a moeda fecha acima do maximo dos 20 dias anteriores -> compra na abertura seguinte.
Stop inicial 2 ATR(14) abaixo da entrada; saida quando fecha abaixo do minimo de 10 dias (Donchian) ou no stop;
tempo maximo 30 dias. Custos 0,10% por lado (taker) + financiamento 10%/ano.
Variantes (k=2): A todos os sinais com risco 1%; B igual mas so as 3 moedas mais fortes por dia (impulso 20 dias).
Metades H1 2021-08..2024-02, H2 2024-03..2026-10. Criterio: conta a crescer nas DUAS metades, >= 50 ops por
metade, media positiva sem as 5% melhores. So informa: papel antes de dinheiro real."""
import numpy as np
exec(open("backtest/estudos/h35_rotacao_altcoins.py").read().split("btc50 = [")[0])
H = np.full_like(C, np.nan); L = H.copy()
# maximos e minimos diarios a partir das velas de 4H (ja agregadas em DD: [o,h,l,c,v])
for a, d in DD.items():
    for t, q in d.items():
        if t in it: H[ia[a], it[t]], L[ia[a], it[t]] = q[1], q[2]
def rolling(M, n, f):
    out = np.full_like(M, np.nan)
    for j in range(n, M.shape[1]): out[:, j] = f(M[:, j - n:j], axis=1)
    return out
MX20 = rolling(H, 20, np.max); MN10 = rolling(L, 10, np.min)
PC = np.roll(C, 1, axis=1); TR = np.fmax(H - L, np.fmax(np.abs(H - PC), np.abs(L - PC))); ATR = rolling(TR, 14, np.mean)
S50b = S50[b]; sub = (C[b] > S50b) & (S50b > np.roll(S50b, 10))
CUSTO, FUND = 0.001, 0.10 / 365
def ops(top3):
    out = []
    for i in range(60, len(T) - 2):
        if not sub[i]: continue
        cand = [a for a in range(len(A)) if a != b and V30[a, i] >= 2e6 and not np.isnan(MX20[a, i]) and C[a, i] > MX20[a, i] and not np.isnan(ATR[a, i])]
        if top3: cand = sorted(cand, key=lambda a: -(C[a, i] / C[a, i - 20] - 1 if not np.isnan(C[a, i - 20]) else -9))[:3]
        for a in cand:
            e = O[a, i + 1]
            if np.isnan(e) or e <= 0: continue
            stop = e - 2 * ATR[a, i]; risk = e - stop
            if risk <= 0: continue
            px, j = None, None
            for k in range(i + 1, min(len(T) - 1, i + 31)):
                if np.isnan(C[a, k]): px, j = C[a, k - 1], k - 1; break
                if L[a, k] <= stop: px, j = min(stop, O[a, k]), k; break
                if not np.isnan(MN10[a, k]) and C[a, k] < MN10[a, k]: px, j = C[a, k], k; break
            if px is None: j = min(len(T) - 2, i + 30); px = C[a, j]
            if np.isnan(px): continue
            R = ((px - e) - CUSTO * (e + px) - FUND * (j - i) * e) / risk
            out.append((T[i + 1], T[j], R))
    return out
def conta(ev):
    eq = 1.0; pk = 1; dd = 0; ab = []
    for t0, t1, R in sorted(ev):
        for o in sorted([o for o in ab if o[0] <= t0]): eq += o[1]; ab.remove(o); pk = max(pk, eq); dd = max(dd, 1 - eq / pk)
        ab.append((t1, 0.01 * eq * R))
    for o in ab: eq += o[1]
    return eq, dd
print("H41 quebras de 20 dias nas altcoins em mercado de subida (futuros, conta, risco 1%)")
for nome, top3 in (("A todos", False), ("B top 3", True)):
    tudo = ops(top3); ok = True
    for per, (a0, a1) in (("H1", H1), ("H2", H2)):
        ev = [x for x in tudo if a0 <= x[0] <= a1]; Rs = [x[2] for x in ev]
        if not Rs: print(f" {nome} {per}: sem operacoes"); ok = False; continue
        eq, dd = conta(ev); sem = np.mean(sorted(Rs)[:max(1, int(len(Rs) * .95))])
        print(f" {nome} {per}: ops {len(Rs)} R {np.mean(Rs):+.3f} acerto {100*np.mean(np.array(Rs)>0):.0f}% conta x{eq:.2f} queda {100*dd:.0f}% sem top5% {sem:+.3f}")
        ok &= eq > 1 and len(Rs) >= 50 and sem > 0
    print(f"   {nome}: {'PASSA -> PAPEL' if ok else 'CHUMBA'}")
