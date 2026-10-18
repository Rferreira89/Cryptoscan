"""Auditoria de sinais (pedido do Rui, 2026-10-18: "porque nao estao a ser
executadas operacoes? quantifica os sinais rejeitados e explica porque").

Repete, vela a vela de 4H e com dados reais da Binance, o que os campeoes da
arena teriam feito nos ultimos DIAS dias em todas as moedas da Bybit UE, e
passa cada sinal pelos mesmos filtros do sistema ao vivo:

  1. filtro de mercado (BTC acima da SMA200 no fecho do dia anterior);
  2. liquidez da Bybit UE hoje (volume, spread, preco desatualizado);
  3. plano real (engine/promo.plan_for com a configuracao em uso);
  4. regras de carteira por ordem cronologica: maximo de operacoes em
     simultaneo, maximo por familia, maximo por vela de 4H, uma so aposta.

Para cada sinal simula tambem o resultado (mesmas saidas do combate), para
medir o que foi ganho ou perdido com cada filtro. Mede ainda, por moeda, o
RSI de 4H mais baixo dos ultimos 4 dias: a familia "sobrevenda" so dispara
abaixo de 25, e e isso que diz se houve ou nao oportunidade.

Limites honestos: o Diretor (R1-R6) nao e repetido (usa derivados e livro
do momento) e a liquidez e a de hoje, nao a de cada dia.

So le dados. Nunca envia ordens nem mexe no estado.
Uso: python -m tools.auditoria_sinais saida.json [dias]
"""
import json
import os
import sys
import time

from engine import backtest as B, config, europa, promo, trade, venue
from engine import paper_bounce as PB
from tools import arena_ringue as AR

H4 = 14400
DAY = 86400


def rsi_min(c4, bars=24):
    c = [x["c"] for x in c4]
    rs = PB.rsi(c)
    vals = [x for x in rs[-bars:] if x is not None]
    return round(min(vals), 1) if vals else None


def simulate(sig, c4, i):
    """Resultado em R do sinal da vela i, entrada na abertura seguinte."""
    if i + 1 >= len(c4):
        return None, None
    px = c4[i + 1]["o"]
    if not (sig["stop"] < px < sig["tp"][0]):
        return None, None
    pos = trade.open_position(dict(sig, max_hold_s=None), px, c4[i + 1]["t"], PB.FEE_PCT,
                              PB.SLIP_PCT, breakeven=sig.get("breakeven", True))
    k = i + 1
    while not pos["closed"] and k < len(c4):
        x = c4[k]
        trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
        if not pos["closed"] and sig.get("hold_s") and x["t"] + H4 - pos["opened_at"] >= sig["hold_s"]:
            trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
            trade._finish(pos, "TIME", x["t"] + H4)
        k += 1
    if not pos["closed"]:
        return "aberta", c4[-1]["c"] / px - 1
    return round(pos["r"], 2), pos.get("closed_at")


def metricas(sinais, days, risco_pct, seed=7, caminhos=2000, n_ops=100):
    """Carteira inteira (so os sinais que passam todos os filtros): expectativa,
    drawdown maximo, crescimento por mes e risco de ruina por Monte Carlo
    (perder metade do capital em n_ops operacoes, com o risco atual)."""
    import random
    rs = [s["r"] for s in sinais if s.get("passa") and isinstance(s["r"], (int, float))]
    if not rs:
        return {"n": 0}
    cum = peak = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    rng = random.Random(seed)
    f = risco_pct / 100
    ruina = 0
    for _ in range(caminhos):
        eq = 1.0
        for _ in range(n_ops):
            eq *= 1 + f * rng.choice(rs)
            if eq <= 0.5:
                ruina += 1
                break
    ops_mes = len(rs) * 30 / days
    exp = sum(rs) / len(rs)
    return {"n": len(rs), "ganhos": sum(1 for r in rs if r > 0), "expectativa_r": round(exp, 3),
            "total_r": round(sum(rs), 2), "drawdown_max_r": round(dd, 2),
            "ops_mes": round(ops_mes, 1), "crescimento_mes_pct": round(ops_mes * exp * risco_pct, 2),
            "risco_pct": round(risco_pct, 2), "ruina_50pct": round(ruina / caminhos, 3)}


