"""H25 (30/10): teste do modo acelerado (engine/acelerado.py) antes de existir dinheiro real nele.
Pergunta: com a mesma estrategia, quanto mais depressa cresce a conta e quanto mais funda e a queda
com o risco normal (0,5%), o acelerado (meio-Kelly calculado so com operacoes passadas, teto 2,5%,
metade a -5%, reduzido 0,25% a -10%) e risco fixo alto (2,5% e 5%)?
Dados: as operacoes reais do H23 L10 (compra no panico, ordem limite) em 2024-26, por ordem de tempo,
e 10 000 anos simulados por blocos (520 operacoes por ano, blocos de 10 para manter as rachas).
Tres mundos: a vantagem medida (+0,08R) e a mesma distribuicao deslocada para +0,15R e +0,30R
(o que teria de aparecer no papel ao vivo para a estrategia ser aprovada)."""
import gzip, glob, os, sys, math, random, numpy as np
sys.argv = ["x"]
src = open(os.path.join(os.path.dirname(__file__), "h23_ordens_limite.py")).read().split("modos = (")[0]
exec(src)
ops = []
for p in sorted(glob.glob("/tmp/claude-0/hist/funding/*.csv.gz")):
    a = os.path.basename(p).split(".")[0]
    if not os.path.exists(f"/tmp/claude-0/hist/{a}.csv.gz"): continue
    x, f = load4(a), loadf(a)
    if len(f) < 400 or len(x) < 600: continue
    t, o, h, l, c = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h, pc) - np.minimum(l, pc)
    d = dict(t=t, o=o, h=h, l=l, c=c, atr=np.convolve(tr, np.ones(42) / 42, "full")[:len(tr)])
    ft, fv = f[:, 0], f[:, 1]; livre = -1
    for i in range(18, len(c) - 2):
        if t[i] < ft[0] + 90 * DAY or i <= livre: continue
        k = np.searchsorted(ft, t[i] + H4, side="right") - 1
        if k < 270: continue
        if fv[k] <= np.percentile(fv[k - 270:k], 5) and fv[k] < 0 and c[i] / c[i - 18] - 1 <= -0.10:
            s = sim(d, i, "L10")
            if s and s[0] != "sem": ops.append((t[i], s[0])); livre = s[1]
ops.sort(); R = np.array([r for _, r in ops])
print(f"H25 modo acelerado | {len(R)} operacoes L10 2024-26, media {R.mean():+.3f}R, acerto {100*(R>0).mean():.0f}%")

def kelly_pct(hist):
    n = len(hist)
    if n < 60: return None
    m = hist.mean(); lb = m - hist.std(ddof=1) / math.sqrt(n); e2 = (hist ** 2).mean()
    return None if lb <= 0 else 100 * 0.5 * lb / e2

def correr(rs, regra, hist0=None):
    eq, pico, mdd, hist = 1.0, 1.0, 0.0, list(hist0 if hist0 is not None else [])
    for r in rs:
        dd = 1 - eq / pico
        if regra == "normal": pct = 0.25 if dd >= 0.10 else 0.5
        elif regra == "acelerado":
            k = kelly_pct(np.array(hist)) if len(hist) >= 60 else None
            if dd >= 0.10: pct = 0.25
            elif k is None or min(k, 2.5) <= 0.5: pct = 0.5
            else: pct = min(k, 2.5) / (2 if dd >= 0.05 else 1)
        else: pct = regra
        eq *= max(1 + pct / 100 * r, 0.0); pico = max(pico, eq); mdd = max(mdd, 1 - eq / pico); hist.append(r)
        if eq <= 0.01: return 0.0, 1.0
    return eq, mdd

print("\n1) Historico real, por ordem (risco a partir da operacao 1; o acelerado so liga depois de 60 operacoes):")
for regra in ("normal", "acelerado", 2.5, 5.0):
    eq, mdd = correr(R, regra)
    print(f"   {str(regra):<10} conta x{eq:.2f}  queda maxima {mdd:.0%}")

rng = np.random.default_rng(25)
def ano(base):
    nb = 52; ii = rng.integers(0, len(base) - 10, nb)
    return np.concatenate([base[i:i + 10] for i in ii])
print("\n2) 10 000 anos simulados (520 operacoes/ano). O acelerado comeca ja com o historico do papel (60 ops):")
for nome, desl in (("vantagem medida", 0.0), ("se o papel der +0,15R", 0.15 - R.mean()), ("se o papel der +0,30R", 0.30 - R.mean())):
    base = R + desl
    print(f"   -- {nome} (media {base.mean():+.2f}R)")
    for regra in ("normal", "acelerado", 2.5, 5.0):
        eqs, dds = [], []
        for _ in range(10000 if regra != "acelerado" else 2000):
            h0 = base[rng.integers(0, len(base), 60)]
            e, m = correr(ano(base), regra, h0); eqs.append(e); dds.append(m)
        eqs, dds = np.array(eqs), np.array(dds)
        print(f"      {str(regra):<10} mediana x{np.median(eqs):.2f}  pior 5% x{np.percentile(eqs,5):.2f}  melhor 5% x{np.percentile(eqs,95):.2f}"
              f"  perde dinheiro {100*(eqs<1).mean():.0f}%  queda >30% {100*(dds>0.30).mean():.0f}%")
