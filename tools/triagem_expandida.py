"""Triagem EXPLORATORIA expandida (missao de expansao, 2026-11-11). Nao valida nada.

Acrescenta a tools/triagem_anomalias.py (mesmas regras, mesmas funcoes):
  - mais mecanismos: momento com volume, forca relativa face ao BTC, quebras de maximos de 20 dias, expansao de
    amplitude, transicoes de regime do BTC, recuo dentro da tendencia (multitemporal), e a familia C de shorts
    (fraqueza relativa persistente, perda de minimos de 20 dias, funding positivo extremo, fraqueza com BTC a cair);
  - horizonte de 14 dias (a triagem anterior mostrou que so a 7 dias aparecia margem);
  - CUSTOS POR CORRETORA, porque decidem tudo: o mesmo efeito bruto paga ou nao paga consoante onde se executa:
      bybit_spot   compra em spot na Bybit UE: 2 x (0,25% + 0,1%) = 0,70% ida e volta; short por margem em spot:
                   0,70% + juros do emprestimo (0,03%/dia, valor de referencia: NAO VERIFICADO)
      okx_perp     X-Perps da OKX: 2 x (0,05% taker + 0,05% deslize) = 0,20% ida e volta, MAIS o funding real
                   pago (long) ou recebido (short) em cada dia da detencao (ramo history/funding; sem funding = 0
                   e assinalado)
  - Holm sobre TODAS as celulas x corretoras (o numero de testes cresce: e o preco de olhar para mais coisas);
  - opcao de universo com as moedas retiradas (ramo history-delistadas) para medir o vies de sobrevivencia.
So dados antes de CORTE (2026-05-08, inicio da reserva). Um dia so conta se o retorno futuro acabar antes do corte.
Os dias sao amostrados de h em h dias (sem sobreposicao); o grupo e o quintil do sinal; uma observacao por dia.
Saida: celulas com bruto, excesso, liquido por corretora, t, p e Holm. O que passar Holm com liquido positivo numa
corretora e um PONTO DE PARTIDA para uma ficha pre-registada (tools/registo_hipoteses.py), nunca uma estrategia.
Uso: python -m tools.triagem_expandida <pasta_history> [saida.json] [--corte AAAA-MM-DD]"""
import datetime as _dt
import json
import math
import sys

from engine import backtest as B
from tools import estatistica_multipla as E
from tools import triagem_anomalias as T

DAY = T.DAY
QUANTIL = T.QUANTIL
HORIZONTES = (1, 3, 7, 14)
CUSTOS = {"bybit_spot": 0.007, "okx_perp": 0.002}
JUROS_MARGEM_DIA = 0.0003


def _fund_soma(p, a, d, h):
    """Funding acumulado das posicoes longas entre d+1 e d+h (positivo = longs pagam). None se faltar."""
    xs = [p[a].get(k, {}).get("fund") for k in range(d + 1, d + h + 1)]
    if any(x is None for x in xs):
        return None
    return sum(xs)


def _sma(p, a, d, n):
    return T._media(p, a, d, n, lambda x: x["c"])


def _maximo(p, a, d, n, campo="h"):
    xs = [p[a][k][campo] for k in range(d - n, d) if k in p[a]]
    return max(xs) if len(xs) >= n * 0.8 else None


def _minimo(p, a, d, n, campo="l"):
    xs = [p[a][k][campo] for k in range(d - n, d) if k in p[a]]
    return min(xs) if len(xs) >= n * 0.8 else None


