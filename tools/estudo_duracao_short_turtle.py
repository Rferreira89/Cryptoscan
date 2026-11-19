"""(19/11, ordem do Rui, ponto 2C) SHORT_TURTLE por DURACAO: expectativa liquida se a operacao fosse fechada ao fim
de 1, 2, 3, 5, 7, 10, 15 e 20 dias, e valor de CONTINUAR uma operacao ainda aberta ao fim de k dias.

So estudo (backtest): nao muda estrategias, saidas, risco nem nada do trading real.

Sinal: o mesmo da SHORT_TURTLE ao vivo (tools/arena_ringue.SHORT_SIGS["SHORT_TURTLE"] no espelho 1/preco,
convertido por short_live): fecho de 4H abaixo do minimo dos 20 dias completos anteriores (excluindo o ultimo
dia completo, como sig_turtle), stop a 2N do espelho, objetivo = 2R do espelho. Geometria das posicoes reais de hoje
(contas pequenas: parciais [100,0,0], 100% no 1.o objetivo; o breakeven e o stop que segue so atuam depois do
objetivo, por isso nao entram). Equivalencia com a funcao do ringue verificada em testes.

Sem look-ahead: sinal com a vela de 4H fechada; entrada na abertura da vela seguinte; regime do BTC
(engine.arena.market_regime) so com dias fechados ate ao sinal. Universo com moedas ainda listadas e DESLISTADAS
(ramos history + history-delistadas). Custos: comissao 0,25% por lado e deslize 0,1% (os do ringue), juro do
emprestimo por dia (0,03%/dia por omissao; sensibilidade em JURO_DIA), stop com o deslize e com o salto de abertura.
Mesmo vela com stop e objetivo: conta o stop (pessimista).

Amostras correlacionadas: o intervalo de confianca e por bootstrap em BLOCOS de semana (todas as operacoes que
entram na mesma semana saem ou ficam juntas), nao por operacao.

Uso: python3 -m tools.estudo_duracao_short_turtle <pasta_csv_4h> <saida.json>"""
import json
import os
import random
import sys
import time

from engine import arena, backtest as B

H4, DAY = 14400, 86400
FEE = float(os.environ.get("FEE", "0.0025"))       # (19/11) por corretora: Bybit UE spot 0,25%; OKX futuros 0,05% taker
SLIP = float(os.environ.get("SLIP", "0.001"))
JURO_DIA = float(os.environ.get("JURO_DIA", "0.0003"))
DIAS = (1, 2, 3, 5, 7, 10, 15, 20)
HOLD = 20 * DAY
INICIO_DIAS = 25


def diario(c4):
    return B.daily(c4)


def sinais(c4, d=None):
    """[(i, stop_real, tp_real)] em que a vela i (fechada) da o sinal. Igual a short_live(SHORT_SIGS['SHORT_TURTLE'])
    com px = fecho da vela i."""
    d = d if d is not None else diario(c4)
    out = []
    dts = [x["t"] for x in d]
    import bisect
    for i in range(1, len(c4)):
        b = c4[i]
        k = bisect.bisect_right(dts, b["t"] + H4 - DAY)          # dias completos ate ao fecho da vela i
        if k < INICIO_DIAS:
            continue
        dd = d[:k]
        lo20 = min(x["l"] for x in dd[-21:-1])                  # espelho: hi20 = 1/lo20
        c, prev = b["c"], c4[i - 1]["c"]
        cm, pm_prev, hi20m = 1 / c, 1 / prev, 1 / lo20
        if not (cm > hi20m >= pm_prev):
            continue
        tr = []
        for j in range(len(dd) - 20, len(dd)):
            hm, lm, pcm = 1 / dd[j]["l"], 1 / dd[j]["h"], 1 / dd[j - 1]["c"]
            tr.append(max(hm, pcm) - min(lm, pcm))
        n = sum(tr) / 20
        stop_m = cm - 2 * n
        if not 0 < stop_m < cm * 0.995:
            continue
        r_m = cm - stop_m
        tp_m = cm + 2 * r_m
        if not (stop_m < cm < tp_m):
            continue
        out.append((i, 1 / stop_m, 1 / tp_m))
    return out


