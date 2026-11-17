"""(17/11) Edge Detection do Quick Opportunities sobre o historico real de 30 min dos X-Perps da OKX.

Investigacao isolada: so endpoints publicos, sem chaves, sem executor, sem ordens. Responde a uma pergunta: as
familias do Quick Opportunities (engine/quick_opportunities.detect_opportunities) tem vantagem liquida fora da
amostra, contra o acaso, depois de custos e com correcao para hipoteses multiplas?

Metodo (fixado antes de correr, igual para todas as hipoteses):
- Universo: os X-Perps vivos (cripto, acoes/ETF, metais) ordenados pelo volume de 24 h; os N primeiros.
  Limite conhecido: so contratos vivos hoje (survivorship); os X-Perps existem ha poucos meses.
- Sinal no fecho da vela i com as 60 velas ate i (sem olhar para a frente); entrada na abertura de i+1
  (simulate_candidate); stop 1,5 ATR, alvo 3 ATR, saida em 8 velas (4 h). Uma posicao de cada vez por
  moeda/familia/lado (sem sobreposicao). Custos: 0,06% de comissao por lado + 0,05% de deslizamento por lado.
  Funding nao incluido (a OKX so da 3 meses; no maximo um evento em 4 h) - limite declarado.
- Hipoteses: familia x lado (ate 8). Divisao cronologica: primeiros 60% do tempo = desenho, ultimos 40% = teste.
- Acaso: para cada operacao real, uma entrada numa vela ao acaso da mesma moeda e do mesmo periodo, mesmo lado e
  a mesma geometria (stop 1,5 ATR / alvo 3 ATR dessa vela); 200 repeticoes -> percentil da media real.
- Walk-forward: media por mes no periodo de teste; fracao de meses positivos.
- Veredicto por hipotese (todos): >= 100 operacoes no teste, media liquida > 0 no desenho E no teste, percentil
  do acaso >= 95 no teste e p de Holm < 0,05 (p = 1 - percentil/100, corrigido para o numero de hipoteses).
  Passar = CANDIDATA A PAPEL (nunca real: a passagem a producao exige autorizacao explicita).

Uso: python -m tools.qo_edge <saida.json> [n_moedas] [dias]
"""
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from engine import quick_opportunities as QO
from engine import quick_opportunities_derivatives as D
from engine import quick_opportunities_okx as QX

BAR = QO.BAR_SECONDS
FEE, SLIP = 0.06, 0.05
WIN = 60
N_ACASO = 200
MIN_OOS = 100


def sinais(candles):
    """[(i, candidato)] sem sobreposicao por familia/lado; o sinal da vela i so usa candles[:i+1]."""
    out, livre = [], {}
    for i in range(WIN - 1, len(candles) - 1):
        for c in QO.detect_opportunities(candles[i - WIN + 1:i + 1], "X"):
            k = (c["family"], c["side"])
            if i < livre.get(k, -1):
                continue
            out.append((i, c))
            livre[k] = i + QO.MAX_HOLD_BARS + 1
    return out


def simular(candles, i, c):
    r = QO.simulate_candidate(candles, i, c, fee_pct=FEE, slippage_pct=SLIP)
    return r if r.get("status") == "CLOSED" else None


_ATR = {}


def atr_em(candles, i):
    """ATR do motor na vela i (cache por serie: o acaso pede milhares de velas)."""
    k = (id(candles), i)
    if k not in _ATR:
        _ATR[k] = QO._atr(candles[i - WIN + 1:i + 1])
    return _ATR[k]


def acaso(candles, i0, i1, side, rng):
    """Entrada ao acaso em [i0, i1) com a geometria do motor nessa vela; R liquido ou None."""
    for _ in range(20):
        i = rng.randrange(max(WIN, i0), max(WIN + 1, i1))
        if i >= len(candles) - 1:
            continue
        atr = atr_em(candles, i)
        if not atr:
            continue
        e = float(candles[i]["c"])
        risk = 1.5 * atr
        c = {"side": side, "stop": e - risk if side == "LONG" else e + risk,
             "target": e + 2 * risk if side == "LONG" else e - 2 * risk}
        r = simular(candles, i, c)
        if r:
            return r["net_r"]
    return None


