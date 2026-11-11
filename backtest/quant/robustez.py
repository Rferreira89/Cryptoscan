"""(11/11) Robustez estatistica que faltava ao modulo quant: correcao de Holm, testes da media em R com dependencia,
bootstrap por blocos, walk-forward sem fuga de informacao, estabilidade temporal, robustez entre ativos e regimes, e
sensibilidade entre configuracoes vizinhas. Complementa (nao duplica) dsr.py, pbo.py e residual.py.

Tudo e biblioteca padrao. Operacoes: dicionarios com "R", "t_entrada" e, quando ha, "t_saida", "ativo".
Nada daqui decide ou liga estrategias: so mede.

Dependencia entre operacoes: operacoes da mesma estrategia abertas no mesmo dia nao sao independentes (o panico
apanha muitas moedas ao mesmo tempo). Por isso os testes da media usam por omissao a SOMA DIARIA de R (uma
observacao por dia com operacoes), e o bootstrap reamostra blocos de dias seguidos."""
import math
import random

from backtest.quant import estatistica as E

DIA = 86400


def holm(pvalores, alfa=0.05):
    """Correcao de Holm-Bonferroni. pvalores: {nome: p}. Devolve {nome: {"p", "p_ajustado", "rejeita"}}."""
    itens = sorted(pvalores.items(), key=lambda kv: kv[1])
    m = len(itens)
    out, acum, parou = {}, 0.0, False
    for i, (nome, p) in enumerate(itens):
        aj = min(1.0, max(acum, (m - i) * p))
        acum = aj
        rej = (not parou) and p <= alfa / (m - i)
        if not rej:
            parou = True
        out[nome] = {"p": p, "p_ajustado": round(aj, 6), "rejeita": rej}
    return out


