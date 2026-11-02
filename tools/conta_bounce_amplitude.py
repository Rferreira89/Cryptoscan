"""Estudo informativo (2026-11-02): CRITERIO DA CONTA aplicado a BOUNCE_AMPLITUDE.

Nao e uma hipotese nova: e o lutador que ja esta no ringue (tools/arena_ringue.sig_amplitude,
saida G0, os mesmos custos 0,25% + 0,1% por lado, BTC acima da SMA200 diaria), simulado como o
Rui opera (decisao de 2026-11-01): uma conta, juros compostos, no maximo 1 posicao com o valor
todo (e tambem 2 posicoes, metade cada); quando ha varios sinais na mesma vela escolhe-se ao
acaso (200 repeticoes). Regra fixada ANTES de correr, sem grelha:
  metades H1 = 2021-08-01..2024-02-29 e H2 = 2024-03-01..fim do historico (as do H33/H34);
  passa se, nas DUAS metades e a 1x com 1 posicao, a mediana das repeticoes fizer a conta crescer
  E o racio retorno/queda maxima for melhor do que o do BTC comprado sempre na mesma metade.
  A 3x so como informacao (retorno da conta = 3 x retorno no preco).

Uso: python -m tools.conta_bounce_amplitude <pasta_history>
"""
import random
import statistics as st
import sys
import time

from engine import backtest as B, paper_bounce as PB, trade
from tools import arena_ringue as AR

H4, DAY = B.H4, B.DAY
H1 = (1627776000, 1709251199)          # 2021-08-01 .. 2024-02-29
H2_INI = 1709251200                    # 2024-03-01


def operacoes(bars, above, fn=AR.sig_amplitude, amp=True):
    """Operacoes de BOUNCE_AMPLITUDE (mesma simulacao de AR.generic_trades, so passado),
    com hora de entrada, hora de saida e retorno liquido no preco."""
    AR.CTX["bars"] = bars
    out = []
    for a, c4 in sorted(bars.items()):
        AR.CTX["asset"] = a
        busy = -1
        for i in range(250, len(c4) - 1):
            t_sig = c4[i]["t"] + H4
            if i < busy or not AR._known(t_sig, above):
                continue
            if amp:     # atalho exato: sig_amplitude devolve None abaixo de AMP_MIN
                f = AR.amplitude_em(t_sig)
                if f is None or f < AR.AMP_MIN:
                    continue
            sig = fn(c4[:i + 1])
            if not sig:
                continue
            px = c4[i + 1]["o"]
            if not (sig["stop"] < px < sig["tp"][0]):
                continue
            pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"],
                                      PB.FEE_PCT, PB.SLIP_PCT, breakeven=True)
            k = i + 1
            while not pos["closed"] and k < len(c4):
                x = c4[k]
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
                    trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
                    trade._finish(pos, "TIME", x["t"] + H4)
                k += 1
            if not pos["closed"]:
                continue
            busy = k
            out.append({"a": a, "t": pos["opened_at"], "fim": pos["closed_at"], "r": pos["r"],
                        "ret": pos["realized"] / pos["entry"]})
    return out


def conta(ops, ini, fim, vagas=1, alav=1.0, rng=None):
    """Conta com juros compostos: no maximo `vagas` posicoes, cada uma com 1/vagas do valor
    da conta no momento da entrada; sinais na mesma vela por ordem aleatoria."""
    ops = [o for o in ops if ini <= o["t"] <= fim]
    por_t = {}
    for o in ops:
        por_t.setdefault(o["t"], []).append(o)
    m, pico, queda, abertas, n = 1.0, 1.0, 0.0, [], 0
    for t in sorted(por_t):
        for o in [x for x in abertas if x[0]["fim"] <= t]:
            m += o[1] * o[0]["ret"] * alav
            abertas.remove(o)
        pico = max(pico, m)
        queda = max(queda, 1 - m / pico)
        cand = list(por_t[t])
        (rng or random).shuffle(cand)
        livres = [x[0]["a"] for x in abertas]
        for o in cand:
            if len(abertas) >= vagas or o["a"] in livres:
                continue
            abertas.append((o, m / vagas))
            livres.append(o["a"])
            n += 1
    for o in sorted(abertas, key=lambda x: x[0]["fim"]):
        m += o[1] * o[0]["ret"] * alav
        pico = max(pico, m)
        queda = max(queda, 1 - m / pico)
    return max(m, 0.0), queda, n


