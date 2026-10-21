"""H8 e H9 (pre-registados a 21/10, antes de correr; OK do Rui).

H8 - So entrar quando o 1.o objetivo paga pelo menos 3x o custo de ida e volta.
  Custo de ida e volta = 2 x (comissao 0,25% + deslize 0,10%) = 0,70% (os do ringue).
  Regra: manter so as operacoes com TP1 >= 2,1% acima da entrada.
  Estrategias: BOUNCE_X30, BOUNCE_ISOLADA, BOUNCE_SQUEEZE (so com funding: 2024-08+),
  BRK_ESPACO, RETESTE. Moedas: as atuais (/hist). Filtro de liquidez por data.
  Periodos: A = 2021-06-01 a 2024-05-31, B = 2024-06-01 a 2026-10-15.
  PASSA se, nos DOIS periodos, o R medio por dia (cada dia conta uma vez) das
  operacoes filtradas for >= +0,05R acima do das nao filtradas, e o filtrado
  mantiver >= 30 dias distintos com entradas.

H9 - A sobrevenda ganha com as moedas que desapareceram?
  Mesmas BOUNCE_X30 e BOUNCE_ISOLADA, universo = moedas atuais + 183 delistadas,
  so com liquidez em cada data (mediana de 30 dias do volume diario >= 5 M USD).
  Compara com o universo so das atuais (mesmo filtro de liquidez).
  O vies de sobrevivencia e MATERIAL se, em algum periodo, o R medio por
  operacao cair >= 0,10R com as delistadas, ou mudar de sinal.
  E a familia SOBREVIVE se continuar com R medio > 0 nos dois periodos com o
  universo completo.
"""
import glob, gzip, os, sys, json, statistics
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/cryptoscan")
from tools import arena_ringue as AR

DAY = 86400
A0, A1 = 1622505600, 1717113600          # 2021-06-01 .. 2024-05-31
B0, B1 = 1717200000, 1792022400          # 2024-06-01 .. 2026-10-15
CUSTO = 2 * (0.25 + 0.10) / 100
LIQ = 5e6
KEYS_H8 = ["BOUNCE_X30", "BOUNCE_ISOLADA", "BOUNCE_SQUEEZE", "BRK_ESPACO", "RETESTE"]
KEYS_H9 = ["BOUNCE_X30", "BOUNCE_ISOLADA"]


def load(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "v": float(r[5]), "tb": float(r[6] or 0)} for r in rows if len(r) >= 7]


def funding_de(a):
    p = f"/tmp/claude-0/hist/funding/{a}.csv.gz"
    if not os.path.exists(p):
        return []
    out = []
    for l in gzip.open(p, "rt").read().split():
        t, r = l.split(",")[:2]
        out.append((int(t), float(r)))
    return sorted(out)


BTC = load("/tmp/claude-0/hist/BTC.csv.gz")
ABOVE = AR.btc_above(BTC)


def liquidez(c4):
    """{dia: mediana 30 dias do volume diario em USD} (so passado)."""
    dv = {}
    for x in c4:
        d = x["t"] // DAY
        dv[d] = dv.get(d, 0) + x["v"] * x["c"]
    dias = sorted(dv)
    out, janela = {}, []
    for d in dias:
        janela.append(dv[d])
        if len(janela) > 30:
            janela.pop(0)
        out[d] = statistics.median(janela)
    return out


def trabalho(arg):
    a, path, keys = arg
    try:
        c4 = load(path)
    except Exception:
        return a, []
    if len(c4) < 400:
        return a, []
    AR.CTX.update(btc=BTC, bars={"BTC": BTC}, funding={a: funding_de(a)}, rank={})
    lq = liquidez(c4)
    out = []
    for k in keys:
        try:
            for _, t in AR.generic_trades(a, c4, ABOVE, A0, k, AR.NEW_SIGS[k]):
                d = t["t"] // DAY
                out.append({"k": k, "a": a, "t": t["t"], "r": t["r"], "tp1": t["geo"]["tp"][0],
                            "liq": lq.get(d - 1, 0)})
        except Exception as e:
            print(a, k, e, file=sys.stderr)
    return a, out


def resumo(ts):
    if not ts:
        return {"n": 0}
    dias = {}
    for t in ts:
        dias.setdefault(t["t"] // DAY, []).append(t["r"])
    md = [sum(v) / len(v) for v in dias.values()]
    return {"n": len(ts), "r": round(sum(t["r"] for t in ts) / len(ts), 3), "dias": len(dias),
            "r_dia": round(sum(md) / len(md), 3)}


def per(ts, a0, a1):
    return [t for t in ts if a0 <= t["t"] < a1]


if __name__ == "__main__":
    atuais = {os.path.basename(p).split(".")[0]: p for p in glob.glob("/tmp/claude-0/hist/*.csv.gz")}
    delist = {os.path.basename(p).split(".")[0]: p for p in glob.glob("/tmp/claude-0/delist/*.csv.gz")}
    jobs = [(a, p, KEYS_H8) for a, p in atuais.items()] + [(a, p, KEYS_H9) for a, p in delist.items() if a not in atuais]
    with Pool(2) as pool:
        res = dict(pool.map(trabalho, jobs, chunksize=4))
    todos = [t for v in res.values() for t in v if t["liq"] >= LIQ]
    json.dump(todos, open("/tmp/claude-0/estudo/h8h9_trades.json", "w"))
    cur = [t for t in todos if t["a"] in atuais]
    print("=== H8: TP1 >= 3x custo (0,70%) ===")
    h8 = True
    for nome, a0, a1 in (("A 2021-24", A0, A1), ("B 2024-26", B0, B1)):
        base = per(cur, a0, a1)
        filt = [t for t in base if t["tp1"] >= 3 * CUSTO]
        rb, rf = resumo(base), resumo(filt)
        ok = rf.get("dias", 0) >= 30 and rb.get("n") and rf.get("r_dia", -9) >= rb["r_dia"] + 0.05
        h8 &= bool(ok)
        print(nome, "sem filtro", rb, "| com filtro", rf, "| passa" if ok else "| falha")
        for k in KEYS_H8:
            b, f = resumo([t for t in base if t["k"] == k]), resumo([t for t in filt if t["k"] == k])
            print("   ", k, b, "->", f)
    print("H8:", "PASSA" if h8 else "CHUMBA")
    print("=== H9: sobrevenda com as moedas delistadas ===")
    sobre = [t for t in todos if t["k"] in KEYS_H9]
    mat, vive = False, True
    for nome, a0, a1 in (("A 2021-24", A0, A1), ("B 2024-26", B0, B1)):
        s_cur = resumo([t for t in per(sobre, a0, a1) if t["a"] in atuais])
        s_all = resumo(per(sobre, a0, a1))
        s_del = resumo([t for t in per(sobre, a0, a1) if t["a"] not in atuais])
        print(nome, "so atuais", s_cur, "| todas", s_all, "| so delistadas", s_del)
        if s_cur.get("n") and s_all.get("n"):
            if s_all["r"] <= s_cur["r"] - 0.10 or (s_cur["r"] > 0) != (s_all["r"] > 0):
                mat = True
            if s_all["r"] <= 0:
                vive = False
        for k in KEYS_H9:
            print("   ", k, "atuais", resumo([t for t in per(sobre, a0, a1) if t["k"] == k and t["a"] in atuais]),
                  "todas", resumo([t for t in per(sobre, a0, a1) if t["k"] == k]))
    print("H9: vies de sobrevivencia", "MATERIAL" if mat else "pequeno", "| sobrevenda", "SOBREVIVE" if vive else "NAO SOBREVIVE", "com o universo completo")
