"""(08/11, pedido do Rui) Auditoria do Kronos K1 fora da amostra.

O Kronos foi pre-treinado com dados ate JUNHO DE 2024 (artigo arXiv 2508.02739, secao de dados: "The pre-training data
for Kronos extends up to June 2024"). Por isso so se testa de 01/08/2024 a 04/11/2026: dados que o modelo nunca viu.
Regra K1 exatamente como registada (tools/kronos_sombra.py), com os mesmos pesos (revisoes fixadas em producao).

Fases (cada uma num processo; a previsao corre em paralelo nos servidores do GitHub, uma tarefa por moeda e metade):
  dados <MOEDA> <pasta>            velas de 1 h do perpetuo global OKX desde 10/07/2024 (API publica)
  prever <MOEDA> <parte 0|1> <pasta> <kronos>   16 trajetorias em cada 4.o dia as 00:00 UTC
  avaliar <pasta>                  junta tudo e mede: LONG e SHORT separados, regimes, metades, referencias, custos

Avaliacao por SINAL (sem limites de conta): entrada no fecho da ultima vela (00:00 UTC), stop 1,5 x amplitude diaria
media de 14 dias, saida 24 h depois ou no stop (velas de 1 h; se a vela toca o stop, sai no stop + 0,1%).
Custos: 0,05% comissao + 0,05% deslize + 0,02% spread por lado (0,24% ida e volta); financiamento NAO incluido
(o historico publico de financiamento da OKX so cobre ~3 meses; fica assinalado).
Referencias no MESMO dia e moeda: (a) momento ingenuo (sinal do retorno de 24 h), (b) sempre LONG, (c) sempre SHORT,
(d) direcao ao acaso (media de 200 sorteios)."""
import json
import os
import random
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from tools import kronos_sombra as K  # noqa: E402
from tools import tfs_sombra as TS    # noqa: E402

INICIO = 1722470400        # 2024-08-01 00:00 UTC (pre-treino ate junho de 2024)
FIM = 1793836800           # 2026-11-04 00:00 UTC
PASSO = 4 * 86400
DADOS_DESDE = 1720569600   # 2024-07-10 (400 h de contexto antes do primeiro dia)
REVISOES = {"NeoQuasar/Kronos-Tokenizer-base": "0e0117387f39004a9016484a186a908917e22426",
            "NeoQuasar/Kronos-small": "901c26c1332695a2a8f243eb2f37243a37bea320"}
CUSTO = 2 * (0.0005 + 0.0005 + 0.0002)
H = 3600


def dias():
    return list(range(INICIO, FIM + 1, PASSO))


def baixar(moeda, pasta):
    out, depois = {}, ""
    for _ in range(400):
        d = TS._get(f"/api/v5/market/history-candles?instId={moeda}-USDT-SWAP&bar=1H&limit=100{depois}")
        if d is None:
            time.sleep(2); continue
        if not d:
            break
        for x in d:
            if len(x) > 8 and x[8] == "1":
                t = int(x[0]) // 1000
                out[t] = [t, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])]
        depois = f"&after={d[-1][0]}"
        if int(d[-1][0]) // 1000 <= DADOS_DESDE:
            break
        time.sleep(0.12)
    v = [out[t] for t in sorted(out)]
    json.dump(v, open(os.path.join(pasta, f"velas_{moeda}.json"), "w"))
    print(moeda, len(v), "velas", time.strftime("%F", time.gmtime(v[0][0])) if v else "-")


def _velas(pasta, moeda):
    v = json.load(open(os.path.join(pasta, f"velas_{moeda}.json")))
    return [{"t": x[0], "o": x[1], "h": x[2], "l": x[3], "c": x[4], "v": x[5]} for x in v]


def prever(moeda, parte, pasta, kronos):
    v = _velas(pasta, moeda)
    idx = {x["t"]: i for i, x in enumerate(v)}
    p = K.PrevisorKronos(kronos, revisoes=REVISOES)
    out = []
    meus = [d for i, d in enumerate(dias()) if i % 2 == int(parte)]
    for d in meus:
        i = idx.get(d - H)                                   # ultima vela fechada antes das 00:00
        if i is None or i < K.CONTEXTO:
            continue
        janela = v[i - K.CONTEXTO + 1: i + 1]
        if janela[0]["t"] != d - K.CONTEXTO * H:             # buracos nos dados: salta
            continue
        traj = p.trajetorias({moeda: janela}, semente=d % 100000)[moeda]
        out.append({"dia": d, "ultimo": janela[-1]["c"], "fechos": [round(x, 10) for x in traj]})
        print(moeda, time.strftime("%F", time.gmtime(d)), file=sys.stderr, flush=True)
    json.dump(out, open(os.path.join(pasta, f"prev_{moeda}_{parte}.json"), "w"))


