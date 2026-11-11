"""Auditoria da BOUNCE_AMPLITUDE (2026-11-11). So leitura: nao promove, nao
muda a execucao, nao mexe em engine/ nem em tools/arena_ringue.py.

Perguntas: de onde vem o +0,8R com 16 de 16 do combate; quantos
acontecimentos independentes ha la dentro; se passar o p95 do acaso resiste a
um acaso que respeita o agrupamento; quanto custa o deslize e a comissao; se
o limiar de 25% e robusto; como compara com o BTC; quanta amostra falta.

Separacao dos dados:
- o registo do combate (state.json do ramo data) e dados ja vistos: so se
  DESCREVE, nao se escolhe nada com ele;
- a robustez dos parametros e os custos medem-se na janela de exploracao
  (2021-08-01 ate ao corte da reserva, tools/triagem_anomalias.CORTE), nunca
  na reserva.

Uso: python -m tools.auditoria_bounce_amplitude <pasta_history> <state.json> [saida.json]
"""
import json
import math
import random
import sys
import time

from engine import backtest as B
from engine import paper_bounce as PB
from tools import arena_ringue as R
from tools import estatistica_multipla as E
from tools.triagem_anomalias import CORTE

DAY, H4 = 86400, 4 * 3600
INICIO_EXPLORACAO = 1627776000          # 2021-08-01
LIMIARES = (0.15, 0.20, 0.25, 0.30, 0.35)


def sig_amp(limiar):
    """sig_amplitude do ringue com o limiar como parametro (mesma logica)."""
    def f(c4):
        s0 = R.sig_x30(c4)
        if not s0:
            return None
        a = R.amplitude_em(c4[-1]["t"] + H4)
        if a is None or a < limiar:
            return None
        return dict(s0, amp=a)
    return f


def operacoes(bars, above, t0, fn, chave="X"):
    out = []
    for a, c4 in sorted(bars.items()):
        out += [dict(t, asset=a) for _, t in R.generic_trades(a, c4, above, t0, chave, fn)]
    out.sort(key=lambda t: t["t"])
    return out


def resumo(trs):
    if not trs:
        return {"n_operacoes": 0, "n_acontecimentos": 0}
    out = E.resumo_eventos(trs)
    rs = [t["r"] for t in trs]
    out["acerto"] = round(sum(1 for x in rs if x > 0) / len(rs), 3)
    ev = [sum(e) / len(e) for e in E.eventos(trs)]
    if len(ev) > 1:
        mu = sum(ev) / len(ev)
        out["sd_por_acontecimento"] = round(math.sqrt(sum((x - mu) ** 2 for x in ev) / (len(ev) - 1)), 4)
    return out


def com_custos(bars, above, t0, fn, fee, slip):
    f0, s0 = PB.FEE_PCT, PB.SLIP_PCT
    try:
        PB.FEE_PCT, PB.SLIP_PCT = fee, slip
        return operacoes(bars, above, t0, fn)
    finally:
        PB.FEE_PCT, PB.SLIP_PCT = f0, s0


def registo_combate(state):
    """Operacoes do combate (ringue longo) tal como estao guardadas."""
    lu = (((state.get("arena") or {}).get("longo") or {}).get("lutadores") or {}).get("BOUNCE_AMPLITUDE") or {}
    rec = [{"t": t, "r": r, "asset": "?"} for t, r in lu.get("recentes") or []]
    return lu, rec