def avaliar(series, corte_t, seed=7):
    """series: {moeda: velas}. Devolve {hipotese: metricas}."""
    rng = random.Random(seed)
    ops = {}
    for a, cs in series.items():
        if len(cs) < WIN + 20:
            continue
        i_corte = next((k for k, b in enumerate(cs) if b["t"] >= corte_t), len(cs))
        for i, c in sinais(cs):
            r = simular(cs, i, c)
            if not r:
                continue
            per = "teste" if cs[i]["t"] >= corte_t else "desenho"
            ops.setdefault((c["family"], c["side"]), []).append(
                {"a": a, "i": i, "t": cs[i]["t"], "r": r["net_r"], "per": per, "regime": c.get("regime"),
                 "lim": (i_corte, len(cs)) if per == "teste" else (WIN, i_corte)})
    res = {}
    for (fam, side), lst in sorted(ops.items()):
        d = [o["r"] for o in lst if o["per"] == "desenho"]
        t = [o for o in lst if o["per"] == "teste"]
        tr = [o["r"] for o in t]
        m_t = sum(tr) / len(tr) if tr else None
        pct = None
        if tr:
            medias = []
            for _ in range(N_ACASO):
                xs = [acaso(series[o["a"]], *o["lim"], side, rng) for o in t]
                xs = [x for x in xs if x is not None]
                if xs:
                    medias.append(sum(xs) / len(xs))
            pct = round(100 * sum(1 for m in medias if m < m_t) / len(medias), 1) if medias else None
        meses = {}
        for o in t:
            meses.setdefault(time.strftime("%Y-%m", time.gmtime(o["t"])), []).append(o["r"])
        regimes = {}
        for o in t:
            regimes.setdefault(o["regime"], []).append(o["r"])
        res[f"{fam}|{side}"] = {
            "n_desenho": len(d), "r_desenho": round(sum(d) / len(d), 4) if d else None,
            "n_teste": len(tr), "r_teste": round(m_t, 4) if m_t is not None else None,
            "acerto_teste": round(sum(1 for x in tr if x > 0) / len(tr), 3) if tr else None,
            "percentil_acaso": pct,
            "meses_teste": {k: [len(v), round(sum(v) / len(v), 3)] for k, v in sorted(meses.items())},
            "fracao_meses_positivos": (round(sum(1 for v in meses.values() if sum(v) > 0) / len(meses), 2)
                                       if meses else None),
            "por_regime_teste": {k: [len(v), round(sum(v) / len(v), 3)] for k, v in sorted(regimes.items())},
            "moedas_teste": len({o["a"] for o in t}),
        }
    holm(res)
    return res


def holm(res):
    """p = 1 - percentil/100 (teste unilateral contra o acaso); Holm sobre todas as hipoteses avaliadas."""
    ps = sorted(((1 - (v["percentil_acaso"] or 0) / 100, k) for k, v in res.items()), key=lambda x: x[0])
    m = len(ps)
    acc = 0.0
    for j, (p, k) in enumerate(ps):
        acc = max(acc, min(1.0, (m - j) * max(p, 1 / (N_ACASO + 1))))
        res[k]["p_holm"] = round(acc, 4)
    for k, v in res.items():
        ok = (v["n_teste"] >= MIN_OOS and (v["r_desenho"] or 0) > 0 and (v["r_teste"] or 0) > 0
              and (v["percentil_acaso"] or 0) >= 95 and v["p_holm"] < 0.05)
        v["veredicto"] = ("CANDIDATA A PAPEL" if ok else
                          "AMOSTRA INSUFICIENTE" if v["n_teste"] < MIN_OOS else "SEM VANTAGEM DEMONSTRADA")
    return res


def recolher(n_moedas=80, dias=240, now=None):
    now = int(now or time.time())
    sel, vistos = QX._public_universe(limit=n_moedas)
    end_ms = (now * 1000 // (BAR * 1000)) * BAR * 1000
    start_ms = end_ms - dias * 86400 * 1000

    def um(info):
        try:
            cs = D.fetch_okx_xperp_candles(info["inst_id"], start_ms, end_ms, pause_seconds=0.15)
            return info, [b for b in cs if b["t"] + BAR <= now]
        except Exception as e:
            return info, {"erro": f"{type(e).__name__}: {str(e)[:100]}"}
    with ThreadPoolExecutor(max_workers=4) as ex:
        got = list(ex.map(um, sel))
    series = {i["base"]: cs for i, cs in got if isinstance(cs, list) and cs}
    erros = {i["base"]: cs for i, cs in got if isinstance(cs, dict)}
    classes = {i["base"]: i.get("asset_class") for i in sel}
    return series, erros, classes, vistos


def main(dest, n_moedas=80, dias=240):
    t0 = time.time()
    series, erros, classes, vistos = recolher(int(n_moedas), int(dias))
    ts = sorted(b["t"] for cs in series.values() for b in cs)
    if not ts:
        out = {"erro": "sem dados", "erros": erros}
    else:
        corte = ts[0] + int(0.6 * (ts[-1] - ts[0]))
        res = avaliar(series, corte)
        por_classe = {}
        for cl in ("crypto", "equity", "precious_metal"):
            sub = {a: cs for a, cs in series.items() if classes.get(a) == cl}
            if sub:
                por_classe[cl] = {k: {q: v[q] for q in ("n_teste", "r_teste", "percentil_acaso")}
                                  for k, v in avaliar(sub, corte, seed=11).items()}
        out = {"instrumentos_vistos": vistos, "moedas": len(series), "erros": erros,
               "classes": {cl: sum(1 for a in series if classes.get(a) == cl) for cl in ("crypto", "equity", "precious_metal")},
               "inicio": ts[0], "corte": corte, "fim": ts[-1], "velas": len(ts),
               "custos": {"comissao_lado_pct": FEE, "deslizamento_lado_pct": SLIP, "funding": "nao incluido"},
               "hipoteses": res, "por_classe": por_classe, "segundos": round(time.time() - t0)}
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    r = main(*sys.argv[1:4])
    for k, v in (r.get("hipoteses") or {}).items():
        print(k, {q: v[q] for q in ("n_desenho", "r_desenho", "n_teste", "r_teste", "percentil_acaso", "p_holm",
                                    "fracao_meses_positivos", "veredicto")})
