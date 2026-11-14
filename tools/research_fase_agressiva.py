"""Investigacao 2026-11-14 (ordem operacional do Rui, fase agressiva): CAP_MERCADO_V2 e BOUNCE_LARGO.
So compras. Pre-registo em backtest/investigacao.md (escrito e guardado em commit antes de correr).

CAP_MERCADO_V2 (prioridade 1)
  gatilho  : vela de 4H da moeda com volume >= 3x a media das 20 anteriores, pavio inferior >= 50% da amplitude,
             fecho no terco superior e minimo pelo menos 8% abaixo do maximo das 18 velas anteriores
             (as regras de tools.arena_ringue.sig_capitulacao)
  mercado  : pelo menos N OUTRAS moedas com queda >= 5% na mesma vela (minimo da vela pelo menos 5% abaixo do
             fecho da vela anterior; a medida de "despejo" do CAP_MERCADO de 2026-10-15). Sem filtro do BTC
             (o BTC pode estar abaixo da SMA200).
  stop     : minimo da vela - 0,1 ATR14. Objetivo unico a K R (calculado na abertura da entrada).
             Sem stop na entrada. Saida ao fim de 3 dias.
  grelha   : N in {3, 5} x K in {1,5; 2}

BOUNCE_LARGO (prioridade 2)
  mercado  : BTC acima da SMA200 diaria (ultimo dia fechado)
  gatilho  : RSI14 4H < X numa das ultimas 3 velas; fecho acima do maximo da vela anterior com RSI a subir;
             volume da vela >= V x media das 20 anteriores
  stop     : o mais baixo de (minimo das ultimas 6 velas - 0,1 ATR) e (fecho - 1,25 ATR)
  saidas   : 50% na SMA20 de 4H, resto no maximo das 42 velas anteriores; stop na entrada depois do 1.o;
             saida ao fim de 5 dias (exatamente tools.research_bounce, com H=5 e o filtro de volume)
  grelha   : X in {30, 35} x V in {2,0; 2,5}

Metodo: tools/research_rlib.evaluate (carteira 4 x 25%, custos 0,25% + 0,1% por lado, ultimos 24 meses:
18 de desenho e 6 de reserva, walk-forward treino 183 / teste 91, acaso +-90 velas com a mesma geometria).
Cada combinacao e avaliada sozinha (walk-forward, reserva e acaso proprios); o criterio 3 (grelha estavel)
usa a fracao das 4 combinacoes da hipotese com retorno positivo no desenho. Criterio do acaso (ordem do Rui):
percentil >= 90 fora da amostra (em vez de > p95). Veredicto maximo: PARA PAPEL.

Uso: python -m tools.research_fase_agressiva <historico> [saida.json]
"""
import json
import sys

from engine import backtest as B
from tools import research_bounce as RB
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
PCTIL_MIN = 90
CAP_GRID = [{"N": n, "K": k} for n in (3, 5) for k in (1.5, 2.0)]
BL_GRID = [{"X": x, "V": v} for x in (30, 35) for v in (2.0, 2.5)]
CAP_HOLD, BL_HOLD = 3 * R.DAY, 5 * R.DAY
DROP = 0.05


def despejos(data):
    """{t de abertura da vela: {moedas com minimo >= 5% abaixo do fecho anterior}} (so a propria vela)."""
    out = {}
    for a, c4 in data.items():
        for i in range(1, len(c4)):
            if c4[i - 1]["t"] == c4[i]["t"] - TF and c4[i]["l"] <= (1 - DROP) * c4[i - 1]["c"]:
                out.setdefault(c4[i]["t"], set()).add(a)
    return out


def cap_raw(c4):
    """{t da abertura da entrada: (sinal sem K, t da vela)} com o gatilho de capitulacao."""
    at = R.atr(c4)
    out = {}
    for i in range(60, len(c4)):
        b = c4[i]
        rg = b["h"] - b["l"]
        vavg = sum(x["v"] for x in c4[i - 20:i]) / 20
        if rg <= 0 or vavg <= 0 or b["v"] < 3 * vavg or at[i] is None:
            continue
        wick = min(b["o"], b["c"]) - b["l"]
        hi18 = max(x["h"] for x in c4[i - 18:i])
        if wick < 0.5 * rg or b["c"] < b["l"] + 2 / 3 * rg or b["l"] > hi18 * 0.92:
            continue
        stop = b["l"] - 0.1 * at[i]
        if stop <= 0:
            continue
        out[b["t"] + TF] = ({"stop": stop, "partials": [100], "breakeven": False, "rank": -b["v"] / vavg}, b["t"])
    return out


