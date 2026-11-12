"""(12/11, OK do Rui 02:13) Motor continuo de descoberta LONG: avalia TODAS as familias LONG existentes do ringue
em todas as moedas com historia (incluindo as retiradas da bolsa), por fase do mercado e por corretora, e diz se
alguma tem vantagem liquida ou se o melhor e ficar em espera. So investigacao: le velas publicas, nao tem chaves,
nao envia ordens, nao muda estrategias autorizadas.

Regras fixas (escritas antes de ver resultados; nao se afinam depois):
  - sinais e saidas: as funcoes do ringue (tools/arena_ringue), com velas fechadas, entrada na abertura seguinte;
    as compras so com o BTC acima da media de 200 dias (como ao vivo);
  - liquidez por data: mediana de 30 dias do volume diario >= 5 M USD na vespera (como o estudo H10);
  - custos Bybit UE: 0,25% + 0,10% por lado (ja no R da simulacao); custos OKX X-Perps: 0,05% + 0,05% por lado
    mais financiamento de referencia de 0,03%/dia pago pelo long (o real e por contrato: fica assinalado);
  - periodos: TREINO ate 2023-12-31, VALIDACAO 2024-01-01..2025-06-30, FORA 2025-07-01 em diante;
  - acontecimento independente = dia UTC de entrada; intervalos por bootstrap de dias;
  - CANDIDATA so se, na mesma fase e corretora: R por dia > 0 nos tres periodos, >= 15 dias em cada um, limite
    inferior (90%) > 0 em VALIDACAO+FORA e p (Holm sobre todos os testes) < 0,05. O resto fica "sem vantagem".
  - comparacao passiva: o que rendeu ter BTC durante cada operacao, na mesma unidade de risco (R).
Uso: python -m tools.descoberta_long <pasta_4h> <saida.json> [--moedas A,B] [--processos N]"""
import gzip
import json
import math
import os
import random
import statistics
import sys
import time

DAY = 86400
T_TREINO, T_VALID = 1704067200, 1751328000          # 2024-01-01, 2025-07-01
LIQ = 5e6
MIN_DIAS = 15
FAMILIAS = {
    "tendencia e momentum": ["TURTLE", "TURTLE_FORTES", "MOMENTUM", "MAIORES_TENDENCIA"],
    "rompimento com volume": ["BRK_ESPACO", "VOLUME_ACUMULACAO"],
    "recuo em tendencia": ["DIP_TREND", "FIBO_RECUO", "MAIORES_RECUO"],
    "reversao apos capitulacao": ["CAPITULACAO", "BOUNCE_X30", "BOUNCE_ISOLADA"],
    "recuperacao de niveis": ["RETESTE", "REVERSAO_INTERVALO"],
    "expansao de volatilidade": ["SQUEEZE_BB"],
}
SEM_DADOS = ["BOUNCE_MACRO", "BOUNCE_FLUXO", "MAIORES_FUNDING", "BOUNCE_LSR", "BOUNCE_DESALAV"]   # precisam de fluxo/macro por data
MAIORES = {"BTC", "ETH", "SOL"}
OKX_CUSTO, BYBIT_CUSTO, OKX_FUNDING_DIA = 0.002, 0.007, 0.0003


def carregar(p):
    rows = [l.split(",") for l in gzip.open(p, "rt").read().split()]
    out = []
    for r in rows:
        if len(r) >= 6 and r[0][:1].isdigit():
            t = int(float(r[0]))
            out.append({"t": t // 1000 if t > 1e11 else t, "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
                        "c": float(r[4]), "v": float(r[5]), "tb": float(r[6]) if len(r) > 6 and r[6] else 0.0})
    return out


def liquidez(c4):
    dv = {}
    for x in c4:
        d = x["t"] // DAY
        dv[d] = dv.get(d, 0) + x["v"] * x["c"]
    out, j = {}, []
    for d in sorted(dv):
        j.append(dv[d])
        j = j[-30:]
        out[d] = statistics.median(j)
    return out


_CTX = {}


def _preparar(pasta):
    from tools import arena_ringue as AR
    btc = carregar(os.path.join(pasta, "BTC.csv.gz"))
    _CTX.update(pasta=pasta, btc=btc, acima=AR.btc_above(btc), fases=AR.regime_by_day(btc),
                btc_px={x["t"]: x["c"] for x in btc})


