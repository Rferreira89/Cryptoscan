"""So os lutadores SHORT da arena (o resto fica vazio para ser rapido), com o codigo real de tools/arena_ringue.run."""
import json, sys, time
sys.path.insert(0, ".")
from engine import backtest as B, config
from tools import arena_ringue as AR
G, dias, variante, saida = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
St = json.load(open(G + "/pub4/state.json"))
tk = set(St["bybit_tickers"]["m"]); mg = set(St["margem_bybit"]["moedas"])
bars, _ = B.load_all(G + "/hist", min_bars=1500)
bars = {a: c for a, c in bars.items() if a in tk or a == "BTC"}
now = bars["BTC"][-1]["t"] + AR.H4
for f in ("live_trades", "bounce_trades", "trend_trades", "bounce_1h_trades"):
    setattr(AR, f, lambda *a, **k: [])
AR.NEW_SIGS = {}
cap = []
orig = AR.generic_trades
def gravar(asset, c4, above, t0, key, fn):
    out = orig(asset, c4, above, t0, key, fn)
    cap.extend({"k": k, "asset": t["asset"], "t": t["t"], "t_fim": t.get("t_fim"), "r": t["r"], "stop": t["geo"]["stop"]} for k, t in out)
    return out
AR.generic_trades = gravar
cfg = config.load()
cfg["juros_margem_dia_pct"] = 0.0 if variante in ("antiga", "margem") else 0.03
m = None if variante == "antiga" else mg
t = time.time()
r = AR.run(bars, cfg, now, dias, margem=m, regimes=dias > 200)
lut = {k: v for k, v in r["lutadores"].items() if k.startswith("SHORT")}
json.dump({"variante": variante, "dias": dias, "now": now, "moedas": sorted(bars), "margem": sorted(mg),
           "lutadores": lut, "operacoes": cap, "segundos": round(time.time() - t)}, open(saida, "w"))
print(variante, dias, "ok", round(time.time() - t), "s", {k: (v["n"], v["avg_r"], v["veredicto"]) for k, v in lut.items()})
