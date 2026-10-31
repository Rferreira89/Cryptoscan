"""H26b (pre-registado 31/10, depois do H26 e antes de correr): confirmacao do TURTLE, o unico lutador
que passou o limiar de R no H26 (M +0,16/+0,28; L05 +0,19/+0,27; L10 +0,20/+0,22).
Tres testes, todos tem de passar para ir a papel:
 1. Sem vies de sobrevivencia: as 72 moedas de hoje MAIS as 184 delistadas da Binance (ramo history-delistadas).
 2. Contra o acaso: mesmas moedas, periodo e numero de entradas; entradas em velas ao acaso com o mesmo plano
    (stop 2N, objetivos 2R/5R, metade em cada, stop a seguir, 20 dias), mesma variante de entrada; 100 repeticoes;
    p unilateral (aproximacao normal, z) < 0,05/44 = 0,0011 (Bonferroni do H26).
 3. Periodo antigo como teste extra fora da amostra: P0 jan/2021-set/2024 (com o filtro BTC>SMA200).
Criterio por periodo (P0, P1, P2): >= +0,15R, >= 50 ops, sem top 5% > 0, custos x2 > 0, p < 0,0011."""
import gzip, glob, os, sys, random, multiprocessing as mp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
import h26_limite_lutadores as H
from tools import arena_ringue as A
from engine import backtest as B
H4, DAY = 14400, 86400
P0, T0, CUT, T1 = 1609459200 + 60 * DAY, H.T0, H.CUT, H.T1
REPS = 100
DELIST = "/tmp/claude-0/delist"

def ler_qualquer(p):
    r = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(float(z[0])), "o": float(z[1]), "h": float(z[2]), "l": float(z[3]), "c": float(z[4]),
             "v": float(z[5]), "tb": float(z[6]) if len(z) > 6 else float(z[5]) / 2} for z in r if len(z) >= 6]

def periodo(t):
    if t < P0 or t >= T1: return None
    return "P0" if t < T0 else ("P1" if t < CUT else "P2")

def planos(c4):
    """Funcao i -> plano do TURTLE sem a condicao de rompimento (para as entradas ao acaso), com o N
    calculado uma vez sobre o diario completo."""
    import bisect
    d = B.daily(c4)
    ts = [x["t"] for x in d]
    tr = [0.0] + [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"]) for k in range(1, len(d))]
    def f(i):
        n_done = bisect.bisect_right(ts, c4[i]["t"] + H4 - DAY)      # dias com t + DAY <= fim da vela
        if n_done < 25: return None
        N = sum(tr[n_done - 20:n_done]) / 20
        e = c4[i]["c"]; stop = e - 2 * N
        if not 0 < stop < e * 0.995: return None
        r = e - stop
        return {"stop": stop, "tp": [e + 2 * r, e + 5 * r], "partials": [50, 50], "breakeven": True,
                "hold_s": 20 * DAY, "trail_r": 1.0}
    return f

def moeda(p):
    try:
        c4 = ler_qualquer(p)
    except Exception:
        return None
    if len(c4) < 400: return None
    rng = random.Random(hash(os.path.basename(p)) & 0xFFFF)
    out = {m: {per: {"r": [], "x2": [], "acaso": [[] for _ in range(REPS)]} for per in ("P0", "P1", "P2")} for m in ("M", "L05", "L10")}
    livre = {m: -1 for m in out}
    cont = {m: {"P0": 0, "P1": 0, "P2": 0} for m in out}
    for i in range(260, len(c4) - 3):
        t_sig = c4[i]["t"] + H4
        per = periodo(t_sig)
        if not per or not A._known(t_sig, H.ABOVE): continue
        if all(i <= livre[m] for m in out): continue
        sig = A.sig_turtle(c4[max(0, i - H.W):i + 1])
        if not sig: continue
        for m in out:
            if i <= livre[m]: continue
            s = H.sim(c4, i, sig, m)
            if not s or s[0] == "sem": continue
            out[m][per]["r"].append(s[0]); livre[m] = s[1]; cont[m][per] += 1
            s2 = H.sim(c4, i, sig, m, 2.0)
            out[m][per]["x2"].append(s2[0] if s2 and s2[0] != "sem" else s[0])
    plano_em = planos(c4)
    pool = {per: [i for i in range(260, len(c4) - 3) if periodo(c4[i]["t"] + H4) == per and A._known(c4[i]["t"] + H4, H.ABOVE)]
            for per in ("P0", "P1", "P2")}
    for m in out:
        for per in ("P0", "P1", "P2"):
            k = cont[m][per]
            if not k or not pool[per]: continue
            for rep in range(REPS):
                got, tent = 0, 0
                while got < k and tent < 6 * k:
                    tent += 1
                    i = rng.choice(pool[per])
                    sig = plano_em(i)
                    if not sig: continue
                    s = H.sim(c4, i, sig, m)
                    if not s or s[0] == "sem": continue
                    out[m][per]["acaso"][rep].append(s[0]); got += 1
    return out

if __name__ == "__main__":
    fich = sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz")) + sorted(glob.glob(f"{DELIST}/*.csv.gz"))
    with mp.Pool(2) as pool:
        partes = [x for x in pool.map(moeda, fich) if x]
    print(f"H26b TURTLE: {len(partes)} moedas com historico (72 atuais + delistadas), acaso {REPS} repeticoes")
    for m in ("M", "L05", "L10"):
        ok = True
        cel = []
        for per in ("P0", "P1", "P2"):
            r = [x for p in partes for x in p[m][per]["r"]]
            x2 = [x for p in partes for x in p[m][per]["x2"]]
            ms = []
            for rep in range(REPS):
                v = [x for p in partes for x in p[m][per]["acaso"][rep]]
                ms.append(sum(v) / len(v) if v else 0)
            if not r:
                cel.append(f"{per} sem ops"); ok = False; continue
            import math, statistics as S
            mm = sum(r) / len(r); sd = S.pstdev(ms) or 1e-9
            pv = 0.5 * math.erfc((mm - sum(ms) / len(ms)) / sd / math.sqrt(2))
            top = sorted(r)[:max(1, int(len(r) * 0.95))]
            tp, md = sum(top) / len(top), sum(x2) / len(x2)
            ac = sum(ms) / len(ms)
            cel.append(f"{per} n={len(r)} {mm:+.3f}R (acaso {ac:+.3f}, p={pv:.4f}) s/top {tp:+.3f} x2 {md:+.3f}")
            ok &= mm >= 0.15 and len(r) >= 50 and tp > 0 and md > 0 and pv < 0.0011
        print(f" {m}: " + " | ".join(cel) + f"  -> {'PASSA -> PAPEL' if ok else 'chumba'}")