def trabalho(a):
    """Operacoes de todas as familias LONG numa moeda (com data, fase, R Bybit, stop e duracao)."""
    from engine import backtest as B
    from tools import arena_ringue as AR
    try:
        c4 = carregar(os.path.join(_CTX["pasta"], a + ".csv.gz"))
    except OSError:
        return []
    if len(c4) < 400:
        return []
    AR.CTX.update(btc=_CTX["btc"], bars={"BTC": _CTX["btc"], a: c4}, funding={}, rank={}, daily={a: B.daily(c4)})
    lq, out = liquidez(c4), []
    for fam, ks in FAMILIAS.items():
        for k in ks:
            if k.startswith("MAIORES_") and a not in MAIORES:
                continue
            fn = AR.NEW_SIGS.get(k) or AR.MAIORES_SIGS.get(k)
            if not fn:
                continue
            try:
                for _, t in AR.generic_trades(a, c4, _CTX["acima"], 0, k, fn):
                    d = t["t"] // DAY
                    if lq.get(d - 1, 0) < LIQ:
                        continue
                    out.append({"k": k, "fam": fam, "a": a, "t": int(t["t"]), "t_fim": int(t.get("t_fim") or t["t"]),
                                "r": float(t["r"]), "stop": abs(float(t["geo"]["stop"])), "fase": _CTX["fases"].get(d - 1)})
            except Exception as e:                           # noqa: BLE001 (uma familia nao para a moeda)
                print(a, k, type(e).__name__, e, file=sys.stderr)
    return out


# ---------------------------------------------------------------- avaliacao (funcoes puras)
def r_okx(t):
    dias = max(0.0, (t["t_fim"] - t["t"]) / DAY)
    return t["r"] + (BYBIT_CUSTO - OKX_CUSTO) / t["stop"] - OKX_FUNDING_DIA * dias / t["stop"] if t["stop"] > 0 else t["r"]