def _sinais(btc_estado):
    """(familia, nome, funcao, lado). Valor alto = agir no lado indicado. btc_estado(d) -> dict do BTC nesse dia."""
    ret = T._ret

    def mom_volume(p, a, d):                       # A: momento de 7 dias so com volume acima do normal
        r, v1, v30 = ret(p, a, d, 7), p[a].get(d, {}).get("v"), T._media(p, a, d - 1, 30, lambda x: x["v"])
        if r is None or not v1 or not v30 or v1 < 1.5 * v30:
            return None
        return r

    def forca_relativa(p, a, d):                   # A: retorno de 30 dias menos o do BTC
        r, rb = ret(p, a, d, 30), (btc_estado(d) or {}).get("r30")
        return None if r is None or rb is None else r - rb

    def quebra_20(p, a, d):                        # D: fecho acima do maximo dos 20 dias anteriores
        c, m = p[a].get(d, {}).get("c"), _maximo(p, a, d, 20)
        return None if not c or not m or c <= m else c / m - 1

    def expansao(p, a, d):                         # D: amplitude de hoje vs media de 20 dias, com fecho a subir
        x = p[a].get(d)
        k20 = T._media(p, a, d - 1, 20, lambda y: (y["h"] - y["l"]) / y["c"] if y["c"] else None)
        if not x or not k20 or x["c"] <= x["o"]:
            return None
        k = (x["h"] - x["l"]) / x["c"]
        return k / k20 if k / k20 >= 1.8 else None

    def mom_btc_sobe(p, a, d):                     # E: momento de 7 dias so com o BTC acima da media de 50
        b = btc_estado(d) or {}
        return ret(p, a, d, 7) if b.get("acima50") else None

    def recuo_tendencia(p, a, d):                  # H: diario acima da SMA50 e retorno de 30 dias > 0; recuo de 2 dias
        c, m, r30, r2 = p[a].get(d, {}).get("c"), _sma(p, a, d, 50), ret(p, a, d, 30), ret(p, a, d, 2)
        if not c or not m or r30 is None or r2 is None or c < m or r30 <= 0 or r2 >= 0:
            return None
        return -r2

    def fraqueza_persistente(p, a, d):             # C: pior retorno de 30 dias e abaixo da SMA50
        c, m, r30 = p[a].get(d, {}).get("c"), _sma(p, a, d, 50), ret(p, a, d, 30)
        if not c or not m or r30 is None or c >= m:
            return None
        return -r30

    def perde_minimo(p, a, d):                     # C: fecho abaixo do minimo dos 20 dias anteriores
        c, m = p[a].get(d, {}).get("c"), _minimo(p, a, d, 20)
        return None if not c or not m or c >= m else 1 - c / m

    def funding_caro(p, a, d):                     # C: longs a pagar muito (3 dias) -> shorts recebem
        f = T._media(p, a, d, 3, lambda x: x.get("fund"))
        return f

    def fraqueza_btc_cai(p, a, d):                 # C+E: forca relativa negativa com o BTC abaixo da SMA50
        b = btc_estado(d) or {}
        r, rb = ret(p, a, d, 30), b.get("r30")
        if b.get("acima50") is not False or r is None or rb is None:
            return None
        return -(r - rb)

    base = [(f, n, fn, "LONG") for f, n, fn in T._sinais()]
    return base + [
        ("A", "momento 7 dias com volume >= 1,5x", mom_volume, "LONG*"),
        ("A", "forca relativa 30 dias face ao BTC", forca_relativa, "LONG"),
        ("D", "quebra do maximo de 20 dias", quebra_20, "LONG*"),
        ("D", "expansao de amplitude >= 1,8x a subir", expansao, "LONG*"),
        ("E", "momento 7 dias com BTC acima da SMA50", mom_btc_sobe, "LONG"),
        ("H", "recuo de 2 dias em tendencia (SMA50 e 30 dias > 0)", recuo_tendencia, "LONG"),
        ("C", "fraqueza persistente (30 dias, abaixo da SMA50)", fraqueza_persistente, "SHORT"),
        ("C", "perda do minimo de 20 dias", perde_minimo, "SHORT*"),
        ("C", "funding positivo alto (3 dias)", funding_caro, "SHORT"),
        ("C", "fraqueza relativa com BTC abaixo da SMA50", fraqueza_btc_cai, "SHORT"),
        ("C", "momento 7 dias (vender o topo: controlo)", lambda p, a, d: ret(p, a, d, 7), "SHORT"),
    ]


def estado_btc(p):
    b = p.get("BTC") or {}
    cache = {}

    def f(d):
        if d in cache:
            return cache[d]
        x = b.get(d)
        out = None
        if x:
            m = _sma(p, "BTC", d, 50)
            out = {"acima50": (x["c"] > m) if m else None, "r30": T._ret(p, "BTC", d, 30)}
        cache[d] = out
        return out
    return f


def seccional(p, fn, lado, h, corte):
    """Uma observacao a cada h dias: (bruto, excesso, liquido_bybit, liquido_okx, funding_em_falta).
    Lado com '*' = sinal de ACONTECIMENTO (quebra, perda de minimo, surto): o grupo sao TODAS as moedas com o sinal
    nesse dia (pelo menos 1), media por dia (as moedas do mesmo dia contam como um acontecimento); o universo para o
    excesso continua a ser todas as moedas com dados. Sem '*': quintil de cima com pelo menos MIN_MOEDAS."""
    evento = lado.endswith("*")
    lado = lado.rstrip("*")
    dias = sorted(set().union(*[set(v) for v in p.values()])) if p else []
    obs = []
    if not dias:
        return obs
    s = 1.0 if lado == "LONG" else -1.0
    d = dias[0] + 100
    while d <= dias[-1]:
        vals, fw = [], {}
        for a in p:
            if d not in p[a]:
                continue
            f = T._fwd(p, a, d, h, corte)
            if f is None:
                continue
            fw[a] = f
            v = fn(p, a, d)
            if v is not None:
                vals.append((v, a))
        if (evento and vals and len(fw) >= T.MIN_MOEDAS) or (not evento and len(vals) >= T.MIN_MOEDAS):
            vals.sort(reverse=True)
            k = len(vals) if evento else max(3, int(len(vals) * QUANTIL))
            grupo = [a for _, a in vals[:k]]
            br = sum(s * fw[a] for a in grupo) / len(grupo)
            uni = sum(s * x for x in fw.values()) / len(fw)          # universo: todas as moedas com dados
            fund, falta = [], 0
            for a in grupo:
                fs = _fund_soma(p, a, d, h)
                if fs is None:
                    falta += 1
                    fs = 0.0
                fund.append(-s * fs)                   # long paga funding positivo; short recebe
            liq_okx = br + sum(fund) / len(fund) - CUSTOS["okx_perp"]
            liq_by = br - CUSTOS["bybit_spot"] - (JUROS_MARGEM_DIA * h if lado == "SHORT" else 0.0)
            obs.append((br, br - uni, liq_by, liq_okx, falta / len(grupo)))
        d += h
    return obs


