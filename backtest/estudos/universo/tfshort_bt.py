"""TF-SHORT U2: livro 'sinais' (todas as operacoes da regra) em velas diarias UTC feitas das de 4H do ramo history,
com as funcoes da producao (tools/okx_tfshort: estado_medias, atr20, liquidez, r_op, STOP_ATR, EXCLUIR, LIQ_MIN).
Entrada na abertura do dia seguinte ao fecho com s<=1; saida na abertura seguinte ao fecho com s>=3; stop
entrada + 3 ATR20 (sai ao stop x 1,001, ou a abertura se ja abriu acima); depois do stop espera s>=3.
Funding: o do ramo history (Binance) quando existe; senao 0 e marcado."""
import gzip, glob, json, os, sys, bisect
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import okx_tfshort as T
pasta, funding_dir, saida = sys.argv[1], sys.argv[2], sys.argv[3]
DAY = 86400
def diario(p):
    d = {}
    for l in gzip.open(p, "rt").read().split():
        z = l.split(",")
        if len(z) < 6 or not z[0][0].isdigit(): continue
        t = int(float(z[0])); t = t // 1000 if t > 1e11 else t
        o, h, lo, c, v = map(float, z[1:6]); k = t // DAY
        x = d.get(k)
        if x is None: d[k] = {"t": k * DAY, "o": o, "h": h, "l": lo, "c": c, "usd": v * c, "n": 1, "_t": t}
        else:
            x["h"] = max(x["h"], h); x["l"] = min(x["l"], lo); x["usd"] += v * c; x["n"] += 1
            if t > x["_t"]: x["c"] = c; x["_t"] = t
    return [d[k] for k in sorted(d) if d[k]["n"] == 6]
def fund(a):
    p = os.path.join(funding_dir, a + ".csv.gz")
    if not os.path.exists(p): return None
    out = []
    for l in gzip.open(p, "rt").read().split():
        z = l.split(",")
        try:
            t = int(float(z[0])); out.append((t // 1000 if t > 1e11 else t, float(z[1])))
        except (ValueError, IndexError): pass
    return sorted(out)
ops = []
for p in sorted(glob.glob(pasta + "/*.csv.gz")):
    a = os.path.basename(p)[:-7]
    if a in T.EXCLUIR: continue
    v = diario(p)
    if len(v) < T.HIST_MIN + 2: continue
    F = fund(a); ft = [x[0] for x in F] if F else []
    aberta, parado = None, False
    for i in range(T.HIST_MIN, len(v) - 1):
        f = [x["c"] for x in v[: i + 1]]
        s = T.estado_medias(f)
        if s is None: continue
        if s >= 3: parado = False
        nx = v[i + 1]
        if aberta:
            # o dia i ja aconteceu: stop durante o dia i?
            if v[i]["h"] >= aberta["stop"] and v[i]["t"] >= aberta["t"]:
                sx = max(aberta["stop"], v[i]["o"]) * 1.001; t_out = v[i]["t"] + DAY; mot = "stop"; parado = True
            elif s >= 3:
                sx = nx["o"]; t_out = nx["t"]; mot = "regra"
            else:
                continue
            fs = None
            if F:
                j0, j1 = bisect.bisect_right(ft, aberta["t"]), bisect.bisect_right(ft, t_out)
                fs = sum(x[1] for x in F[j0:j1])
            R, ret = T.r_op(aberta["entrada"], sx, aberta["atr_pct"], fs or 0.0)
            ops.append({"ativo": a, "t_entrada": aberta["t"], "t_saida": t_out, "R": R, "ret": ret, "motivo": mot,
                        "funding_conhecido": fs is not None, "estrategia": "TF-SHORT U2"})
            aberta = None
            continue
        if s <= 1 and not parado and T.liquidez(v[: i + 1]) >= T.LIQ_MIN:
            atr = T.atr20(v[: i + 1])
            if not atr: continue
            e = nx["o"]
            aberta = {"t": nx["t"], "entrada": e, "atr_pct": atr / e, "stop": e + T.STOP_ATR * atr}
json.dump({"operacoes": ops}, open(saida, "w"))
print(len(ops), "operacoes", len({o["ativo"] for o in ops}), "moedas")
