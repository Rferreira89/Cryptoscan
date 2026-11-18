"""(18/11, ordem final, prioridade 6; investigacao, nada em producao) Acaso da arena: metodo atual ao lado de
controlos neutros a tendencia, com regime, juros, varias sementes e intervalos por grupos de vela.

Para cada operacao real do ringue (AR.generic_trades, ultimo ano; shorts em velas espelhadas, juros descontados),
entradas ao acaso com a MESMA geometria (stop, objetivos, parciais, tempo maximo; custos da arena):
  C0   metodo atual da arena: +-90 velas de 4H a volta da entrada real, sem juros (preservado para comparacao);
  C0j  C0 com juros da margem nos shorts;
  N    neutro: qualquer vela do historico da moeda, com juros;
  NR   neutro, mesmo regime do BTC e so PASSADO: velas anteriores a entrada real cujo regime (dia ANTERIOR, sem olhar
       para o fecho do proprio dia) e igual ao da entrada real; com juros.
Funding: estas operacoes sao spot (compra) e margem spot (short), que pagam juros e nao funding; os juros entram.
5 sementes x 12 entradas por operacao e por controlo. Diferenca real - controlo com intervalo de 90% por bootstrap
de GRUPOS de vela (operacoes que entram no mesmo fecho de 4H contam como um grupo, nao como observacoes
independentes). Separado por estrategia, regime e moeda. Nao muda veredictos nem classificacoes.
Uso: python -m tools.investigacao_arena_acaso <pasta_history> <saida.json>"""
import bisect
import json
import random
import statistics
import sys

from engine import arena, backtest as B, short as SH
from tools import arena_ringue as AR
from tools.investigacao_h18_controlo import controlo

H4, DAY = 4 * 3600, 86400
SEMENTES = (11, 22, 33, 44, 55)
REPS = 12
ESTRATEGIAS = (("TURTLE", "L", "TURTLE"), ("MOMENTUM", "L", "MOMENTUM"), ("BRK_ESPACO", "L", "BRK_ESPACO"),
               ("SHORT_TURTLE", "S", "SHORT_TURTLE"))


def regime_entrada(rmap, t):
    return rmap.get(t // DAY - 1)


def boot_grupos(pares, rng, reps=3000):
    """pares: [(grupo, diferenca)] -> media e IC 90% por bootstrap de grupos."""
    g = {}
    for k, x in pares:
        g.setdefault(k, []).append(x)
    gs = list(g.values())
    if len(gs) < 5:
        return None
    ms = []
    for _ in range(reps):
        s = [x for _ in gs for x in rng.choice(gs)]
        ms.append(sum(s) / len(s))
    ms.sort()
    return {"grupos": len(gs), "ic90": [round(ms[int(.05 * reps)], 4), round(ms[int(.95 * reps)], 4)]}


def resumo(linhas, rng):
    if not linhas:
        return {"n": 0}
    out = {"n": len(linhas), "real": round(statistics.mean(x["r"] for x in linhas), 4)}
    for c in ("C0", "C0j", "N", "NR"):
        v = [x for x in linhas if x.get(c) is not None]
        if not v:
            continue
        out[c] = round(statistics.mean(x[c] for x in v), 4)
        b = boot_grupos([(x["grupo"], x["r"] - x[c]) for x in v], rng)
        out["real_menos_" + c] = round(statistics.mean(x["r"] - x[c] for x in v), 4)
        if b:
            out["ic90_real_menos_" + c] = b["ic90"]
            out["grupos"] = b["grupos"]
        # dispersao entre sementes da media do controlo
        por_semente = [statistics.mean(x[c + "_s"][k] for x in v) for k in range(len(SEMENTES))]
        out[c + "_sementes"] = [round(min(por_semente), 4), round(max(por_semente), 4)]
    return out


def main(folder, dest):
    bars, _ = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    always = {k: True for k in above}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    juros = AR.JUROS_MARGEM_DIA_PCT
    t0 = end - 365 * DAY
    reg_vela = {a: [regime_entrada(rmap, x["t"]) for x in c] for a, c in bars.items()}
    out = {"fim": end, "moedas": len(bars), "juros_margem_dia_pct": juros, "sementes": SEMENTES, "reps": REPS,
           "estrategias": {}}
    for nome, lado, chave in ESTRATEGIAS:
        fn = AR.NEW_SIGS.get(chave) if lado == "L" else AR.SHORT_SIGS[chave]
        if fn is None:
            continue
        jb = bars if lado == "L" else mbars
        jr = juros if lado == "S" else 0.0
        linhas = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            for _, t in AR.generic_trades(a, jb[a], above if lado == "L" else always, t0, nome, fn):
                if lado == "S":
                    t = dict(t, r=t["r"] - AR.juros_short_r(t, juros))
                c4 = jb[a]
                ts = [b["t"] for b in c4]
                i = bisect.bisect_right(ts, t["t"]) - 1
                if i < 0 or not t.get("geo"):
                    continue
                reg = regime_entrada(rmap, t["t"])
                mesmos = [j for j in range(60, i) if reg_vela[a][j] == reg]
                x = {"asset": a, "r": t["r"], "regime": reg, "grupo": t["t"] // H4}
                for c, (lo, hi, jj, pool) in {"C0": (max(0, i - arena.WINDOW), i + arena.WINDOW, 0.0, None),
                                              "C0j": (max(0, i - arena.WINDOW), i + arena.WINDOW, jr, None),
                                              "N": (60, len(c4) - 2, jr, None),
                                              "NR": (0, 0, jr, mesmos)}.items():
                    por_s = []
                    for s in SEMENTES:
                        rng = random.Random(s * 1_000_003 + i)
                        if pool is not None:
                            if not pool:
                                por_s = []
                                break
                            vals = []
                            for _ in range(REPS):
                                j = rng.choice(pool)
                                vals += controlo(c4, j, j, t["geo"], rng, 1, jj)
                        else:
                            vals = controlo(c4, lo, hi, t["geo"], rng, REPS, jj)
                        if not vals:
                            por_s = []
                            break
                        por_s.append(statistics.mean(vals))
                    if por_s:
                        x[c] = statistics.mean(por_s)
                        x[c + "_s"] = por_s
                linhas.append(x)
        rng = random.Random(7)
        moedas = sorted({x["asset"] for x in linhas}, key=lambda m: -sum(1 for x in linhas if x["asset"] == m))[:8]
        out["estrategias"][nome] = {
            "lado": "SHORT" if lado == "S" else "LONG",
            "total": resumo(linhas, rng),
            "por_regime": {g: resumo([x for x in linhas if x["regime"] == g], rng) for g in ("subida", "lateral", "queda")},
            "por_moeda": {m: resumo([x for x in linhas if x["asset"] == m], rng) for m in moedas}}
        print(nome, json.dumps(out["estrategias"][nome]["total"]), flush=True)
        with open(dest, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
