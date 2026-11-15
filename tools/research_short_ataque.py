"""Investigacao SHORT_SOBRECOMPRA (4H) e ATAQUE_1H long/short (1H).
Pre-registo: backtest/pre_registo_short_ataque_1h.md (2026-11-15, antes de testar).

SHORT_SOBRECOMPRA: X in {70,75} x V in {2.0, 2.5}, so vendas 4H.
ATAQUE_1H: k in {1.5, 2} x H in {12, 24}h, long e short separados.
Metodo: tools/research_rlib.evaluate quando disponivel; senao reporta grelha e sai.

Uso: python -m tools.research_short_ataque <historico> [saida.json]
"""
import json
import sys

PCTIL_MIN = 90
SS_GRID = [{"X": x, "V": v} for x in (70, 75) for v in (2.0, 2.5)]
AT_GRID = [{"k": k, "H": h} for k in (1.5, 2.0) for h in (12, 24)]


def main(folder, out="backtest/research_short_ataque.json"):
    res = {
        "pre_registo": "backtest/pre_registo_short_ataque_1h.md",
        "pctil_min": PCTIL_MIN,
        "SHORT_SOBRECOMPRA_grelha": SS_GRID,
        "ATAQUE_1H_long_grelha": AT_GRID,
        "ATAQUE_1H_short_grelha": AT_GRID,
        "estado": "grelha pronta; correr evaluate quando historico 4H+1H estiver disponivel",
        "historico": folder,
        "criterio": "seis de sempre + acaso >= p90; veredicto max PARA PAPEL; conta so apos >=25 op. papel",
        "venues": ["Bybit", "OKX"],
    }
    try:
        from engine import backtest as B
        data, _ = B.load_all(folder)
        res["moedas"] = len(data)
        res["ultima_vela_btc"] = data.get("BTC", [{}])[-1].get("t") if data.get("BTC") else None
    except Exception as e:
        res["load_erro"] = f"{type(e).__name__}: {e}"
    try:
        from tools import research_rlib as R  # noqa: F401
        res["research_rlib"] = "disponivel"
    except Exception as e:
        res["research_rlib"] = f"indisponivel: {type(e).__name__}"
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in res if k != "detalhe"}, indent=1))
    return res


if __name__ == "__main__":
    main(*sys.argv[1:3])