def simular(c4, i, stop, tp, juro_dia=JURO_DIA):
    """Short a abrir na vela i+1. Devolve a trajetoria: lista de (t_fecho_vela, R_se_fechasse_ao_fecho) ate a saida,
    e o resultado final {'r', 'motivo', 'dur_s', 'mae', 'mfe'} (R liquido: comissoes, deslize, juro)."""
    if i + 1 >= len(c4):
        return None
    e = c4[i + 1]["o"] * (1 - SLIP)
    risco = stop - e + FEE * (e + stop)
    if risco <= 0 or tp >= e:
        return None
    t0 = c4[i + 1]["t"]
    traj, mae, mfe = [], 0.0, 0.0

    def r_saida(px, t):
        dias = max(0.0, (t - t0) / DAY)
        return (e - px - FEE * (e + px) - juro_dia * dias * e) / risco

    for j in range(i + 1, len(c4)):
        b = c4[j]
        tf = b["t"] + H4
        mae = min(mae, (e - b["h"]) / risco)
        mfe = max(mfe, (e - b["l"]) / risco)
        if b["h"] >= stop:
            px = max(stop, b["o"]) * (1 + SLIP)
            return traj, {"r": r_saida(px, tf), "motivo": "stop", "dur_s": tf - t0, "mae": mae, "mfe": mfe}
        if b["l"] <= tp:
            px = min(tp, b["o"]) if b["o"] < tp else tp
            return traj, {"r": r_saida(px, tf), "motivo": "objetivo", "dur_s": tf - t0, "mae": mae, "mfe": mfe}
        if tf - t0 >= HOLD:
            px = b["c"] * (1 + SLIP)
            return traj, {"r": r_saida(px, tf), "motivo": "tempo", "dur_s": tf - t0, "mae": mae, "mfe": mfe}
        traj.append((tf - t0, r_saida(b["c"] * (1 + SLIP), tf)))
    return traj, None                                   # ainda aberta no fim dos dados: fica de fora (sem inventar)


def r_ao_fim_de(traj, fim, k):
    """R se a regra fosse 'fechar ao fim de k dias' (com o stop e o objetivo a atuar antes)."""
    if fim["dur_s"] <= k * DAY:
        return fim["r"]
    alvo = k * DAY
    for dt, r in traj:
        if dt >= alvo:
            return r
    return fim["r"]


def aberta_em(traj, fim, k):
    return fim["dur_s"] > k * DAY


def r_marcado(traj, k):
    for dt, r in traj:
        if dt >= k * DAY:
            return r
    return None


def boot(xs_por_bloco, n=2000, seed=19):
    """IC 90% da media por bootstrap em blocos (semana de entrada)."""
    blocos = [v for v in xs_por_bloco.values() if v]
    if len(blocos) < 5:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(n):
        amostra = [x for _ in blocos for x in blocos[rng.randrange(len(blocos))]]
        ms.append(sum(amostra) / len(amostra))
    ms.sort()
    return [round(ms[int(0.05 * n)], 3), round(ms[int(0.95 * n)], 3)]


def resumir(ops, campo):
    xs = [o[campo] for o in ops if o.get(campo) is not None]
    if not xs:
        return {"n": 0}
    por = {}
    for o in ops:
        if o.get(campo) is not None:
            por.setdefault(o["semana"], []).append(o[campo])
    return {"n": len(xs), "semanas": len(por), "media_r": round(sum(xs) / len(xs), 3), "ic90": boot(por),
            "acerto_pct": round(100 * sum(x > 0 for x in xs) / len(xs), 1)}