def auditar(pasta, state):
    bars_all, _ = B.load_all(pasta, min_bars=1500)
    btc = bars_all["BTC"]
    fim = btc[-1]["t"] + H4
    above = R.btc_above(btc)
    out = {"gerado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "fim_historico": fim}

    # 1. o registo do combate
    lu, rec = registo_combate(state)
    out["combate"] = {"n": lu.get("n"), "avg_r": lu.get("avg_r"), "por_regime": {
        k: {"n": v.get("n"), "avg_r": v.get("avg_r"), "dias": (v.get("qualidade") or {}).get("dias"),
            "acaso_p95": v.get("acaso_p95")} for k, v in (lu.get("por_regime") or {}).items()},
        "recentes_45d": resumo(rec),
        "velas_distintas_recentes": sorted({time.strftime("%Y-%m-%d %H", time.gmtime(t["t"])) for t in rec})}

    # 2. reconstrucao local dos ultimos 90 dias (dados ja vistos; so descreve)
    R.CTX.update(btc=btc, bars=bars_all, funding={}, oi={}, macro={}, ls={}, rank={})
    t90 = fim - 90 * DAY
    loc = {}
    for lim in (0.25, 0.22, 0.0):
        trs = operacoes(bars_all, above, t90, sig_amp(lim))
        loc[f"limiar_{lim:.2f}"] = dict(resumo(trs), operacoes=[
            [time.strftime("%Y-%m-%d %H", time.gmtime(t["t"])), t["asset"], round(t["r"], 3)] for t in trs])
    amp = R.CTX["_amp"][1]
    picos = sorted(((k, v) for k, v in amp.items() if k >= t90 and v >= 0.2), key=lambda x: x[0])
    out["ultimos_90_dias_local"] = {"operacoes": loc, "fracao_em_sobrevenda_picos": [
        [time.strftime("%Y-%m-%d %H", time.gmtime(k)), round(v, 3)] for k, v in picos]}

    # 3. acaso independente contra acaso agrupado, nas operacoes de 90 dias com o
    #    limiar a 22% (o que reproduz o dia 09/10 do combate neste universo)
    trs = operacoes(bars_all, above, t90, sig_amp(0.22))
    rng = random.Random(11)
    ind = E.acaso_agrupado(trs, bars_all, rng, reps=400, agrupar=False)
    agr = E.acaso_agrupado(trs, bars_all, random.Random(11), reps=400, agrupar=True)
    mu = sum(t["r"] for t in trs) / len(trs) if trs else None
    out["acaso_90d"] = {"n": len(trs), "r_medio": None if mu is None else round(mu, 3),
                        "independente": {"mediana": _r(ind["mediana"]), "p95": _r(ind["p95"]),
                                         "p": _r(E.p_acaso(mu, ind["medias"])) if mu is not None else None},
                        "agrupado": {"mediana": _r(agr["mediana"]), "p95": _r(agr["p95"]),
                                     "p": _r(E.p_acaso(mu, agr["medias"])) if mu is not None else None}}

    # 4. exploracao (antes da reserva): limiar, custos e acaso agrupado
    bars = {a: [x for x in c if x["t"] + H4 <= CORTE] for a, c in bars_all.items()}
    R.CTX.update(btc=bars["BTC"], bars=bars, funding={}, oi={}, macro={}, ls={}, rank={})
    R.CTX.pop("_amp", None)
    lims = {}
    base = None
    for lim in LIMIARES:
        tr = operacoes(bars, above, INICIO_EXPLORACAO, sig_amp(lim))
        lims[f"{lim:.2f}"] = resumo(tr)
        if lim == 0.25:
            base = tr
    x30 = operacoes(bars, above, INICIO_EXPLORACAO, R.sig_x30)
    lims["sem_filtro (BOUNCE_X30)"] = resumo(x30)
    out["exploracao"] = {"janela": [INICIO_EXPLORACAO, CORTE], "por_limiar": lims}
    custos = {}
    for fee, slip in ((0.1, 0.05), (0.25, 0.1), (0.25, 0.2), (0.4, 0.2)):
        custos[f"comissao {fee}% + deslize {slip}%"] = resumo(com_custos(bars, above, INICIO_EXPLORACAO,
                                                                          sig_amp(0.25), fee, slip))
    out["exploracao"]["custos_limiar_0.25"] = custos
    if base:
        ind = E.acaso_agrupado(base, bars, random.Random(5), reps=200, agrupar=False)
        agr = E.acaso_agrupado(base, bars, random.Random(5), reps=200, agrupar=True)
        mu = sum(t["r"] for t in base) / len(base)
        out["exploracao"]["acaso_limiar_0.25"] = {
            "r_medio": round(mu, 3),
            "independente": {"mediana": _r(ind["mediana"]), "p95": _r(ind["p95"]), "p": _r(E.p_acaso(mu, ind["medias"]))},
            "agrupado": {"mediana": _r(agr["mediana"]), "p95": _r(agr["p95"]), "p": _r(E.p_acaso(mu, agr["medias"]))}}
        ev = [sum(e) / len(e) for e in E.eventos(base)]
        anos = (CORTE - INICIO_EXPLORACAO) / (365.25 * DAY)
        sd = lims["0.25"].get("sd_por_acontecimento") or 1.0
        need = {f"{d:+.2f}R": E.n_necessario(sd, d) for d in (0.1, 0.15, 0.25)}
        out["amostra"] = {"acontecimentos_por_ano": round(len(ev) / anos, 1), "sd_por_acontecimento": sd,
                          "acontecimentos_necessarios": need,
                          "anos_necessarios": {k: (round(v / (len(ev) / anos), 1) if v else None) for k, v in need.items()}}

    # 5. referencias passivas nos mesmos 90 dias
    b90 = [x for x in btc if x["t"] >= t90]
    out["referencias_90d"] = {"btc_comprado": round(b90[-1]["c"] / b90[0]["o"] - 1, 4) if b90 else None,
                              "dias_btc_acima_sma200": sum(1 for k, v in above.items() if k >= t90 // DAY and v)}
    return out


def _r(x):
    return None if x is None else round(x, 4)


if __name__ == "__main__":
    st = json.load(open(sys.argv[2], encoding="utf-8"))
    res = auditar(sys.argv[1], st)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "ultimos_90_dias_local"}, ensure_ascii=False, indent=1))
