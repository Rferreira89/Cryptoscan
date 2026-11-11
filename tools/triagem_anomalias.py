"""Triagem EXPLORATORIA de anomalias por familia (auditoria de 2026-11-11).

Nao valida nada. Serve para o agente deixar de inventar combinacoes de
indicadores de 4H e passar a procurar primeiro um comportamento do mercado que
exista nos dados, com margem sobre os custos, e so depois escrever uma ficha.

Regras:
- so usa dados ANTES de CORTE (inicio da reserva em vigor no dia da
  auditoria). Uma vela, um financiamento ou um retorno futuro que acabe depois
  do corte nunca entra (recortar() e _fwd() garantem-no; ha teste);
- cada celula (sinal x horizonte) e um teste; os p-valores sao corrigidos por
  Holm sobre TODAS as celulas da triagem;
- o que conta para o Rui e a margem LIQUIDA de uma compra em spot na Bybit UE:
  retorno bruto medio do grupo comprado menos 0,7% por ida e volta
  (0,25% de comissao + 0,1% de deslize por lado);
- os dias sao amostrados sem sobreposicao (de h em h dias) e o desvio usa a
  media do grupo por dia, por isso moedas do mesmo dia contam uma vez;
- o universo e o do ramo history (moedas listadas hoje): ha vies de
  sobrevivencia, que favorece as compras. Uma anomalia que so aparece aqui
  ainda tem de ser confirmada com as delistadas.

Saida: lista de celulas com familia, sinal, horizonte, n de dias, retorno
bruto, excesso sobre o universo, margem liquida, t, p e p de Holm. O que
passar Holm com margem liquida positiva e um PONTO DE PARTIDA para uma ficha
(tools/registo_hipoteses.py), validada so em dados posteriores ao registo.

Uso: python -m tools.triagem_anomalias <pasta_history> [saida.json]
"""
import gzip
import json
import math
import os
import sys

from engine import backtest as B
from tools import estatistica_multipla as E

DAY, H4 = 86400, 4 * 3600
CORTE = 1778198400               # 2026-05-08 00:00 UTC: inicio da reserva de 2026-11-11
CUSTO_IDA_VOLTA = 0.007          # 2 x (0,25% + 0,1%)
QUANTIL = 0.2
MIN_MOEDAS = 15


class Contaminacao(RuntimeError):
    pass


def recortar(bars, corte=CORTE):
    """So velas de 4H que FECHAM antes do corte."""
    return {a: [x for x in c if x["t"] + H4 <= corte] for a, c in bars.items()}


def carregar_funding(pasta, corte=CORTE):
    out = {}
    d = os.path.join(pasta, "funding")
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if fn.endswith(".csv.gz"):
            with gzip.open(os.path.join(d, fn), "rt") as f:
                rows = [l.strip().split(",") for l in f if l.strip()]
            out[fn[:-7]] = [(int(r[0]), float(r[1])) for r in rows if int(r[0]) < corte]
    return out