def triagem(pasta, corte=T.CORTE, horizontes=HORIZONTES, min_bars=1500):
    bars, _ = B.load_all(pasta, min_bars=min_bars)
    bars = T.recortar(bars, corte)
    for a, c in bars.items():
        if c and c[-1]["t"] + T.H4 > corte:
            raise T.Contaminacao(f"{a}: vela depois do corte")
    p = T.painel(bars, T.carregar_funding(pasta, corte))
    btc = estado_btc(p)
    cel = []
    for fam, nome, fn, lado in _sinais(btc):
        for h in horizontes:
            obs = seccional(p, fn, lado, h, corte)
            c = {"familia": fam, "sinal": nome, "lado": lado.rstrip("*"), "acontecimento": lado.endswith("*"),
                 "horizonte_dias": h, "n_dias": len(obs)}
            for i, k in enumerate(("bruto", "excesso", "liquido_bybit", "liquido_okx")):
                mu, t = T._t([o[i] for o in obs])
                c[k], c["t_" + k] = mu, t
                c["p_" + k] = None if t is None else 1 - E.phi(t)
            c["funding_em_falta"] = round(sum(o[4] for o in obs) / len(obs), 3) if obs else None
            cel.append(c)
    for k in ("liquido_bybit", "liquido_okx"):
        pass
    idx = [(i, k) for i, c in enumerate(cel) for k in ("liquido_bybit", "liquido_okx") if c["p_" + k] is not None]
    aj = E.holm([cel[i]["p_" + k] for i, k in idx])
    for (i, k), (_, pa, rej) in zip(idx, aj):
        cel[i]["holm_" + k] = pa
        cel[i]["passa_" + k] = rej
    for c in cel:
        for k, v in list(c.items()):
            if isinstance(v, float):
                c[k] = round(v, 6)
    return {"corte": corte, "moedas": len(bars), "n_celulas": len(cel), "n_testes_holm": len(idx),
            "custos": CUSTOS, "juros_margem_dia": JUROS_MARGEM_DIA, "celulas": cel,
            "aviso": "EXPLORATORIA: nao valida nada; so dados antes da reserva; Holm sobre celulas x corretoras"}


if __name__ == "__main__":
    a = sys.argv
    corte = T.CORTE
    if "--corte" in a:
        corte = int(_dt.datetime.strptime(a[a.index("--corte") + 1], "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc).timestamp())
        if corte > T.CORTE:
            sys.exit("o corte nao pode passar o inicio da reserva")
    res = triagem(a[1], corte)
    if len(a) > 2 and not a[2].startswith("--"):
        json.dump(res, open(a[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    melhores = sorted(res["celulas"], key=lambda c: -(c.get("t_liquido_okx") or -99))[:25]
    for c in melhores:
        print(f"{c['familia']} {c['lado'][:1]} {c['sinal'][:46]:46s} h={c['horizonte_dias']:2d} n={c['n_dias']:4d} "
              f"bruto={c['bruto']} liqOKX={c['liquido_okx']} t={c['t_liquido_okx']} holm={c.get('holm_liquido_okx')} "
              f"liqBybit={c['liquido_bybit']} holmB={c.get('holm_liquido_bybit')} fundfalta={c['funding_em_falta']}")


def sazonalidade_1h(pasta, corte=T.CORTE, min_moedas=T.MIN_MOEDAS):
    """F com velas de 1H (ramo history/1h, desde 2024-10): retorno medio do mercado por hora UTC de abertura, antes
    do corte. Comprar e vender uma vela de 1H custa 0,20% na OKX e 0,70% na Bybit UE."""
    import gzip
    import os
    d = os.path.join(pasta, "1h")
    mk = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".csv.gz"):
            continue
        with gzip.open(os.path.join(d, fn), "rt") as f:
            for ln in f:
                r = ln.strip().split(",")
                if len(r) < 5:
                    continue
                t, o, c = int(r[0]), float(r[1]), float(r[4])
                if t + 3600 > corte or o <= 0:
                    continue
                mk.setdefault(t, []).append(c / o - 1)
    por_h = {}
    for t, rs in mk.items():
        if len(rs) >= min_moedas:
            por_h.setdefault(t % DAY // 3600, []).append(sum(rs) / len(rs))
    out = []
    for h, rs in sorted(por_h.items()):
        mu, t = T._t(rs)
        out.append({"hora_utc": h, "n": len(rs), "bruto": round(mu, 6), "t": round(t, 2) if t else None,
                    "liquido_okx": round(mu - CUSTOS["okx_perp"], 6), "liquido_bybit": round(mu - CUSTOS["bybit_spot"], 6)})
    return out