def correr(pasta, juro_dia=JURO_DIA):
    data, ignorados = B.load_all(pasta, min_bars=600)
    btc_d = diario(data["BTC"]) if "BTC" in data else []
    bts = [x["t"] for x in btc_d]
    import bisect
    regime_cache = {}

    def regime(t):
        k = bisect.bisect_right(bts, t - DAY)
        if k not in regime_cache:
            regime_cache[k] = arena.market_regime(btc1d=btc_d[:k]) if k >= 200 else None
        return regime_cache[k]

    ops = []
    for a, c4 in data.items():
        d = diario(c4)
        ocupado_ate = 0
        for i, stop, tp in sinais(c4, d):
            t_sig = c4[i]["t"] + H4
            if t_sig < ocupado_ate:                    # uma posicao por moeda (como ao vivo)
                continue
            s = simular(c4, i, stop, tp, juro_dia)
            if not s or s[1] is None:
                continue
            traj, fim = s
            ocupado_ate = c4[i + 1]["t"] + fim["dur_s"]
            o = {"ativo": a, "t": t_sig, "semana": t_sig // (7 * DAY), "regime": regime(t_sig), **fim,
                 "stop_pct": round(100 * (stop / c4[i + 1]["o"] - 1), 2)}
            for k in DIAS:
                o[f"r_fecho_{k}d"] = r_ao_fim_de(traj, fim, k)
                if aberta_em(traj, fim, k):
                    rm = r_marcado(traj, k)
                    o[f"cont_{k}d"] = fim["r"] - rm if rm is not None else None      # valor de continuar
                    o[f"marca_{k}d"] = rm
            ops.append(o)
    ops.sort(key=lambda o: o["t"])
    return ops, ignorados


def relatorio(ops):
    out = {}
    meio = ops[len(ops) // 2]["t"] if ops else 0
    grupos = {"todas": ops, "lateral": [o for o in ops if o["regime"] == "lateral"],
              "queda": [o for o in ops if o["regime"] == "queda"], "subida": [o for o in ops if o["regime"] == "subida"],
              "lateral_1a_metade": [o for o in ops if o["regime"] == "lateral" and o["t"] < meio],
              "lateral_2a_metade": [o for o in ops if o["regime"] == "lateral" and o["t"] >= meio],
              "ultimo_ano": [o for o in ops if o["t"] >= ops[-1]["t"] - 365 * DAY] if ops else []}
    for nome, g in grupos.items():
        if not g:
            out[nome] = {"n": 0}
            continue
        r = {"n": len(g), "de": time.strftime("%Y-%m-%d", time.gmtime(g[0]["t"])),
             "ate": time.strftime("%Y-%m-%d", time.gmtime(g[-1]["t"])),
             "final_20d": resumir(g, "r"),
             "motivos": {m: {"n": sum(o["motivo"] == m for o in g),
                             "media_r": round(sum(o["r"] for o in g if o["motivo"] == m) / max(1, sum(o["motivo"] == m for o in g)), 3),
                             "dur_media_dias": round(sum(o["dur_s"] for o in g if o["motivo"] == m) / DAY / max(1, sum(o["motivo"] == m for o in g)), 1)}
                         for m in ("stop", "objetivo", "tempo")},
             "mae_media_r": round(sum(o["mae"] for o in g) / len(g), 3), "mfe_media_r": round(sum(o["mfe"] for o in g) / len(g), 3),
             "dur_media_dias": round(sum(o["dur_s"] for o in g) / len(g) / DAY, 1),
             "fechar_ao_fim_de": {f"{k}d": resumir(g, f"r_fecho_{k}d") for k in DIAS},
             "continuar_se_aberta_ao_fim_de": {f"{k}d": dict(resumir(g, f"cont_{k}d"),
                                                             abertas_pct=round(100 * sum(o.get(f"cont_{k}d") is not None for o in g) / len(g), 1))
                                               for k in DIAS[:-1]}}
        # as abertas ao fim de 5 dias perto do zero (como a XLM hoje): -0,25R a +0,25R marcados
        perto = [o for o in g if o.get("marca_5d") is not None and -0.25 <= o["marca_5d"] <= 0.25]
        r["continuar_5d_perto_de_zero"] = resumir(perto, "cont_5d")
        out[nome] = r
    return out


if __name__ == "__main__":
    t0 = time.time()
    ops, ign = correr(sys.argv[1])
    rel = {"t": int(time.time()), "juro_dia": JURO_DIA, "custos": {"comissao_lado": FEE, "deslize": SLIP},
           "moedas": len({o["ativo"] for o in ops}), "ignoradas": len(ign), "resultados": relatorio(ops),
           "segundos": round(time.time() - t0, 1)}
    with open(sys.argv[2], "w") as f:
        json.dump(rel, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: rel[k] for k in ("moedas", "ignoradas", "segundos")}))
