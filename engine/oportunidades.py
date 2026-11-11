"""(11/11) Global Opportunity Hunter — classificacao de oportunidades em SOMBRA. Sem autoridade de execucao: nao
envia ordens, nao cria sinais para os executores, nao muda estrategias. So regista e mede.

Fontes gratuitas que o CryptoScan ja recolhe (verificadas a 11/11; ver docs no fim):
  derivados.json (ramo data)     21 moedas, de hora a hora desde 20/10: preco, OI, funding, long/short, liquidacoes,
                                 variacao do OI em 24 h, basis
  dados-novos (CSV diario)       164 moedas desde 05/11: OHLC, volume, preco X-Perp e global, funding X-Perp, OI
  history (ramo)                 velas de 4H de ~70 moedas desde 2021 (so precos e volume)
  state.json (ramo data)         regime de cada moeda da Bybit
Fontes que NAO existem de graca nesta infraestrutura: fluxo de ordens (trades a trades) historico, profundidade
historica do livro (so a partir de agora, tools/recolha_liquidez_okx.py), liquidacoes para alem das 21 moedas.

Cada detetor devolve (forca 0-1, direcao "LONG"/"SHORT"/None, motivo) ou None. A direcao e uma HIPOTESE, nao uma
entrada. A classificacao junta detetores, qualidade dos dados, risco, custos, invalidacao, expectativa e confianca.
Expectativa e confianca vem SO de evidencia medida (`evidencia`: IC por caracteristica, de estudo historico ou da
propria sombra); sem evidencia suficiente ficam "desconhecida" / "sem evidencia". Nada e inventado.

Avaliacao da sombra: `avaliar` mede, para cada caracteristica, o IC de postos (Spearman) transversal por dia entre o
valor da caracteristica e o retorno seguinte (ideia do IC/RankIC do Qlib, reimplementada) e o t do IC medio."""
import math

CUSTO_IDA_VOLTA = 0.0005 * 2 + 0.001        # taker nos dois lados + deslize no stop (estimativa, como no mapa)
MIN_DIAS_IC = 30                            # dias de IC para haver "confianca"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _z(x, hist):
    xs = [v for v in hist if v is not None]
    if x is None or len(xs) < 10:
        return None
    m = sum(xs) / len(xs)
    dp = math.sqrt(sum((v - m) ** 2 for v in xs) / (len(xs) - 1))
    return None if dp == 0 else (x - m) / dp


def _pct(x, hist):
    xs = [v for v in hist if v is not None]
    if x is None or len(xs) < 10:
        return None
    # postos medios nos empates: um funding igual ao valor por omissao (ex.: 0,01%) que se repete nao e "extremo"
    return (sum(1 for v in xs if v < x) + 0.5 * sum(1 for v in xs if v == x)) / len(xs)


# ---------- detetores (cada um olha so para dados ATE ao instante avaliado) ----------

def volume_anomalo(a):
    z = _z(a.get("log_volume"), a.get("log_volume_hist") or [])
    if z is None or abs(z) < 2.5:
        return None
    return min(1.0, abs(z) / 5), None, f"volume {z:+.1f} desvios do normal de 20 dias"


def oi_variacao(a):
    d = _f(a.get("oi_chg_24h"))
    r = _f(a.get("ret_24h"))
    if d is None or abs(d) < 0.08:
        return None
    if r is not None and r < -0.03 and d > 0:
        return min(1.0, d / 0.3), "SHORT", f"OI +{100 * d:.0f}% com o preco a cair {100 * r:.1f}% (shorts novos)"
    if r is not None and r < -0.03 and d < 0:
        return min(1.0, -d / 0.3), "LONG", f"OI {100 * d:.0f}% com o preco a cair (desalavancagem)"
    if r is not None and r > 0.03 and d > 0:
        return min(1.0, d / 0.3), "LONG", f"OI +{100 * d:.0f}% com o preco a subir (dinheiro novo)"
    if r is not None and r > 0.03 and d < 0:
        return min(1.0, -d / 0.3), "SHORT", f"subida com OI {100 * d:.0f}% (sem dinheiro novo)"
    return None