def main(dest, days=14):
    now = int(time.time())
    scan = json.load(open(os.environ.get("SCAN_JSON", "/tmp/scan.json")))
    state = json.load(open(os.environ.get("STATE_JSON", "/tmp/state.json")))
    cfg = dict(config.DEFAULTS, **scan["config"])
    disabled = set(scan.get("disabled_strategies") or {})
    champs = promo.champions(state, disabled)
    reg = AR.SINAIS
    ven = venue.fetch("USDC")
    need = 6 * (B.analysis.MIN_BARS + 15) + 6 * days
    bars, falhas = {}, []
    for base in sorted(set(ven) | {"BTC"}):
        try:
            c = AR.fetch(base, now, max(need, 1300 if base == "BTC" else need))
        except Exception as e:
            falhas.append(f"{base}: {str(e)[:40]}")
            continue
        if len(c) >= 300:
            bars[base] = c
        time.sleep(0.1)
    above = AR.btc_above(bars["BTC"])
    eu = europa.load(europa.MAX_AGE_RING, now)
    funding, oi, ls = {}, {}, {}
    for base in bars:
        c = europa.coin(eu, base) or {}
        if c.get("funding"):
            funding[base] = [tuple(x) for x in c["funding"]]
        if c.get("oi"):
            oi[base] = [tuple(x) for x in c["oi"]]
        if c.get("ls"):
            ls[base] = [tuple(x) for x in c["ls"]]
    macro = {k: [tuple(x) for x in v] for k, v in ((eu or {}).get("macro") or {}).items()}
    AR.CTX.update(btc=bars["BTC"], funding=funding, oi=oi, macro=macro, ls=ls, bars=bars, rank={})

    t0 = now - days * DAY
    sinais, quase = [], []
    for a, c4 in sorted(bars.items()):
        quase.append((rsi_min(c4), a))
        AR.CTX["asset"] = a
        v = ven.get(a)
        liq_ok, liq_why = venue.check(v, None, cfg)
        ocupada = 0                            # uma operacao de cada vez por moeda (como ao vivo)
        for i in range(260, len(c4)):
            t_sig = c4[i]["t"] + H4
            if t_sig < t0 or t_sig < ocupada:
                continue
            px = c4[i + 1]["o"] if i + 1 < len(c4) else c4[i]["c"]
            for rank, k in enumerate(champs):
                try:
                    sig = reg[k](c4[:i + 1], px, cfg)
                except Exception:
                    sig = None
                if not sig:
                    continue
                row = {"t": t_sig, "ativo": a, "campeao": k, "rank": rank,
                       "familia": promo.family(k)}
                if not AR._known(t_sig, above):
                    row["filtro"] = "mercado: BTC abaixo da SMA200"
                elif not liq_ok:
                    row["filtro"] = "liquidez Bybit UE: " + ", ".join(liq_why)
                else:
                    p, why = promo.plan_for(sig, px, cfg)
                    if not p:
                        row["filtro"] = "plano: " + str(why)
                    else:
                        row["plano"] = {"pos": p.get("position_usdc"), "risco": p.get("risk_usdc"),
                                        "stop_pct": p.get("stop_pct"), "rr_tp1": p.get("rr_tp1")}
                r, fim = simulate(sig, c4, i)
                row["r"], row["fim"] = r, fim
                ocupada = fim if isinstance(r, (int, float)) else float("inf")
                sinais.append(row)
                break                          # o melhor campeao com sinal ganha a moeda
    # regras de carteira, por ordem cronologica (como ao vivo)
    sinais.sort(key=lambda x: (x["t"], x["rank"]))
    abertas = []                               # (fim, familia)
    por_vela = {}
    for s in sinais:
        if "filtro" in s:
            continue
        abertas = [x for x in abertas if x[0] is None or x[0] > s["t"]]
        fam = sum(1 for x in abertas if x[1] == s["familia"])
        n = por_vela.setdefault(s["t"], {})
        if len(abertas) >= cfg.get("max_open_positions", 4):
            s["filtro"] = "carteira: limite de operações em simultâneo"
        elif fam >= promo.MAX_PER_FAMILY:
            s["filtro"] = f"carteira: família {s['familia']} já com {fam} abertas"
        elif n.get(s["familia"], 0) >= 1:
            s["filtro"] = "carteira: uma só aposta por família e vela (ficou o melhor)"
        else:
            n[s["familia"]] = n.get(s["familia"], 0) + 1
            s["passa"] = True
            fim = s["fim"] if isinstance(s["r"], (int, float)) else None
            abertas.append((fim, s["familia"]))
    resumo = {}
    for s in sinais:
        k = "PASSA" if s.get("passa") else s["filtro"].split(":")[0]
        b = resumo.setdefault(k, {"n": 0, "r": 0.0, "fechados": 0})
        b["n"] += 1
        if isinstance(s["r"], (int, float)):
            b["r"] = round(b["r"] + s["r"], 2)
            b["fechados"] += 1
    risco = 100 * (cfg.get("max_risk_usdc") or 0) / (cfg.get("capital_usdc") or 1)
    out = {"gerado": now, "dias": days, "carteira": metricas(sinais, days, risco),
           "nota": "campeões de hoje aplicados ao passado: dentro da amostra, otimista", "moedas": len(bars), "campeoes": champs,
           "desligadas": sorted(disabled), "sinais": sinais, "resumo": resumo,
           "rsi_min_4d": sorted([q for q in quase if q[0] is not None])[:20],
           "falhas": falhas[:20]}
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"moedas {len(bars)}  campeoes {len(champs)}  sinais {len(sinais)}")
    for k, v in resumo.items():
        print(f"  {k:12s} n={v['n']:3d}  R simulado={v['r']:+.2f} ({v['fechados']} fechados)")
    for s in sinais:
        print(time.strftime("%m-%d %H:%M", time.gmtime(s["t"])), f"{s['ativo']:8s} {s['campeao']:18s}",
              "PASSA" if s.get("passa") else s["filtro"], "R=", s["r"])
    print("RSI 4H mais baixo (4 dias):", out["rsi_min_4d"][:12])
    print("carteira:", out["carteira"])


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 14)
