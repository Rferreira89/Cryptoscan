"""Autopsia de BOUNCE_V1 (2026-10-31): o gatilho do Oversold Bounce com as
quatro saidas do papel (G0, V1, V2, V3), nos ultimos 90 dias e 24 meses do
ramo history, com o motivo de saida, a distancia do stop e do 1.o objetivo e
o maximo favoravel (MFE) de cada operacao. So diagnostico: nao e estrategia.

Uso: python -m tools.autopsia_bounce_v1 <pasta_history>
"""
import sys, statistics as st, time
from engine import backtest as B, config, paper_bounce as PB, trade
from tools import arena_ringue as AR
H4, DAY = B.H4, B.DAY
bars, _ = B.load_all(sys.argv[1], min_bars=1500)
cfg = config.load()
btc = bars["BTC"]; above = AR.btc_above(btc)
end = btc[-1]["t"] + H4
reg = AR.regime_by_day(btc) if hasattr(AR, "regime_by_day") else {}
def run(t0):
    out = []
    for a, c4 in sorted(bars.items()):
        busy = {}
        for i in range(PB.HIGH_BARS + 30, len(c4) - 1):
            t_sig = c4[i]["t"] + H4
            if t_sig < t0 or not AR._known(t_sig, above): continue
            sig = PB.signal(c4[max(0, i - 299):i + 1])
            if not sig: continue
            px = c4[i + 1]["o"]
            try:
                a4 = B._tf(c4[max(0, i + 1 - B.WINDOW):i + 1])
                d1 = [x for x in B.daily(c4[:i + 1]) if x["t"] + DAY <= t_sig]
                a1 = B._tf(d1[-B.WINDOW:])
                if not (a4.get("ok") and a1.get("ok")): a4 = a1 = None
            except Exception: a4 = a1 = None
            for g, p in PB.plans(sig, px, a4, a1, cfg).items():
                if busy.get(g, 0) > i: continue
                pos = trade.open_position(p, px, c4[i+1]["t"], PB.FEE_PCT, PB.SLIP_PCT, breakeven=p["breakeven"])
                k = i + 1; mfe = 0
                while not pos["closed"] and k < len(c4):
                    x = c4[k]; mfe = max(mfe, (x["h"] - px) / (px - p["stop"]))
                    trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + H4)
                    if not pos["closed"] and x["t"] + H4 - pos["opened_at"] >= PB.GEOS[g]["hold"]:
                        trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"])); trade._finish(pos, "TIME", x["t"] + H4)
                    k += 1
                if not pos["closed"]: continue
                busy[g] = k
                out.append(dict(g=g, a=a, t=pos["opened_at"], r=pos["r"], why=pos["exit_reason"], bars=k-i-1,
                    stop=1-p["stop"]/px, tp1=p["tp"][0]/px-1, ntp=len(p["tp"]), mfe=mfe, rg=reg.get((pos["opened_at"]-DAY)//DAY)))
    return out
def show(trs, lab):
    for g in ("G0","V1","V2","V3"):
        x=[t for t in trs if t["g"]==g]
        if not x: continue
        rs=[t["r"] for t in x]; why={}
        for t in x: why[t["why"]]=why.get(t["why"],0)+1
        print(lab,g,len(x),"avgR %.3f"%st.mean(rs),"acerto %.0f%%"%(100*sum(r>0 for r in rs)/len(rs)),
              "stop%% med %.2f"%(100*st.median(t["stop"] for t in x)),"tp1%% med %.2f"%(100*st.median(t["tp1"] for t in x)),
              "barras med",st.median(t["bars"] for t in x), why)
print("fim do historico", time.strftime("%Y-%m-%d %H:%M", time.gmtime(end)))
r90 = run(end - 90*DAY); show(r90, "90d")
for t in [t for t in r90 if t["g"]=="V1"]:
    print(" ", time.strftime("%m-%d %H", time.gmtime(t["t"])), t["a"], "%.2f"%t["r"], t["why"], t["bars"], "stop %.1f%% tp1 %.1f%% ntp %d mfe %.2fR"%(100*t["stop"],100*t["tp1"],t["ntp"],t["mfe"]), t["rg"])
r24 = run(end - 730*DAY); show(r24, "24m")