def cap_signals(asset, raw, desp, n, k):
    out = {}
    for te, (s, t) in raw.items():
        if len(desp.get(t, set()) - {asset}) >= n:
            out[te] = dict(s, tp_r=k)
    return out


def bl_signals(c4, btc_up, x, v):
    base = RB.signals(c4, btc_up, x, False)
    idx = {b["t"] + TF: i for i, b in enumerate(c4)}
    out = {}
    for te, s in base.items():
        i = idx[te]
        vavg = sum(y["v"] for y in c4[i - 20:i]) / 20
        if vavg > 0 and c4[i]["v"] >= v * vavg:
            out[te] = dict(s, breakeven=True)
    return out


def linha(res, share):
    """Criterios 1-6 (o 3 com a fracao da grelha inteira) + acaso >= p90 -> veredicto por combinacao."""
    crit = {k: v for k, v in res["criteria"].items() if not k.startswith("7_")}
    crit["3_grelha_estavel"] = share >= 0.75
    fa = res["random"]["fora_da_amostra"]
    pct = fa.get("percentil")
    crit["7_acaso_percentil_90"] = pct is not None and pct >= PCTIL_MIN
    n_wf = res["walk_forward"]["oos_trades"]
    seis = all(v for k, v in crit.items() if not k.startswith("7_"))
    if n_wf < 40:
        ver = "AMOSTRA INSUFICIENTE"
    elif seis and crit["7_acaso_percentil_90"]:
        ver = "PARA PAPEL"
    else:
        ver = "NAO VALIDADA"
    return {"operacoes_fora_amostra": fa.get("n"), "operacoes_walk_forward": n_wf,
            "operacoes_reserva": (res["holdout"]["trades"] or {}).get("n"),
            "r_medio_fora_amostra": fa.get("r_real"), "acaso_mediana": fa.get("r_acaso_mediana"),
            "percentil_acaso": pct, "criterios": crit, "seis_passam": seis,
            "acaso_p90": crit["7_acaso_percentil_90"], "veredicto": ver,
            "desenho": res["grid"][next(iter(res["grid"]))]["trades"]}


def correr(nome, grid, runner, hold, data, majors, base, d0, ds, d1, warm):
    full = {}
    for cfg in grid:
        full[json.dumps(cfg, sort_keys=True)] = R.evaluate(nome, [cfg], runner, data, TF, lambda c: hold, 90,
                                                          majors, base, d0, ds, d1, warm=warm)
    share = sum(1 for r in full.values() if next(iter(r["grid"].values()))["all"]["return_pct"] > 0) / len(full)
    return {k: dict(linha(r, share), detalhe=r) for k, r in full.items()}, share


def main(folder, out="backtest/research_fase_agressiva.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    warm = days[0] + 210
    res = {"moedas": len(data), "ultima_vela_btc": data["BTC"][-1]["t"]}

    desp = despejos(data)
    raw = {a: cap_raw(data[a]) for a in data}

    def cap_runner(cfg, universe):
        sigs = {a: cap_signals(a, raw[a], desp, cfg["N"], cfg["K"]) for a in data}
        return R.simulate(data, sigs, TF, CAP_HOLD, universe)

    res["CAP_MERCADO_V2"], res["CAP_MERCADO_V2_fracao_grelha"] = correr(
        "CAP_MERCADO_V2", CAP_GRID, cap_runner, CAP_HOLD, data, majors, base, d0, ds, d1, warm)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)

    cache = {}

    def bl_runner(cfg, universe):
        k = (cfg["X"], cfg["V"])
        if k not in cache:
            cache[k] = {a: bl_signals(data[a], btc_up, *k) for a in data}
        return R.simulate(data, cache[k], TF, BL_HOLD, universe)

    res["BOUNCE_LARGO"], res["BOUNCE_LARGO_fracao_grelha"] = correr(
        "BOUNCE_LARGO", BL_GRID, bl_runner, BL_HOLD, data, majors, base, d0, ds, d1, warm)
    res["janela"] = next(iter(res["BOUNCE_LARGO"].values()))["detalhe"]["window"]
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    for h in ("CAP_MERCADO_V2", "BOUNCE_LARGO"):
        for k, v in r[h].items():
            print(h, k, {q: v[q] for q in ("operacoes_fora_amostra", "operacoes_walk_forward", "r_medio_fora_amostra",
                                           "percentil_acaso", "seis_passam", "veredicto")})
