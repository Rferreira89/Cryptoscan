"""Investigacao 2026-11-17: BOUNCE_ALVO, sucessor da arena de BOUNCE_LARGO_X30V20 / X35V20 (so compras).
Pre-registo em backtest/investigacao.md (escrito e guardado em commit antes de correr).

Autopsia: o 1.o objetivo (SMA20 de 4H) fica a menos de 1R da entrada em ~70% das operacoes (mediana 0,6R-0,8R);
vende 50% ai e passa o stop para a entrada, logo ganha ~0,4R quando acerta e perde 1R quando falha.

Correcao unica: exatamente BOUNCE_LARGO (tools.research_fase_agressiva.bl_signals: BTC acima da SMA200, RSI14 4H
< X numa das ultimas 3 velas, fecho acima do maximo anterior com RSI a subir, volume >= 2x a media de 20; stop
min(minimo 6 velas - 0,1 ATR, fecho - 1,25 ATR); 50% na SMA20, resto no maximo de 42 velas; stop na entrada depois
do 1.o; 5 dias), so quando (SMA20 - fecho) >= M x (fecho - stop) no fecho da vela do sinal.

Grelha (4): X in {30, 35} x M in {1,0; 1,25}; V = 2,0.
Metodo e criterios: os de tools/research_fase_agressiva (cada combinacao sozinha), com PARA PAPEL so com
percentil >= 90 E R medio fora da amostra > 0.

Uso: python -m tools.research_bounce_alvo <historico> [saida.json]
"""
import json
import sys

from engine import backtest as B
from tools import research_fase_agressiva as FA
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
V = 2.0
GRID = [{"X": x, "M": m} for x in (30, 35) for m in (1.0, 1.25)]
HOLD = 5 * R.DAY


def alvo_ok(sig, close, m):
    """1.o objetivo pelo menos m x o risco acima do fecho da vela do sinal."""
    risk = close - sig["stop"]
    return risk > 0 and sig["tp"][0] - close >= m * risk


def signals(c4, btc_up, x, m):
    """{t da abertura da entrada: sinal}. Usa so as velas 0..i (as de bl_signals) e o fecho de i."""
    base = FA.bl_signals(c4, btc_up, x, V)
    idx = {b["t"] + TF: i for i, b in enumerate(c4)}
    return {te: s for te, s in base.items() if alvo_ok(s, c4[idx[te]]["c"], m)}


def veredicto(linha):
    """AMOSTRA INSUFICIENTE (< 40 no walk-forward) manda sobre CANDIDATA; PARA PAPEL acrescenta-se (>= p90 e R > 0)."""
    r, p = linha["r_medio_fora_amostra"], linha["percentil_acaso"]
    papel = p is not None and p >= FA.PCTIL_MIN and r is not None and r > 0
    if linha["operacoes_walk_forward"] < 40:
        base = "AMOSTRA INSUFICIENTE"
    elif linha["seis_passam"] and p is not None and p > 95 and r is not None and r > 0:
        base = "CANDIDATA"
    else:
        base = "NAO VALIDADA"
    return base + (" — PARA PAPEL" if papel else "")


def main(folder, out="backtest/research_bounce_alvo.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    warm = days[0] + 210
    cache = {}

    def runner(cfg, universe):
        k = (cfg["X"], cfg["M"])
        if k not in cache:
            cache[k] = {a: signals(data[a], btc_up, *k) for a in data}
        return R.simulate(data, cache[k], TF, HOLD, universe)

    res = {"moedas": len(data), "ultima_vela_btc": data["BTC"][-1]["t"]}
    linhas, share = FA.correr("BOUNCE_ALVO", GRID, runner, HOLD, data, majors, base, d0, ds, d1, warm)
    for v in linhas.values():
        v["veredicto_fase"] = v["veredicto"]          # a regra de 14/11 (so o percentil)
        v["veredicto"] = veredicto(v)
    res["BOUNCE_ALVO"], res["fracao_grelha"] = linhas, share
    res["janela"] = next(iter(linhas.values()))["detalhe"]["window"]
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    print(r["janela"], "fracao grelha", r["fracao_grelha"])
    for k, v in r["BOUNCE_ALVO"].items():
        d = v["detalhe"]
        print(k, {q: v[q] for q in ("operacoes_fora_amostra", "operacoes_walk_forward", "operacoes_reserva",
                                    "r_medio_fora_amostra", "acaso_mediana", "percentil_acaso", "seis_passam",
                                    "veredicto_fase", "veredicto")})
        print("   criterios", v["criterios"])
        print("   desenho", v["desenho"], "| oos", {q: d["walk_forward"]["oos"].get(q) for q in ("return_pct", "max_dd_pct", "sharpe")},
              "| reserva", {q: d["holdout"]["all"].get(q) for q in ("return_pct", "max_dd_pct", "sharpe")},
              d["holdout"]["trades"], "| base reserva", d["holdout"]["baseline_btc_sma200"].get("return_pct"),
              "| oos trades", d["walk_forward"]["oos_trade_stats"], "| antigo", (d.get("info_old_period") or {}).get("trades"))
