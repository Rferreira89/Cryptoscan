"""Afinacao H13 (2026-11-04): Tartarugas com o filtro do Sistema 1 (TURTLE_S1).

O gatilho e o do TURTLE do ringue (fecho de 4H acima do maximo dos 20 dias
diarios completos anteriores, fecho anterior abaixo; stop 2N; 2R/5R; stop que
segue; 20 dias). Filtro do Sistema 1 (Dennis/Faith): so se toma o rompimento se
o rompimento hipotetico anterior na mesma moeda foi PERDEDOR (bateu o stop de
2N antes da saida pelo minimo de 10 dias). So dias diarios fechados.
Grelha escrita antes de testar (afinacao.md, H13).

Uso: python -m tools.afinacao_h13_turtle_s1 <pasta_history> <saida.json> [T0 T1 ...]
"""
import bisect
import json
import sys

from engine import backtest as B
from tools import arena_ringue as AR
from tools.afinacao_h09_racio import B_END, B_START
from tools.afinacao_h10_racio_short import summary

DAY, H4 = AR.DAY, AR.H4

# nome: (filtro, fases, rede de 55 dias)
#   filtro: None (sem filtro), "perdedor" (Sistema 1), "ganhador" (controlo invertido)
GRID = {
    "T0": (None, None, False),
    "T1": ("perdedor", None, False),
    "T2": ("perdedor", ("lateral",), False),
    "T3": ("perdedor", ("subida",), False),
    "T4": ("perdedor", None, True),
    "T5": ("ganhador", None, False),
}

_dias = AR._diario          # no estudo troca-se por uma versao rapida equivalente


def _n20(d):
    """N das Tartarugas: media do true range dos ultimos 20 dias de d."""
    tr = [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"])
          for k in range(len(d) - 20, len(d))]
    return sum(tr) / 20


RECENTE = 3     # dias: um rompimento hipotetico ainda aberto e mais novo do que isto e o atual


def estado_s1(d, n=20, saida=10, recente=RECENTE):
    """Percorre os dias fechados d e simula os rompimentos hipoteticos de n dias
    (tomados ou nao), um de cada vez. Devolve (ultimo, aberto): ultimo =
    "perdedor", "ganhador" ou None (nenhum resolvido); aberto = ha um ainda por
    resolver no fim de d que comecou ha mais de `recente` dias (um mais novo e
    o proprio rompimento atual, que furou o maximo num dia anterior sem fechar
    a vela de 4H acima dele, e nao conta como "anterior")."""
    ultimo, pos, inicio = None, None, None
    for j in range(max(n, saida) + 1, len(d)):
        x = d[j]
        if pos is not None:
            if x["l"] <= pos:
                ultimo, pos = "perdedor", None
            elif x["l"] < min(y["l"] for y in d[j - saida:j]):
                ultimo, pos = "ganhador", None
            continue
        hi = max(y["h"] for y in d[j - n:j])
        if x["h"] > hi:
            entry = max(hi, x["o"])
            pos, inicio = entry - 2 * _n20(d[:j]), j
    return ultimo, pos is not None and len(d) - inicio > recente


def _rompe(c4, d, n):
    """Plano das Tartarugas se a ultima vela de 4H rompe o maximo de n dias."""
    if len(d) < n + 5:
        return None
    hi = max(x["h"] for x in d[-n - 1:-1])
    if not (c4[-1]["c"] > hi >= c4[-2]["c"]):
        return None
    return AR._trend_plan(c4, c4[-1]["c"] - 2 * _n20(d),
                          gat=f"rompimento do máximo de {n} dias ({hi:.6g})")


def turtle_s1(filtro="perdedor", fases=None, rede55=False):
    """Funcao de sinal (formato NEW_SIGS)."""
    def f(c4):
        if len(c4) < 2:
            return None
        if fases and AR._fase_btc(c4[-1]["t"] + H4) not in fases:
            return None
        d = _dias(c4)
        if rede55:
            s55 = _rompe(c4, d, 55)
            if s55:
                return dict(s55, gatilho=s55["gatilho"] + " (rede do Sistema 1)")
        s = _rompe(c4, d, 20)
        if not s or filtro is None:
            return s
        ultimo, aberto = estado_s1(d)
        if aberto or ultimo != filtro:
            return None
        return dict(s, gatilho=s["gatilho"] + f"; o rompimento anterior foi {ultimo}")
    return f


def dias_rapido(daily):
    """Versao rapida de AR._diario com os dias de cada moeda ja calculados:
    mesmos dias (completos e fechados ate a ultima vela de 4H)."""
    ts = {a: [x["t"] for x in d] for a, d in daily.items()}

    def f(c4):
        a = AR.CTX.get("asset")
        fim = c4[-1]["t"] + H4
        k = bisect.bisect_right(ts[a], fim - DAY)
        return daily[a][:k]
    return f


def main(folder, dest, only=None):
    global _dias
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    daily = {a: B.daily(c) for a, c in bars.items()}
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    _dias = dias_rapido(daily)
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            trs += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, key, turtle_s1(*cfg))]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        for k in ("B", "A", "C90", "L365"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