def r_passivo_btc(t, btc_px):
    """O que rendeu ter BTC no mesmo intervalo, na unidade de risco da operacao (R)."""
    a, b = btc_px.get(t["t"] // 14400 * 14400), btc_px.get(t["t_fim"] // 14400 * 14400)
    if not a or not b or t["stop"] <= 0:
        return None
    return (b / a - 1) / t["stop"]


def por_dia(ops, campo):
    d = {}
    for o in ops:
        d.setdefault(o["t"] // DAY, []).append(o[campo])
    return {k: sum(v) / len(v) for k, v in d.items()}


def resumo(ops, campo, rng, reps=1000):
    if not ops:
        return {"n": 0, "dias": 0}
    rs = [o[campo] for o in ops]
    dd = sorted(por_dia(ops, campo).items())
    md = [v for _, v in dd]
    m = sum(md) / len(md)
    sd = math.sqrt(sum((x - m) ** 2 for x in md) / (len(md) - 1)) if len(md) > 1 else 0.0
    g, p = [x for x in rs if x > 0], [x for x in rs if x <= 0]
    eq = pk = q = 0.0
    for o in sorted(ops, key=lambda o: o["t_fim"]):
        eq += o[campo]
        pk = max(pk, eq)
        q = min(q, eq - pk)
    lo = hi = None
    if len(md) >= 5:
        bs = sorted(sum(rng.choice(md) for _ in md) / len(md) for _ in range(reps))
        lo, hi = bs[int(0.05 * reps)], bs[int(0.95 * reps) - 1]
    s = sorted(rs)
    return {"n": len(rs), "dias": len(md), "r_op": round(sum(rs) / len(rs), 4), "r_dia": round(m, 4),
            "ic90_dia": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
            "t_dia": round(m / (sd / math.sqrt(len(md))), 3) if sd > 0 else None,
            "pf": round(sum(g) / -sum(p), 3) if p and sum(p) < 0 else None, "acerto": round(len(g) / len(rs), 3),
            "mediana": round(s[len(s) // 2], 3), "p05": round(s[int(0.05 * len(s))], 3), "max_dd_r": round(q, 2)}


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def holm(ps):
    m = len(ps)
    ordem = sorted(range(m), key=lambda i: ps[i])
    adj, cor = [0.0] * m, 0.0
    for j, i in enumerate(ordem):
        cor = max(cor, min(1.0, (m - j) * ps[i]))
        adj[i] = cor
    return adj


def avaliar(ops, btc_px, seed=7, reps=1000):
    """Tabela familia x estrategia x fase x corretora com o criterio fixo, redundancias e leitura passiva."""
    rng = random.Random(seed)
    for o in ops:
        o["r_bybit"], o["r_okx"] = o["r"], r_okx(o)
        pb = r_passivo_btc(o, btc_px)
        o["r_btc"] = pb if pb is not None else 0.0
    linhas, ps = [], []
    for k in sorted({o["k"] for o in ops}):
        for fase in ("subida", "lateral", "queda"):
            xs = [o for o in ops if o["k"] == k and o["fase"] == fase]
            if not xs:
                continue
            for corretora, campo in (("bybit_ue", "r_bybit"), ("okx", "r_okx")):
                tr = [o for o in xs if o["t"] < T_TREINO]
                va = [o for o in xs if T_TREINO <= o["t"] < T_VALID]
                fo = [o for o in xs if o["t"] >= T_VALID]
                R = {"treino": resumo(tr, campo, rng, reps), "validacao": resumo(va, campo, rng, reps),
                     "fora": resumo(fo, campo, rng, reps), "validacao_mais_fora": resumo(va + fo, campo, rng, reps)}
                vf = R["validacao_mais_fora"]
                p = 1 - phi(vf["t_dia"]) if vf.get("t_dia") is not None else 1.0
                base = all(R[x].get("dias", 0) >= MIN_DIAS and (R[x].get("r_dia") or 0) > 0 for x in ("treino", "validacao", "fora"))
                passivo = resumo(va + fo, "r_btc", rng, 200)
                linhas.append({"estrategia": k, "familia": xs[0]["fam"], "fase": fase, "corretora": corretora, **R,
                               "passivo_btc_r_dia": passivo.get("r_dia"), "p": round(p, 5), "_base": base,
                               "moedas": len({o["a"] for o in xs})})
                ps.append(p)
    for l, adj in zip(linhas, holm(ps) if ps else []):
        ic = (l["validacao_mais_fora"].get("ic90_dia") or [None])[0]
        l["p_holm"] = round(adj, 5)
        l["candidata"] = bool(l.pop("_base") and ic is not None and ic > 0 and adj < 0.05)
        l["veredicto"] = "CANDIDATA (papel/sombra; real so com aprovacao)" if l["candidata"] else "sem vantagem demonstrada"
        l["classe"] = classe(l)
    # redundancia: correlacao dos resultados diarios (Bybit) entre estrategias
    dias = {k: por_dia([o for o in ops if o["k"] == k], "r_bybit") for k in {o["k"] for o in ops}}
    red = []
    ks = sorted(dias)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            com = sorted(set(dias[a]) & set(dias[b]))
            if len(com) >= 20:
                xa, xb = [dias[a][d] for d in com], [dias[b][d] for d in com]
                ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
                va, vb = sum((x - ma) ** 2 for x in xa), sum((x - mb) ** 2 for x in xb)
                if va > 0 and vb > 0:
                    c = sum((x - ma) * (y - mb) for x, y in zip(xa, xb)) / math.sqrt(va * vb)
                    if c >= 0.7:
                        red.append({"a": a, "b": b, "corr": round(c, 2), "dias_comuns": len(com)})
    return linhas, red


def classe(l):
    """Tres classes, por regra fixa:
    VANTAGEM DEMONSTRADA: passou o criterio inteiro (candidata).
    INCONCLUSIVA: R por dia > 0 em VALIDACAO+FORA mas o intervalo inclui zero ou ha menos de 15 dias nalgum periodo.
    SEM VANTAGEM: R por dia <= 0 em VALIDACAO+FORA (NEGATIVA se o intervalo inteiro fica abaixo de zero)."""
    vf = l.get("validacao_mais_fora") or {}
    if l.get("candidata"):
        return "VANTAGEM DEMONSTRADA"
    rd = vf.get("r_dia")
    ic = vf.get("ic90_dia") or [None, None]
    if rd is not None and rd > 0:
        return "INCONCLUSIVA"
    if ic[1] is not None and ic[1] < 0:
        return "SEM VANTAGEM (NEGATIVA)"
    return "SEM VANTAGEM"


def markdown(r):
    """Tabela legivel do resultado (uma linha por estrategia, fase e corretora)."""
    out = [f"Moedas avaliadas: {r.get('moedas_avaliadas')} (com operacoes: {r.get('moedas_com_operacoes')}); operacoes: {r.get('operacoes')}.",
           f"BTC comprar e manter (%): {r.get('btc_comprar_e_manter_pct')}.", f"Portao: {r.get('portao', {}).get('decisao')}", "",
           "| Estrategia | Familia | Fase | Corretora | Classe | Treino R/dia (dias) | Validacao R/dia (dias) | Fora R/dia (dias) | Val+Fora R/op | Val+Fora R/dia [IC90] | PF | Pior DD (R) | BTC passivo R/dia | p Holm |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for l in sorted(r.get("resultados") or [], key=lambda l: (classe(l), l["estrategia"], l["fase"], l["corretora"])):
        vf = l["validacao_mais_fora"]
        c = lambda x: f"{x.get('r_dia')} ({x.get('dias', 0)})"
        out.append(f"| {l['estrategia']} | {l['familia']} | {l['fase']} | {l['corretora']} | {classe(l)} | {c(l['treino'])} | {c(l['validacao'])} | "
                   f"{c(l['fora'])} | {vf.get('r_op')} | {vf.get('r_dia')} {vf.get('ic90_dia')} | {vf.get('pf')} | {vf.get('max_dd_r')} | "
                   f"{l.get('passivo_btc_r_dia')} | {l.get('p_holm')} |")
    if r.get("redundantes"):
        out += ["", "Redundantes (correlacao diaria >= 0,7): " + "; ".join(f"{x['a']} ~ {x['b']} ({x['corr']})" for x in r["redundantes"])]
    return "\n".join(out) + "\n"


def portao(linhas, fase_atual):
    """O que o mercado permite agora: as candidatas da fase atual, ou espera."""
    ok = sorted({(l["estrategia"], l["corretora"]) for l in linhas if l["candidata"] and l["fase"] == fase_atual})
    return {"fase_atual": fase_atual, "long_permitido": bool(ok), "candidatas": [{"estrategia": a, "corretora": b} for a, b in ok],
            "decisao": "ha candidatas LONG para esta fase (so papel/sombra ate aprovacao)" if ok else
                       "ESPERA: nenhuma familia LONG tem vantagem demonstrada nesta fase"}


def correr(pasta, moedas=None, processos=1, reps=1000):
    _preparar(pasta)
    todas = sorted(f[:-7] for f in os.listdir(pasta) if f.endswith(".csv.gz"))
    moedas = [m for m in (moedas or todas) if m in todas]
    if processos > 1:
        from multiprocessing import Pool
        with Pool(processos, initializer=_preparar, initargs=(pasta,)) as pool:
            ops = [t for r in pool.imap_unordered(trabalho, moedas, chunksize=2) for t in r]
    else:
        ops = [t for a in moedas for t in trabalho(a)]
    linhas, red = avaliar(ops, _CTX["btc_px"], reps=reps)
    btc = _CTX["btc"]
    fase = _CTX["fases"].get(max(_CTX["fases"])) if _CTX["fases"] else None

    def bh(a, b):
        xs = [x["c"] for x in btc if a <= x["t"] < b]
        return round((xs[-1] / xs[0] - 1) * 100, 1) if len(xs) > 1 else None
    fim = btc[-1]["t"] + 14400
    return {"gerado": int(time.time()), "dados_ate": fim, "moedas_avaliadas": len(moedas), "operacoes": len(ops),
            "moedas_com_operacoes": len({o["a"] for o in ops}),
            "btc_comprar_e_manter_pct": {"treino": bh(0, T_TREINO), "validacao": bh(T_TREINO, T_VALID), "fora": bh(T_VALID, fim)},
            "criterio": "R/dia > 0 e >= 15 dias em TREINO, VALIDACAO e FORA; IC90 inferior > 0 em VALIDACAO+FORA; Holm < 0,05",
            "portao": portao(linhas, fase), "resultados": linhas, "redundantes": red,
            "sem_dados_para_avaliar": SEM_DADOS,
            "aviso": "So investigacao. Historico nao e garantia. Nenhuma estrategia passa a dinheiro real sem aprovacao do Rui."}


if __name__ == "__main__" and sys.argv[1:2] == ["--resumir"]:
    with open(sys.argv[2], encoding="utf-8") as f:
        _r = json.load(f)
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        f.write(markdown(_r))
    from collections import Counter
    print(dict(Counter(classe(l) for l in _r["resultados"])))
elif __name__ == "__main__":
    a = sys.argv
    moedas = a[a.index("--moedas") + 1].split(",") if "--moedas" in a else None
    proc = int(a[a.index("--processos") + 1]) if "--processos" in a else 1
    r = correr(a[1], moedas, proc)
    with open(a[2], "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(json.dumps(r["portao"], ensure_ascii=False))
    for l in sorted(r["resultados"], key=lambda l: -(l["validacao_mais_fora"].get("r_dia") or -9))[:12]:
        vf = l["validacao_mais_fora"]
        print(f"{l['estrategia']:20s} {l['fase']:8s} {l['corretora']:9s} treino {l['treino'].get('r_dia')} val+fora {vf.get('r_dia')} "
              f"ic {vf.get('ic90_dia')} dias {vf.get('dias')} holm {l['p_holm']} -> {l['veredicto']}")
