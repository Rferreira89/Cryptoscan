"""Acompanhamento PROSPETIVO em sombra das hipoteses pre-registadas (missao de expansao, 2026-11-11).

Sem autoridade de execucao: nao chama corretoras, nao escreve estado de estrategias, nao envia ordens. Le velas
publicas (ramo history) e calcula, so com dias POSTERIORES ao pre-registo de cada ficha, os acontecimentos e o
resultado liquido com os custos da corretora onde a hipotese seria executada (OKX: 0,10% por lado + funding real).

Regras (as da ficha, sem as mudar depois de ver):
  - um acontecimento = um dia de sinal; o seguinte so pode comecar depois de o anterior acabar (sem sobreposicao);
  - entrada na abertura de d+1, saida no fecho de d+h; o primeiro d possivel e o dia do pre-registo (d+1 posterior);
  - as funcoes de sinal sao as MESMAS da triagem (tools/triagem_expandida), para nao haver diferenca entre o que foi
    explorado e o que e seguido;
  - teste contra o acaso AGRUPADO: para cada acontecimento sorteia-se um grupo do mesmo tamanho entre as moedas com
    dados nesse dia (o mesmo dia, o mesmo mercado), e compara-se a media.
Uso: python -m tools.sombra_prospetiva <pasta_history> <saida.json> [--ate AAAA-MM-DD]"""
import datetime as _dt
import json
import math
import random
import sys

from engine import backtest as B
from tools import estatistica_multipla as E
from tools import registo_hipoteses as R
from tools import triagem_anomalias as T
from tools import triagem_expandida as X

DAY = T.DAY
HIPOTESES = {
    "MOMENTO_RISCO_ON": {"lado": "LONG", "h": 3, "sinal": "momento 7 dias com BTC acima da SMA50", "evento": False},
    "QUEBRA_MINIMO_SHORT": {"lado": "SHORT", "h": 3, "sinal": "perda do minimo de 20 dias", "evento": True},
}


def _fn(nome, btc):
    for fam, n, fn, lado in X._sinais(btc):
        if n == nome:
            return fn
    raise KeyError(nome)


def _dia(iso):
    return int(_dt.datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc).timestamp()) // DAY


def grupo(p, fn, d, h, evento, ate):
    """(grupo, universo) do dia d: moedas com sinal e todas as moedas com o retorno de d+1..d+h completo."""
    fw, vals = {}, []
    for a in p:
        if d not in p[a]:
            continue
        f = T._fwd(p, a, d, h, ate)
        if f is None:
            continue
        fw[a] = f
        v = fn(p, a, d)
        if v is not None:
            vals.append((v, a))
    if (evento and not vals) or (not evento and len(vals) < T.MIN_MOEDAS) or len(fw) < T.MIN_MOEDAS:
        return None, fw
    vals.sort(reverse=True)
    k = len(vals) if evento else max(3, int(len(vals) * X.QUANTIL))
    return [a for _, a in vals[:k]], fw


def liquido(p, grupo_, fw, d, h, lado):
    s = 1.0 if lado == "LONG" else -1.0
    br = sum(s * fw[a] for a in grupo_) / len(grupo_)
    fund, falta = [], 0
    for a in grupo_:
        fs = X._fund_soma(p, a, d, h)
        if fs is None:
            falta += 1
            fs = 0.0
        fund.append(-s * fs)
    return br + sum(fund) / len(fund) - X.CUSTOS["okx_perp"], br, falta


def acompanhar(p, id_, inicio_dia, ate, rng=None, reps=1000):
    cfg = HIPOTESES[id_]
    fn = _fn(cfg["sinal"], X.estado_btc(p))
    h, lado = cfg["h"], cfg["lado"]
    dias = sorted(set().union(*[set(v) for v in p.values()])) if p else []
    evs, livre = [], inicio_dia
    for d in dias:
        if d < livre or d < inicio_dia:
            continue
        g, fw = grupo(p, fn, d, h, cfg["evento"], ate)
        if not g:
            continue
        liq, br, falta = liquido(p, g, fw, d, h, lado)
        evs.append({"dia": _dt.datetime.fromtimestamp(d * DAY, _dt.timezone.utc).strftime("%Y-%m-%d"), "moedas": len(g),
                    "bruto": round(br, 6), "liquido_okx": round(liq, 6), "funding_em_falta": falta, "_fw": fw, "_n": len(g),
                    "_d": d})
        livre = d + h
    rng = rng or random.Random(7)
    medias = []
    if evs:
        for _ in range(reps):
            tot = 0.0
            for e in evs:
                fw = list(e["_fw"].items())
                amostra = rng.sample(fw, min(e["_n"], len(fw)))
                s = 1.0 if lado == "LONG" else -1.0
                tot += sum(s * f for _, f in amostra) / len(amostra) - X.CUSTOS["okx_perp"]
            medias.append(tot / len(evs))
    xs = [e["liquido_okx"] for e in evs]
    mu, t = T._t(xs) if len(xs) >= 10 else ((sum(xs) / len(xs)) if xs else None, None)
    obs = mu if mu is not None else None
    p_acaso = E.p_acaso(obs, medias) if medias and obs is not None else None
    for e in evs:
        for k in ("_fw", "_n", "_d"):
            e.pop(k)
    return {"id": id_, "inicio": _dt.datetime.fromtimestamp(inicio_dia * DAY, _dt.timezone.utc).strftime("%Y-%m-%d"),
            "acontecimentos": len(evs), "faltam_para_30": max(0, 30 - len(evs)), "media_liquida_okx": obs,
            "t": t, "p_unilateral": None if t is None else 1 - E.phi(t), "p_acaso_agrupado": p_acaso,
            "eventos": evs, "estado": "a acumular" if len(evs) < 30 else "pronta para decisao (registar resultado)"}


def correr(pasta, ate=None, linhas=None):
    linhas = R.ler() if linhas is None else linhas
    bars, _ = B.load_all(pasta, min_bars=300)
    ate = ate or max(c[-1]["t"] + T.H4 for c in bars.values() if c)
    p = T.painel(bars, T.carregar_funding(pasta, ate + 1))
    out = []
    for id_ in HIPOTESES:
        f = R._ficha(linhas, id_)
        if not f:
            out.append({"id": id_, "estado": "sem pre-registo: nao se acompanha"})
            continue
        ini = max(_dia(f["dados"]["validacao"]["inicio"]), _dia(f["quando"]) + 1)
        out.append(acompanhar(p, id_, ini, ate))
    return {"gerado": int(_dt.datetime.now(_dt.timezone.utc).timestamp()), "dados_ate": ate, "hipoteses": out,
            "aviso": "SOMBRA: sem dinheiro real nem autoridade de execucao; so dias depois do pre-registo"}


if __name__ == "__main__":
    a = sys.argv
    ate = None
    if "--ate" in a:
        ate = _dia(a[a.index("--ate") + 1]) * DAY
    r = correr(a[1], ate)
    json.dump(r, open(a[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for h in r["hipoteses"]:
        print(h["id"], h.get("estado"), "acontecimentos", h.get("acontecimentos"), "media", h.get("media_liquida_okx"),
              "p_acaso", h.get("p_acaso_agrupado"))