def btc_hold(btc, ini, fim):
    c = [x["c"] for x in btc if ini <= x["t"] <= fim]
    pico, queda = c[0], 0.0
    for v in c:
        pico = max(pico, v)
        queda = max(queda, 1 - v / pico)
    return c[-1] / c[0], queda


def anual(m, ini, fim):
    anos = (fim - ini) / (365 * DAY)
    return m ** (1 / anos) - 1 if m > 0 else -1.0


def _amp_rapido(c4):
    f = AR.amplitude_em(c4[-1]["t"] + H4)
    return AR.sig_amplitude(c4) if f is not None and f >= AR.AMP_MIN else None


def acaso_por_periodo(bars, above, periodos, seed=7):
    """Teste contra o acaso do proprio ringue (AR.generic_trades + AR.judge) em cada periodo."""
    AR.CTX["bars"] = bars
    trs = []
    for a, c4 in sorted(bars.items()):
        trs += [t for _, t in AR.generic_trades(a, c4, above, 0, "BOUNCE_AMPLITUDE", _amp_rapido)]
    out = {}
    for nome, (ini, fim) in periodos:
        x = [t for t in trs if ini <= t["t"] <= fim]
        out[nome] = AR.judge(x, bars, random.Random(seed)) if x else None
    return out


def main(pasta):
    bars, _ = B.load_all(pasta, min_bars=1500)
    btc = bars["BTC"]
    above = AR.btc_above(btc)
    fim_hist = btc[-1]["t"] + H4
    print("BOUNCE_AMPLITUDE, criterio da conta; fim do historico",
          time.strftime("%Y-%m-%d %H:%M", time.gmtime(fim_hist)), "moedas", len(bars))
    ops = operacoes(bars, above)
    rng = random.Random(20261102)
    passa = True
    for nome, (ini, fim) in (("H1", H1), ("H2", (H2_INI, fim_hist))):
        x = [o for o in ops if ini <= o["t"] <= fim]
        rs = [o["r"] for o in x]
        bm, bq = btc_hold(btc, ini, fim)
        print(f"\n{nome} {time.strftime('%Y-%m-%d', time.gmtime(ini))}..{time.strftime('%Y-%m-%d', time.gmtime(fim))}:"
              f" {len(x)} op. (todas), R medio {st.mean(rs) if rs else 0:+.3f}, acerto"
              f" {100 * sum(r > 0 for r in rs) / max(1, len(rs)):.0f}%, ret. medio no preco"
              f" {100 * st.mean(o['ret'] for o in x) if x else 0:+.2f}%")
        print(f"  BTC comprado sempre: x{bm:.2f} ({100 * anual(bm, ini, fim):+.0f}%/ano), queda max {100 * bq:.0f}%,"
              f" ret/queda {(bm - 1) / max(bq, 1e-9):.2f}")
        for vagas in (1, 2):
            for alav in (1.0, 3.0):
                res = [conta(ops, ini, fim, vagas, alav, rng) for _ in range(200)]
                mm = st.median(r[0] for r in res)
                qq = st.median(r[1] for r in res)
                nn = st.median(r[2] for r in res)
                p_cresce = sum(r[0] > 1 for r in res) / len(res)
                rq = (mm - 1) / max(qq, 1e-9)
                print(f"  {vagas} posicao(oes) {alav:.0f}x: mediana x{mm:.2f} ({100 * anual(mm, ini, fim):+.0f}%/ano),"
                      f" queda max {100 * qq:.0f}%, {nn:.0f} op., cresce em {100 * p_cresce:.0f}% das repeticoes,"
                      f" ret/queda {rq:.2f}")
                if vagas == 1 and alav == 1.0:
                    passa &= mm > 1 and rq > (bm - 1) / max(bq, 1e-9)
    per = (("H1", H1), ("H2", (H2_INI, fim_hist)), ("ultimos 90 dias", (fim_hist - 90 * DAY, fim_hist)),
           ("24 meses", (fim_hist - 730 * DAY, fim_hist)))
    print("\nContra o acaso (metodo do ringue, mesma geometria, entradas ao acaso perto de cada sinal):")
    for nome, j in acaso_por_periodo(bars, above, per).items():
        if j:
            print(f"  {nome}: {j['n']} op., {j['wins']} ganhadoras, R medio {j['avg_r']:+.3f},"
                  f" acaso mediana {j['acaso_mediana']}, p95 {j['acaso_p95']} -> {j['veredicto']}")
    print("\nVEREDICTO DO CRITERIO DA CONTA:", "PASSA" if passa else "CHUMBA")
    return passa


if __name__ == "__main__":
    main(sys.argv[1])