def por_dia(ops, campo="R"):
    """Soma de R por dia de entrada (uma observacao por dia com operacoes)."""
    d = {}
    for o in ops:
        if o.get(campo) is None or not o.get("t_entrada"):
            continue
        k = int(o["t_entrada"] // DIA)
        d[k] = d.get(k, 0.0) + float(o[campo])
    return [d[k] for k in sorted(d)]


def teste_media(xs, unilateral=True):
    """t de Student para media > 0 (unilateral) ou != 0. Devolve (media, t, p, n)."""
    n = len(xs)
    if n < 3:
        return None, None, None, n
    m = E.media(xs)
    dp = E.desvio(xs)
    if dp == 0:
        return m, None, 0.0 if m > 0 else 1.0, n
    t = m / (dp / math.sqrt(n))
    cdf = E.t_cdf(t, n - 1)
    p = 1 - cdf if unilateral else 2 * min(cdf, 1 - cdf)
    return m, t, p, n


def bootstrap_blocos(xs, n_boot=2000, bloco=None, semente=11, nivel=0.95):
    """Bootstrap circular por blocos da media. Devolve media, IC e P(media <= 0) nas reamostras."""
    n = len(xs)
    if n < 5:
        return {"n": n, "media": E.media(xs) if xs else None, "ic": None, "p_nao_positivo": None}
    b = bloco or max(1, int(round(n ** (1 / 3))))
    rnd = random.Random(semente)
    medias = []
    for _ in range(n_boot):
        amostra = []
        while len(amostra) < n:
            i = rnd.randrange(n)
            amostra += [xs[(i + j) % n] for j in range(b)]
        medias.append(sum(amostra[:n]) / n)
    medias.sort()
    lo = medias[int((1 - nivel) / 2 * n_boot)]
    hi = medias[min(n_boot - 1, int((1 + nivel) / 2 * n_boot))]
    return {"n": n, "bloco": b, "media": round(E.media(xs), 5), "ic": [round(lo, 5), round(hi, 5)],
            "p_nao_positivo": round(sum(1 for m in medias if m <= 0) / n_boot, 4)}


def sem_melhores(rs, frac=0.05):
    """Media sem as frac melhores operacoes (dependencia de poucos ganhos grandes)."""
    if not rs:
        return None
    k = int(len(rs) * frac)
    s = sorted(rs)
    resto = s[:len(s) - k] if k else s
    return round(sum(resto) / len(resto), 5)


def estabilidade(ops, k=4):
    """Media de R em k blocos de tempo consecutivos com o mesmo numero de operacoes; quantos sao positivos."""
    xs = sorted((o for o in ops if o.get("R") is not None), key=lambda o: o["t_entrada"])
    if len(xs) < 2 * k:
        return {"k": k, "blocos": [], "positivos": None}
    tam = len(xs) // k
    bl = []
    for i in range(k):
        parte = xs[i * tam:(i + 1) * tam] if i < k - 1 else xs[i * tam:]
        bl.append({"de": parte[0]["t_entrada"], "ate": parte[-1]["t_entrada"], "n": len(parte),
                   "media_r": round(E.media([o["R"] for o in parte]), 4)})
    return {"k": k, "blocos": bl, "positivos": sum(1 for b in bl if b["media_r"] > 0)}


def por_grupo(ops, chave, minimo=5):
    """Media de R por grupo (ativo, regime...); fracao de grupos positivos e concentracao do resultado."""
    g = {}
    for o in ops:
        if o.get("R") is None:
            continue
        g.setdefault(o.get(chave) or "?", []).append(o["R"])
    validos = {k: v for k, v in g.items() if len(v) >= minimo}
    total = sum(sum(v) for v in g.values())
    melhores = sorted(((sum(v), k) for k, v in g.items()), reverse=True)
    top = melhores[:max(1, len(melhores) // 10)]
    return {"grupos": len(g), "grupos_com_minimo": len(validos),
            "positivos_pct": round(100 * sum(1 for v in validos.values() if E.media(v) > 0) / len(validos), 1) if validos else None,
            "soma_r_total": round(total, 3), "soma_r_sem_10pct_melhores_grupos": round(total - sum(s for s, _ in top), 3),
            "por_grupo": {k: {"n": len(v), "media_r": round(E.media(v), 4)} for k, v in sorted(g.items())}}


def regime_btc(btc_4h, t, janela=300):
    """'subida' / 'descida' pela media de ~50 dias (300 velas de 4H) do BTC, usando so velas ATE t (sem futuro)."""
    import bisect
    ts = [x[0] for x in btc_4h]
    k = bisect.bisect_right(ts, t) - 1
    if k < janela:
        return None
    m = sum(x[1] for x in btc_4h[k - janela + 1:k + 1]) / janela
    return "subida" if btc_4h[k][1] > m else "descida"


def marcar_regime(ops, btc_4h):
    return [{**o, "regime": regime_btc(btc_4h, o["t_entrada"])} for o in ops]


def walk_forward(configs, treino_dias=365, teste_dias=90, criterio=None, inicio=None, fim=None, minimo_treino=20):
    """Walk-forward ancorado em janelas deslizantes. configs: {nome: [ops]}. Em cada passo escolhe, SO com as
    operacoes FECHADAS antes do inicio do teste (t_saida < inicio), a configuracao com melhor criterio e regista o
    resultado dela no periodo de teste. Devolve as operacoes fora da amostra e as escolhas."""
    criterio = criterio or (lambda rs: E.media(rs) - (E.desvio(rs) / math.sqrt(len(rs)) if len(rs) > 1 else 0))
    todas = [o for v in configs.values() for o in v]
    if not todas:
        return {"passos": [], "oos": []}
    t0 = inicio or min(o["t_entrada"] for o in todas)
    t1 = fim or max(o["t_entrada"] for o in todas)
    passos, oos = [], []
    a = t0 + treino_dias * DIA
    while a < t1:
        b = a + teste_dias * DIA
        notas = {}
        for nome, ops in configs.items():
            tr = [o["R"] for o in ops if a - treino_dias * DIA <= o["t_entrada"] and (o.get("t_saida") or o["t_entrada"]) < a]
            if len(tr) >= minimo_treino:
                notas[nome] = criterio(tr)
        if notas:
            esc = max(notas, key=notas.get)
            te = [o for o in configs[esc] if a <= o["t_entrada"] < b]
            oos += [{**o, "config": esc} for o in te]
            passos.append({"teste_de": a, "teste_ate": b, "escolhida": esc, "nota_treino": round(notas[esc], 4),
                           "n_teste": len(te), "media_teste": round(E.media([o["R"] for o in te]), 4) if te else None})
        else:
            passos.append({"teste_de": a, "teste_ate": b, "escolhida": None, "n_teste": 0})
        a = b
    return {"passos": passos, "oos": oos}


def sensibilidade(variantes):
    """variantes: {nome: [R]} de configuracoes vizinhas (um parametro a variar). Frageis quando o sinal da media muda
    entre vizinhas ou a amplitude das medias e maior do que a propria media."""
    medias = {k: E.media(v) for k, v in variantes.items() if v}
    if len(medias) < 2:
        return {"medias": medias, "fragil": None}
    sinais = {m > 0 for m in medias.values()}
    amp = max(medias.values()) - min(medias.values())
    centro = abs(E.media(list(medias.values())))
    return {"medias": {k: round(v, 4) for k, v in medias.items()}, "muda_de_sinal": len(sinais) > 1,
            "amplitude": round(amp, 4), "fragil": len(sinais) > 1 or amp > centro}


def avaliar(ops, btc_4h=None, n_boot=2000):
    """Bateria completa para uma estrategia num ambiente (nunca misturar ambientes)."""
    rs = [o["R"] for o in ops if o.get("R") is not None]
    diario = por_dia(ops)
    m, t, p, n = teste_media(diario)
    out = {"n_operacoes": len(rs), "n_dias": len(diario), "media_r": round(E.media(rs), 4) if rs else None,
           "media_r_sem_5pct_melhores": sem_melhores(rs),
           "teste_diario": {"media": None if m is None else round(m, 4), "t": None if t is None else round(t, 3),
                            "p_unilateral": None if p is None else round(p, 5), "n": n},
           "bootstrap_diario": bootstrap_blocos(diario, n_boot=n_boot),
           "estabilidade": estabilidade(ops), "ativos": por_grupo(ops, "ativo") if any("ativo" in o for o in ops) else None}
    if btc_4h:
        out["regimes"] = por_grupo(marcar_regime(ops, btc_4h), "regime", minimo=10)
    return out