# ---------- avaliacao ----------
def resultado(v, i0, lado, stop_pct):
    """R liquido de uma operacao: entra no fecho da vela i0, sai 24 h depois ou no stop."""
    e = v[i0]["c"]
    s = 1 if lado == "LONG" else -1
    stop = e * (1 - s * stop_pct)
    fim = v[i0 + 1: i0 + 25]
    if len(fim) < 24:
        return None
    for x in fim:
        if (lado == "LONG" and x["l"] <= stop) or (lado == "SHORT" and x["h"] >= stop):
            saida = (min(stop, x["o"]) * (1 - 0.001)) if lado == "LONG" else (max(stop, x["o"]) * (1 + 0.001))
            break
    else:
        saida = fim[-1]["c"]
    return (s * (saida / e - 1) - CUSTO) / stop_pct


def metricas(R):
    R = [r for r in R if r is not None]
    if not R:
        return {"n": 0}
    g = sum(r for r in R if r > 0); p = -sum(r for r in R if r < 0)
    eq = pico = queda = 0.0
    for r in R:
        eq += r; pico = max(pico, eq); queda = max(queda, pico - eq)
    rs = random.Random(1)
    medias = sorted(st.mean(rs.choice(R) for _ in R) for _ in range(2000))
    return {"n": len(R), "media": round(st.mean(R), 3), "pf": round(g / p, 2) if p else None,
            "acerto": round(100 * sum(r > 0 for r in R) / len(R)), "queda_R": round(queda, 1),
            "ic90": [round(medias[100], 3), round(medias[1899], 3)], "p_media_le_0": round(sum(m <= 0 for m in medias) / 2000, 3)}


def regimes(pasta):
    """Regime do BTC por dia (independente do Kronos): retorno de 90 dias > +15% subida, < -15% descida, resto lateral."""
    v = _velas(pasta, "BTC")
    fecho_dia = {}
    for x in v:
        if x["t"] % 86400 == 82800:
            fecho_dia[x["t"] + H] = x["c"]
    out = {}
    for d in dias():
        a, b = fecho_dia.get(d), fecho_dia.get(d - 90 * 86400)
        out[d] = None if not (a and b) else ("subida" if a / b - 1 > 0.15 else "descida" if a / b - 1 < -0.15 else "lateral")
    return out


def avaliar(pasta):
    reg = regimes(pasta) if os.path.exists(os.path.join(pasta, "velas_BTC.json")) else {}
    linhas = []
    for m in K.UNIVERSO:
        try:
            v = _velas(pasta, m)
        except FileNotFoundError:
            continue
        idx = {x["t"]: i for i, x in enumerate(v)}
        prevs = []
        for parte in (0, 1):
            f = os.path.join(pasta, f"prev_{m}_{parte}.json")
            if os.path.exists(f):
                prevs += json.load(open(f))
        for p in prevs:
            i = idx.get(p["dia"] - H)
            if i is None:
                continue
            lado, f, acordo = K.sinal(p["ultimo"], p["fechos"])
            amp = K.amplitude_diaria(v[: i + 1])
            if not amp:
                continue
            sp = K.STOP_X * amp
            mom = v[i]["c"] / v[i - 24]["c"] - 1
            media400 = st.mean(x["c"] for x in v[i - 399: i + 1])
            real24 = v[i + 24]["c"] / v[i]["c"] - 1 if i + 24 < len(v) else None
            fd = [x["c"] for x in v[: i + 1] if x["t"] % 86400 == 82800]      # fechos diarios ate hoje
            tfs = None
            if len(fd) >= 200:
                s_ = sum(fd[-1] > st.mean(fd[-n:]) for n in (20, 50, 100, 200))
                tfs = "SHORT" if s_ <= 1 else ("fora" if s_ >= 3 else "neutro")
            linhas.append({"m": m, "dia": p["dia"], "lado": lado, "f": f, "acordo": acordo, "regime": reg.get(p["dia"]),
                           "tfshort": tfs,
                           "R": resultado(v, i, lado, sp) if lado else None,
                           "R_long": resultado(v, i, "LONG", sp), "R_short": resultado(v, i, "SHORT", sp),
                           "R_mom": resultado(v, i, "LONG" if mom > 0 else "SHORT", sp),
                           "dist_media": v[i]["c"] / media400 - 1, "real24": real24})
    json.dump(linhas, open(os.path.join(pasta, "linhas.json"), "w"))
    return relatorio(linhas)