def funding_extremo(a):
    p = _pct(_f(a.get("funding")), a.get("funding_hist") or [])
    if p is None or 0.05 < p < 0.95:
        return None
    if p <= 0.05:
        return (0.05 - p) / 0.05 * 0.5 + 0.5, "LONG", f"funding no percentil {100 * p:.0f} (shorts a pagar)"
    return (p - 0.95) / 0.05 * 0.5 + 0.5, "SHORT", f"funding no percentil {100 * p:.0f} (longs a pagar)"


def long_short(a):
    z = _z(_f(a.get("ls")), a.get("ls_hist") or [])
    if z is None or abs(z) < 2:
        return None
    return min(1.0, abs(z) / 4), ("SHORT" if z > 0 else "LONG"), f"long/short {z:+.1f} desvios (posicionamento extremo)"


def liquidacoes(a):
    lo, sh = _f(a.get("liq_long")), _f(a.get("liq_short"))
    hist = [v for v in (a.get("liq_total_hist") or []) if v is not None]
    if lo is None or sh is None or len(hist) < 10:
        return None
    tot = lo + sh
    lim = sorted(hist)[int(0.95 * (len(hist) - 1))]
    if tot <= lim or tot <= 0:
        return None
    lado = "LONG" if lo > sh else "SHORT"           # longs liquidados em massa -> possivel exaustao vendedora
    return min(1.0, tot / (2 * lim)) if lim else 1.0, lado, f"liquidacoes acima do p95 ({'longs' if lo > sh else 'shorts'} {100 * max(lo, sh) / tot:.0f}%)"


def aceleracao(a):
    r, atr = _f(a.get("ret_24h")), _f(a.get("atr_pct"))
    if r is None or not atr:
        return None
    k = r / atr
    if abs(k) < 2.5:
        return None
    return min(1.0, abs(k) / 5), ("LONG" if k > 0 else "SHORT"), f"movimento de 24 h = {k:+.1f} ATR"


def relativo_btc(a):
    r, rb = _f(a.get("ret_24h")), _f(a.get("btc_ret_24h"))
    beta = _f(a.get("beta_btc")) or 1.0
    atr = _f(a.get("atr_pct"))
    if r is None or rb is None or not atr:
        return None
    res = r - beta * rb
    if abs(res) < 2 * atr:
        return None
    return min(1.0, abs(res) / (4 * atr)), ("LONG" if res > 0 else "SHORT"), f"residual face ao BTC {100 * res:+.1f}% (beta {beta:.2f})"


def divergencia(a):
    r, v = _f(a.get("ret_24h")), _f(a.get("vol_ratio"))
    if r is None or v is None:
        return None
    if abs(r) > 0.05 and v < 0.6:
        return 0.5, ("SHORT" if r > 0 else "LONG"), f"preco {100 * r:+.1f}% com volume a {100 * v:.0f}% do normal (sem atividade)"
    return None


def liquidez(a):
    s, sh = _f(a.get("spread_bps")), a.get("spread_hist") or []
    z = _z(s, sh)
    if z is None or z < 3:
        return None
    return min(1.0, z / 6), None, f"spread {s:.0f} pb ({z:+.1f} desvios): liquidez a piorar"


def desacoplamento(a):
    c, ch = _f(a.get("corr_btc_7d")), _f(a.get("corr_btc_60d"))
    if c is None or ch is None or ch < 0.5:
        return None
    if ch - c < 0.4:
        return None
    return min(1.0, (ch - c) / 0.8), None, f"correlacao com o BTC caiu de {ch:.2f} para {c:.2f}"


