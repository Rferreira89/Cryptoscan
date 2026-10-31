"""H26 (pre-registado 31/10, antes de correr): entrada com ordem limite nos lutadores da arena.
Pergunta: o ganho que a ordem limite deu a compra no panico (H23) repete-se nas outras estrategias?
Lutadores de compra que so usam velas (+ BTC): os de NEW_SIGS que correm sem contexto externo.
Periodos: P1 out/2024-set/2025, P2 out/2025-out/2026 (velas de 4H, 72 moedas, filtro BTC>SMA200 da arena).
Variantes de entrada para cada sinal (mesmas saidas do lutador: stop, objetivos, parciais, tempo):
  M   mercado na abertura seguinte (como hoje): 0,25% + 0,1% deslize por lado.
  L05 limite 0,5% abaixo do fecho do sinal, valida 2 velas; entrada 0,10% sem deslize; saidas como M.
  L10 o mesmo a 1,0%.  Sem execucao nao ha operacao.
Criterio (o unico, k = numero de lutadores x 2 variantes, Bonferroni): >= +0,15R nos dois periodos,
>= 50 ops por periodo, sem as 5% melhores > 0, custos a dobrar > 0. p contra a variante M do proprio
lutador (permutacao das diferencas por sinal emparelhado nao se aplica: usa-se o acaso da arena so se
algum passar). Resultado esperado honesto: a limite melhora a media de quase todos; a questao e se
algum chega a +0,15R."""
import gzip, glob, os, sys, math, json, multiprocessing as mp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools import arena_ringue as A
from engine import trade, paper_bounce as PB
H4, DAY = 14400, 86400
T0, CUT, T1 = 1727740800, 1759276800, 1792800000
W = 700
FEE, SLIP, MAKER = 0.25, 0.1, 0.10

def ler(a):
    r = [l.split(",") for l in gzip.open(f"/tmp/claude-0/hist/{a}.csv.gz", "rt").read().split()]
    return [{"t": int(float(z[0])), "o": float(z[1]), "h": float(z[2]), "l": float(z[3]), "c": float(z[4]), "v": float(z[5]), "tb": float(z[6]) if len(z) > 6 else float(z[5]) / 2}
            for z in r if len(z) >= 6]

BTC = ler("BTC")
ABOVE = A.btc_above(BTC)
A.CTX["btc"] = BTC

def correr(pos, c4, k0, sig, fill_o=None):
    k = k0
    while not pos["closed"] and k < len(c4):
        x = c4[k]
        o = fill_o if (k == k0 and fill_o is not None) else x["o"]
        trade.step(pos, o, x["h"], x["l"], x["c"], x["t"] + H4)
        if not pos["closed"] and sig.get("hold_s") and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
            trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
            trade._finish(pos, "TIME", x["t"] + H4)
        k += 1
    return k if pos["closed"] else None

def sim(c4, i, sig, modo, mult=1.0):
    plan = dict(sig, max_hold_s=None)
    if modo == "M":
        px = c4[i + 1]["o"]
        if not (sig["stop"] < px < sig["tp"][0]): return None
        pos = trade.open_position(plan, px, c4[i + 1]["t"], FEE * mult, SLIP * mult, breakeven=sig.get("breakeven", True))
        fim = correr(pos, c4, i + 1, sig)
        return None if fim is None else (pos["r"], fim)
    lim = c4[i]["c"] * (1 - (0.005 if modo == "L05" else 0.010))
    k0 = next((k for k in (i + 1, i + 2) if k < len(c4) and c4[k]["l"] <= lim), None)
    if k0 is None: return ("sem", None)
    e = min(lim, c4[k0]["o"])
    if not (sig["stop"] < e < sig["tp"][0]): return None
    pos = trade.open_position(plan, e, c4[k0]["t"], FEE * mult, SLIP * mult, breakeven=sig.get("breakeven", True))
    pos["entry"] = e                                   # limite: sem deslize na entrada
    fim = correr(pos, c4, k0, sig, fill_o=e)
    if fim is None: return None
    ru = (e - sig["stop"]) + (MAKER * mult / 100) * e + (FEE * mult / 100) * sig["stop"]
    r = (pos["realized"] + ((FEE - MAKER) * mult / 100) * e) / ru
    return (round(r, 3), fim)