def painel(bars, funding=None):
    """{moeda: {dia: {o, c, v_usd, tb_frac, fund}}} de dias completos."""
    out = {}
    for a, c4 in bars.items():
        dd = {}
        for x in c4:
            k = x["t"] // DAY
            r = dd.setdefault(k, {"n": 0, "o": x["o"], "c": x["c"], "v": 0.0, "tb": 0.0, "h": x["h"], "l": x["l"]})
            r["n"] += 1
            r["c"] = x["c"]
            r["v"] += x["v"] * x["c"]
            r["tb"] += x["tb"] * x["c"]
            r["h"] = max(r["h"], x["h"])
            r["l"] = min(r["l"], x["l"])
        fu = {}
        for t, v in (funding or {}).get(a, []):
            fu[t // DAY] = fu.get(t // DAY, 0.0) + v
        out[a] = {k: dict(r, tbf=(r["tb"] / r["v"] if r["v"] > 0 else None), fund=fu.get(k))
                  for k, r in dd.items() if r["n"] == 6}
    return out


def _fwd(p, a, d, h, corte=CORTE):
    """Compra na abertura de d+1, venda no fecho de d+h. None se sair do corte."""
    if (d + h + 1) * DAY > corte:
        return None
    x0, x1 = p[a].get(d + 1), p[a].get(d + h)
    if not x0 or not x1 or x0["o"] <= 0:
        return None
    return x1["c"] / x0["o"] - 1


def _ret(p, a, d, n):
    x0, x1 = p[a].get(d - n), p[a].get(d)
    if not x0 or not x1 or x0["c"] <= 0:
        return None
    return x1["c"] / x0["c"] - 1


def _media(p, a, d, n, f):
    xs = [f(p[a][k]) for k in range(d - n + 1, d + 1) if k in p[a]]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if len(xs) >= n * 0.8 else None


# sinais: valor alto = comprar. (familia, descricao, funcao)
def _sinais():
    def mom(n):
        return lambda p, a, d: _ret(p, a, d, n)

    def rev(n):
        return lambda p, a, d: (lambda r: None if r is None else -r)(_ret(p, a, d, n))

    def taker(n):
        return lambda p, a, d: _media(p, a, d, n, lambda x: x.get("tbf"))

    def taker_div(p, a, d):            # compradores agressivos com o preco a cair 3 dias
        t, r = _media(p, a, d, 3, lambda x: x.get("tbf")), _ret(p, a, d, 3)
        return None if t is None or r is None else t - 0.5 - 0.5 * r

    def fund_neg(p, a, d):
        f = _media(p, a, d, 3, lambda x: x.get("fund"))
        return None if f is None else -f

    def compressao(p, a, d):           # amplitude de 5 dias face a 60: mais apertado = maior
        k5 = _media(p, a, d, 5, lambda x: (x["h"] - x["l"]) / x["c"] if x["c"] else None)
        k60 = _media(p, a, d, 60, lambda x: (x["h"] - x["l"]) / x["c"] if x["c"] else None)
        return None if not k5 or not k60 else -(k5 / k60)

    def volume_surto(p, a, d):
        v1 = p[a].get(d, {}).get("v")
        v30 = _media(p, a, d - 1, 30, lambda x: x["v"])
        return None if not v1 or not v30 else v1 / v30

    def tendencia_recuo(p, a, d):      # multitemporal: acima da media de 50 dias e a cair 3 dias
        r3, m = _ret(p, a, d, 3), _media(p, a, d, 50, lambda x: x["c"])
        c = p[a].get(d, {}).get("c")
        if r3 is None or not m or not c or c < m:
            return None
        return -r3

    return [
        ("A", "momento 7 dias", mom(7)), ("A", "momento 30 dias", mom(30)),
        ("A", "momento 90 dias", mom(90)),
        ("B", "reversao 1 dia", rev(1)), ("B", "reversao 3 dias", rev(3)), ("B", "reversao 7 dias", rev(7)),
        ("D", "compressao de amplitude 5/60", compressao),
        ("G", "fracao compradora 1 dia", taker(1)), ("G", "fracao compradora 3 dias", taker(3)),
        ("G", "compradores com preco a cair", taker_div), ("G", "surto de volume", volume_surto),
        ("H", "recuo de 3 dias acima da media de 50", tendencia_recuo),
        ("I", "financiamento negativo 3 dias", fund_neg),
    ]


def seccional(p, fn, h, corte=CORTE, q=QUANTIL):
    """Serie (um ponto a cada h dias) de: retorno bruto do grupo comprado e
    excesso sobre a media do universo."""
    dias = sorted(set().union(*[set(v) for v in p.values()])) if p else []
    if not dias:
        return [], []
    brutos, excessos = [], []
    d = dias[0] + 100
    while d <= dias[-1]:
        vals, fw = [], {}
        for a in p:
            if d not in p[a]:
                continue
            v = fn(p, a, d)
            f = _fwd(p, a, d, h, corte)
            if v is None or f is None:
                continue
            vals.append((v, a))
            fw[a] = f
        if len(vals) >= MIN_MOEDAS:
            vals.sort(reverse=True)
            k = max(3, int(len(vals) * q))
            topo = [fw[a] for _, a in vals[:k]]
            todos = list(fw.values())
            b = sum(topo) / len(topo)
            brutos.append(b)
            excessos.append(b - sum(todos) / len(todos))
        d += h
    return brutos, excessos


def _t(xs):
    n = len(xs)
    if n < 10:
        return None, None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu, (mu / (sd / math.sqrt(n)) if sd > 0 else None)


def sazonalidade(bars, corte=CORTE):
    """F: retorno medio do mercado (media das moedas) por hora de abertura da
    vela de 4H e por dia da semana; comprar uma vela custa 0,7% ida e volta."""
    por_bin, por_dia = {}, {}
    mk = {}
    for a, c4 in bars.items():
        for x in c4:
            if x["t"] + H4 > corte or x["o"] <= 0:
                continue
            mk.setdefault(x["t"], []).append(x["c"] / x["o"] - 1)
    dia_mk = {}
    for t, rs in mk.items():
        if len(rs) >= MIN_MOEDAS:
            r = sum(rs) / len(rs)
            por_bin.setdefault(t % DAY // 3600, []).append(r)
            dia_mk.setdefault(t // DAY, []).append(r)
    for k, rs in dia_mk.items():
        if len(rs) == 6:
            prod = 1.0
            for r in rs:
                prod *= 1 + r
            por_dia.setdefault((k + 3) % 7, []).append(prod - 1)     # 0 = segunda
    out = []
    for hh, rs in sorted(por_bin.items()):
        mu, t = _t(rs)
        out.append(("F", f"vela de 4H que abre as {hh:02d}h UTC", 0, rs, mu, t))
    nomes = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    for wd, rs in sorted(por_dia.items()):
        mu, t = _t(rs)
        out.append(("F", f"dia da semana: {nomes[wd]}", 1, rs, mu, t))
    return out


def regime(p, corte=CORTE):
    """E: o BTC a cruzar para cima a media de 200 dias -> retorno do BTC em
    30 dias (acontecimentos raros: so informativo)."""
    b = p.get("BTC") or {}
    dias = sorted(b)
    cs = [b[d]["c"] for d in dias]
    ev = []
    for i in range(200, len(dias) - 1):
        m0 = sum(cs[i - 200:i]) / 200
        m1 = sum(cs[i - 199:i + 1]) / 200
        if cs[i - 1] <= m0 and cs[i] > m1:
            f = _fwd(p, "BTC", dias[i], 30, corte)
            if f is not None:
                ev.append(f)
    return ev


def triagem(pasta, corte=CORTE, horizontes=(1, 3, 7)):
    bars, _ = B.load_all(pasta, min_bars=1500)
    bars = recortar(bars, corte)
    for a, c in bars.items():
        if c and c[-1]["t"] + H4 > corte:
            raise Contaminacao(f"{a}: vela depois do corte")
    p = painel(bars, carregar_funding(pasta, corte))
    celulas = []
    for fam, nome, fn in _sinais():
        for h in horizontes:
            br, ex = seccional(p, fn, h, corte)
            mu_b, _ = _t(br)
            liq = [x - CUSTO_IDA_VOLTA for x in br]
            mu_l, t_l = _t(liq)
            mu_e, t_e = _t(ex)
            celulas.append({"familia": fam, "sinal": nome, "horizonte_dias": h, "n_dias": len(br),
                            "bruto": mu_b, "excesso": mu_e, "t_excesso": t_e,
                            "liquido": mu_l, "t_liquido": t_l})
    for fam, nome, h, rs, mu, t in sazonalidade(bars, corte):
        liq = [x - CUSTO_IDA_VOLTA for x in rs]
        mu_l, t_l = _t(liq)
        celulas.append({"familia": fam, "sinal": nome, "horizonte_dias": h, "n_dias": len(rs),
                        "bruto": mu, "excesso": None, "t_excesso": t,
                        "liquido": mu_l, "t_liquido": t_l})
    ev = regime(p, corte)
    for c in celulas:
        for k in ("t_excesso", "t_liquido"):
            t = c[k]
            c["p_" + k[2:]] = None if t is None else 1 - E.phi(t)
    for k in ("p_excesso", "p_liquido"):
        idx = [i for i, c in enumerate(celulas) if c[k] is not None]
        aj = E.holm([celulas[i][k] for i in idx])
        for i, (_, pa, rej) in zip(idx, aj):
            celulas[i][k + "_holm"] = pa
            celulas[i][k + "_passa"] = rej
    for c in celulas:
        for k, v in list(c.items()):
            if isinstance(v, float):
                c[k] = round(v, 6)
    return {"corte": corte, "moedas": len(bars), "celulas": celulas, "n_testes": len(celulas),
            "regime_btc_sma200": {"acontecimentos": len(ev),
                                  "retorno_30d_medio": round(sum(ev) / len(ev), 4) if ev else None},
            "aviso": "EXPLORATORIA: nao valida nada; dados antes da reserva; vies de sobrevivencia"}


if __name__ == "__main__":
    res = triagem(sys.argv[1])
    dest = sys.argv[2] if len(sys.argv) > 2 else None
    if dest:
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    for c in sorted(res["celulas"], key=lambda c: -(c["t_excesso"] or -99)):
        print(f"{c['familia']} {c['sinal'][:40]:40s} h={c['horizonte_dias']} n={c['n_dias']:4d} "
              f"bruto={c['bruto']} exc={c['excesso']} t={c['t_excesso']} liq={c['liquido']} "
              f"holm_exc={c.get('p_excesso_holm')} holm_liq={c.get('p_liquido_holm')}")