def reversao_ou_continuacao(a):
    q3, rg = _f(a.get("ret_3d")), a.get("regime")
    if q3 is None:
        return None
    if q3 <= -0.10 and rg not in ("STRONG BEAR",):
        return min(1.0, -q3 / 0.25), "LONG", f"queda de 3 dias {100 * q3:.0f}% (reversao possivel; regime {rg or '?'})"
    if q3 >= 0.10 and rg in ("BULL", "STRONG BULL"):
        return min(1.0, q3 / 0.25), "LONG", f"subida de 3 dias {100 * q3:.0f}% em regime {rg} (continuacao possivel)"
    return None


DETETORES = {"volume": volume_anomalo, "oi": oi_variacao, "funding": funding_extremo, "long_short": long_short,
             "liquidacoes": liquidacoes, "aceleracao": aceleracao, "relativo_btc": relativo_btc,
             "divergencia": divergencia, "liquidez": liquidez, "desacoplamento": desacoplamento,
             "reversao_continuacao": reversao_ou_continuacao}

CAMPOS_ESPERADOS = ("preco", "ret_24h", "ret_3d", "atr_pct", "log_volume", "funding", "oi_chg_24h", "ls", "spread_bps")


def qualidade(a):
    """Fracao dos campos esperados presentes, idade do dado e fontes. 'baixa' quando falta metade ou mais."""
    pres = [c for c in CAMPOS_ESPERADOS if a.get(c) is not None]
    frac = len(pres) / len(CAMPOS_ESPERADOS)
    idade = _f(a.get("idade_s"))
    nivel = "alta" if frac >= 0.75 and (idade is None or idade < 3 * 3600) else "media" if frac >= 0.5 else "baixa"
    return {"nivel": nivel, "campos": round(frac, 2), "em_falta": [c for c in CAMPOS_ESPERADOS if c not in pres],
            "fontes": sorted(a.get("fontes") or []), "idade_h": None if idade is None else round(idade / 3600, 1)}


def classificar(a, evidencia=None):
    """Registo explicavel de uma oportunidade (ou None se nenhum detetor disparou)."""
    sinais = []
    for nome, fn in DETETORES.items():
        try:
            r = fn(a)
        except (TypeError, ValueError, ZeroDivisionError):
            r = None
        if r:
            sinais.append({"detetor": nome, "forca": round(r[0], 3), "direcao": r[1], "motivo": r[2]})
    if not sinais:
        return None
    votos = {"LONG": 0.0, "SHORT": 0.0}
    for s in sinais:
        if s["direcao"]:
            votos[s["direcao"]] += s["forca"]
    direcao = None
    if votos["LONG"] or votos["SHORT"]:
        direcao = "LONG" if votos["LONG"] > votos["SHORT"] else "SHORT"
        if min(votos.values()) > 0.5 * max(votos.values()):
            direcao = "conflito"
    atr = _f(a.get("atr_pct"))
    preco = _f(a.get("preco"))
    spread = (_f(a.get("spread_bps")) or 0) / 1e4
    custo = CUSTO_IDA_VOLTA + spread
    inval = None
    if preco and atr and direcao in ("LONG", "SHORT"):
        inval = round(preco * (1 - 2 * atr) if direcao == "LONG" else preco * (1 + 2 * atr), 10)
    q = qualidade(a)
    esp, conf = expectativa(sinais, evidencia)
    return {"ativo": a.get("ativo"), "t": a.get("t"), "direcao_potencial": direcao, "regime": a.get("regime"),
            "sinais": sinais, "qualidade_dados": q,
            "risco": {"atr_pct": atr, "stop_2atr_pct": round(2 * atr * 100, 2) if atr else None,
                      "liquidez_spread_bps": _f(a.get("spread_bps"))},
            "custos_estimados_pct": round(100 * custo, 3),
            "custos_em_r_com_stop_2atr": round(custo / (2 * atr), 3) if atr else None,
            "invalidacao": inval, "expectativa_estimada": esp, "confianca_estatistica": conf,
            "motivo": "; ".join(s["motivo"] for s in sinais), "autoridade": "nenhuma (sombra)"}