def relatorio(L):
    out = []
    P = lambda s: out.append(s)  # noqa: E731
    P(f"KRONOS K1 FORA DA AMOSTRA (01/08/2024 a 04/11/2026, cada 4.o dia, {len({x['m'] for x in L})} moedas, "
      f"{len(L)} previsoes moeda-dia)")
    sinais = [x for x in L if x["lado"]]
    P(f"Sinais: {len(sinais)} de {len(L)} ({100 * len(sinais) / max(1, len(L)):.0f}%) | LONG {sum(x['lado'] == 'LONG' for x in sinais)} "
      f"| SHORT {sum(x['lado'] == 'SHORT' for x in sinais)}")
    # enviesamento
    fs = [x["f"] for x in L]
    P(f"Previsao f: media {100 * st.mean(fs):+.2f}% mediana {100 * st.median(fs):+.2f}% | realizado 24 h: media "
      f"{100 * st.mean(x['real24'] for x in L if x['real24'] is not None):+.2f}%")
    import math
    def corr(a, b):
        ma, mb = st.mean(a), st.mean(b)
        sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
        return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0
    P(f"Correlacao f vs distancia a media de 400 h: {corr(fs, [x['dist_media'] for x in L]):+.2f} "
      f"(muito negativa = o modelo preve regresso a media)")
    LR = [x for x in L if x["real24"] is not None]
    P(f"Correlacao f vs retorno real de 24 h: {corr([x['f'] for x in LR], [x['real24'] for x in LR]):+.3f}")
    acerto = [((x["f"] > 0) == (x["real24"] > 0)) for x in LR if x["f"]]
    P(f"Acerto de direcao (todas as previsoes): {100 * st.mean(acerto):.1f}% em {len(acerto)}")
    P("")
    P("Desempenho por SINAL (R liquido; custos 0,24% ida e volta; sem financiamento):")
    def bloco(nome, xs):
        k = metricas([x["R"] for x in xs]); mo = metricas([x["R_mom"] for x in xs])
        al = metricas([x["R_long"] for x in xs]); sh = metricas([x["R_short"] for x in xs])
        P(f"  {nome:32s} Kronos {k}")
        if k["n"]:
            P(f"  {'':32s} mesmos dias: momento {mo.get('media')} | sempre LONG {al.get('media')} | sempre SHORT {sh.get('media')}")
    bloco("TODOS", sinais)
    bloco("LONG", [x for x in sinais if x["lado"] == "LONG"])
    bloco("SHORT", [x for x in sinais if x["lado"] == "SHORT"])
    for g in ("subida", "lateral", "descida"):
        for lado in ("LONG", "SHORT"):
            bloco(f"{lado} em {g}", [x for x in sinais if x["lado"] == lado and x["regime"] == g])
    meio = 1759276800   # 2025-10-01
    bloco("1.a metade (ate 09/2025)", [x for x in sinais if x["dia"] < meio])
    bloco("2.a metade (desde 10/2025)", [x for x in sinais if x["dia"] >= meio])
    # acaso
    rs = random.Random(7)
    medias = []
    for _ in range(200):
        medias.append(st.mean(x["R_long"] if rs.random() < 0.5 else x["R_short"] for x in sinais
                              if x["R_long"] is not None and x["R_short"] is not None))
    medias.sort()
    P(f"  Direcao ao acaso nos mesmos dias e moedas: media {st.mean(medias):+.3f} (p95 {medias[189]:+.3f})")
    P("")
    P("Concentracao e diversificacao:")
    por_dia = {}
    for x in sinais:
        por_dia.setdefault(x["dia"], []).append(x["lado"])
    mesmos = [max(l.count("LONG"), l.count("SHORT")) / len(l) for l in por_dia.values() if len(l) >= 2]
    P(f"  Dias com sinal: {len(por_dia)}; sinais por dia: media {st.mean(len(l) for l in por_dia.values()):.1f}; "
      f"fracao na mesma direcao: {100 * st.mean(mesmos):.0f}%")
    tf = [x for x in sinais if x["tfshort"]]
    if tf:
        P(f"  Sobreposicao com o TF-SHORT ({len(tf)} sinais com historia de 200 dias): Kronos LONG com TF-SHORT a dar SHORT "
          f"{sum(x['lado'] == 'LONG' and x['tfshort'] == 'SHORT' for x in tf)}; Kronos SHORT com TF-SHORT SHORT "
          f"{sum(x['lado'] == 'SHORT' and x['tfshort'] == 'SHORT' for x in tf)}")
        bloco("Kronos LONG contra TF-SHORT SHORT", [x for x in tf if x["lado"] == "LONG" and x["tfshort"] == "SHORT"])
        bloco("Kronos LONG fora de TF-SHORT", [x for x in tf if x["lado"] == "LONG" and x["tfshort"] != "SHORT"])
    return "\n".join(out)


def correlacoes(pasta, moedas=("XRP", "OP", "FIL", "BTC"), dias_=30):
    """Correlacao dos retornos de 1 h nos ultimos `dias_` dias (posicoes abertas em sombra)."""
    import math
    R = {}
    for m in moedas:
        v = _velas(pasta, m)[-24 * dias_ - 1:]
        R[m] = {v[i]["t"]: v[i]["c"] / v[i - 1]["c"] - 1 for i in range(1, len(v))}
    ts = sorted(set.intersection(*[set(r) for r in R.values()]))
    def c(a, b):
        x = [R[a][t] for t in ts]; y = [R[b][t] for t in ts]
        mx, my = st.mean(x), st.mean(y)
        return sum((p - mx) * (q - my) for p, q in zip(x, y)) / math.sqrt(sum((p - mx) ** 2 for p in x) * sum((q - my) ** 2 for q in y))
    return {f"{a}-{b}": round(c(a, b), 2) for i, a in enumerate(moedas) for b in moedas[i + 1:]}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "dados":
        baixar(a[1], a[2])
    elif a[0] == "prever":
        prever(a[1], a[2], a[3], a[4])
    elif a[0] == "avaliar":
        print(avaliar(a[1]))
        print("Correlacao 1 h, ultimos 30 dias:", correlacoes(a[1]))