def moeda(args):
    a, nomes = args
    try:
        c4 = ler(a)
    except Exception:
        return {}
    A.CTX["asset"] = a
    out = {}
    for nome in nomes:
        fn = A.NEW_SIGS[nome]
        res = {m: {"P1": [], "P2": [], "x2": {"P1": [], "P2": []}} for m in ("M", "L05", "L10")}
        livre = {m: -1 for m in res}
        try:
            for i in range(260, len(c4) - 3):
                t_sig = c4[i]["t"] + H4
                if t_sig < T0 or t_sig >= T1 or not A._known(t_sig, ABOVE):
                    continue
                if all(i <= livre[m] for m in res):
                    continue
                sig = fn(c4[max(0, i - W):i + 1])
                if not sig: continue
                per = "P1" if t_sig < CUT else "P2"
                for m in res:
                    if i <= livre[m]: continue
                    s = sim(c4, i, sig, m)
                    if not s or s[0] == "sem": continue
                    res[m][per].append(s[0]); livre[m] = s[1]
                    s2 = sim(c4, i, sig, m, 2.0)
                    res[m]["x2"][per].append(s2[0] if s2 and s2[0] != "sem" else s[0])
        except Exception as e:
            res = {"erro": f"{type(e).__name__}: {e}"[:100]}
        out[nome] = res
    return out

if __name__ == "__main__":
    nomes = [k for k in A.NEW_SIGS if k not in ("MOMENTUM", "BOUNCE_AMPLITUDE", "BOUNCE_LSR", "BOUNCE_MACRO",
                                                 "BOUNCE_MEDO", "BOUNCE_DESALAV", "BOUNCE_FLUXO", "MAIORES_FUNDING")]
    moedas = [os.path.basename(p).split(".")[0] for p in sorted(glob.glob("/tmp/claude-0/hist/*.csv.gz"))]
    with mp.Pool(2) as pool:
        partes = pool.map(moeda, [(a, nomes) for a in moedas])
    junta = {}
    for p in partes:
        for nome, res in p.items():
            if "erro" in res:
                junta.setdefault(nome, {"erros": 0})["erros"] = junta.get(nome, {}).get("erros", 0) + 1; continue
            j = junta.setdefault(nome, {m: {"P1": [], "P2": [], "x2": {"P1": [], "P2": []}} for m in ("M", "L05", "L10")})
            if "M" not in j: continue
            for m in ("M", "L05", "L10"):
                for per in ("P1", "P2"):
                    j[m][per] += res[m][per]; j[m]["x2"][per] += res[m]["x2"][per]
    k = 2 * len(nomes)
    print(f"H26 entrada com ordem limite nos lutadores ({len(nomes)} lutadores, {k} variantes novas; R liquido por operacao)")
    passou = []
    for nome, j in junta.items():
        if "M" not in j:
            print(f"{nome:<20} erro em {j.get('erros')} moedas"); continue
        linha = []
        for m in ("M", "L05", "L10"):
            ok = m != "M"
            cel = []
            for per in ("P1", "P2"):
                r = j[m][per]
                if not r: cel.append("  sem ops"); ok = False; continue
                mm = sum(r) / len(r); top = sorted(r)[:max(1, int(len(r) * 0.95))]; tp = sum(top) / len(top)
                x2 = sum(j[m]["x2"][per]) / len(j[m]["x2"][per])
                cel.append(f"n={len(r):>4} {mm:+.3f}")
                ok &= mm >= 0.15 and len(r) >= 50 and tp > 0 and x2 > 0
            linha.append(f"{m} {' / '.join(cel)}{' PASSA' if ok else ''}")
            if ok: passou.append((nome, m))
        print(f"{nome:<20} " + " | ".join(linha))
    print("candidatos a teste contra o acaso:", passou or "nenhum")