def expectativa(sinais, evidencia):
    """Expectativa e confianca SO de evidencia medida. evidencia: {detetor: {"ic_na_direcao", "t", "dias",
    "liquido_pct", "fonte"}}, em que ic_na_direcao > 0 quer dizer que a direcao que o detetor propoe acertou em media
    (IC de postos com o sinal ja ajustado a direcao) e liquido_pct e o resultado medio por operacao depois de custos
    de uma carteira de quintis. 'positiva' exige as duas coisas: IC significativo na direcao E liquido > 0."""
    if not evidencia:
        return "desconhecida", "sem evidencia"
    usados = [(s, evidencia.get(s["detetor"])) for s in sinais if evidencia.get(s["detetor"])]
    usados = [(s, e) for s, e in usados if (e.get("dias") or 0) >= MIN_DIAS_IC]
    if not usados:
        return "desconhecida", "sem evidencia (menos de 30 dias de IC)"
    txt = "; ".join(f"{s['detetor']}: IC na direcao {e['ic_na_direcao']:+.3f} (t {e['t']:+.1f}, {e['dias']} d), "
                    f"liquido {e.get('liquido_pct')}% ({e.get('fonte', '?')})" for s, e in usados)
    sig = [(s, e) for s, e in usados if abs(e.get("t") or 0) >= 2]
    if not sig:
        return "sem vantagem medida", txt
    a_favor = [(s, e) for s, e in sig if e["ic_na_direcao"] > 0]
    if a_favor and all((e.get("liquido_pct") or -1) > 0 for _, e in a_favor) and len(a_favor) == len(sig):
        return "positiva com evidencia", txt
    if a_favor:
        return "IC a favor mas sem resultado liquido positivo", txt
    return "contra a direcao proposta", txt


# ---------- avaliacao (sombra ou historico) ----------

def _postos(xs):
    ordem = sorted(range(len(xs)), key=lambda i: xs[i])
    p = [0.0] * len(xs)
    i = 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and xs[ordem[j + 1]] == xs[ordem[i]]:
            j += 1
        for k in range(i, j + 1):
            p[ordem[k]] = (i + j) / 2
        i = j + 1
    return p


def spearman(x, y):
    if len(x) < 5:
        return None
    px, py = _postos(x), _postos(y)
    mx, my = sum(px) / len(px), sum(py) / len(py)
    num = sum((a - mx) * (b - my) for a, b in zip(px, py))
    den = math.sqrt(sum((a - mx) ** 2 for a in px) * sum((b - my) ** 2 for b in py))
    return num / den if den else None


def ic_diario(linhas, caracteristica, alvo="ret_seguinte", minimo=8):
    """linhas: [{dia, ativo, <caracteristica>, <alvo>}]. IC de postos transversal por dia."""
    por = {}
    for l in linhas:
        if l.get(caracteristica) is None or l.get(alvo) is None:
            continue
        por.setdefault(l["dia"], []).append((l[caracteristica], l[alvo]))
    ics = []
    for d in sorted(por):
        v = por[d]
        if len(v) >= minimo:
            r = spearman([a for a, _ in v], [b for _, b in v])
            if r is not None:
                ics.append((d, r))
    return ics


def resumo_ic(ics):
    xs = [r for _, r in ics]
    n = len(xs)
    if n < 3:
        return {"dias": n, "ic_medio": None, "t": None}
    m = sum(xs) / n
    dp = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    meio = n // 2
    m1 = sum(xs[:meio]) / meio if meio else None
    m2 = sum(xs[meio:]) / (n - meio)
    return {"dias": n, "ic_medio": round(m, 4), "t": round(m / (dp / math.sqrt(n)), 2) if dp else None,
            "ic_1a_metade": None if m1 is None else round(m1, 4), "ic_2a_metade": round(m2, 4),
            "positivos_pct": round(100 * sum(1 for x in xs if x > 0) / n, 1)}
