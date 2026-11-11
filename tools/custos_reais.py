"""Reconciliacao dos custos reais (auditoria de rentabilidade, 2026-11-11).
So leitura das copias publicas; sem rede, sem chaves, sem ordens.

Junta:
- comissoes oficiais (constantes abaixo, com a fonte e a data);
- spread real da Bybit UE por moeda (liquidez.json do ramo data: mediana
  diaria das amostras do scanner);
- deslize de entrada nas operacoes reais da Bybit (state.json "ledger": preco
  executado contra o preco do plano);
- custos e deslize no stop das operacoes reais da OKX (contabilidade_okx.json);
- o custo em R de cada operacao real (custo de ida e volta / distancia do stop).

Responde: os 0,7% de ida e volta usados na investigacao estao certos para que
mercado, moeda e tipo de ordem?

Uso: python -m tools.custos_reais <pasta_com_copias> [saida.json]
"""
import json
import os
import statistics as st
import sys

# fontes: Bybit UE, "Benefits of the VIP Program", atualizado 2026-07-02 (VIP0, pares cripto, < 10 000 USDC/30 d);
# OKX: tabela publica nivel 1 (fontes secundarias: README okx-fee-analysis e artigo MEXC de 21/10/2026)
COMISSOES = {
    "bybit_ue_spot": {"maker": 0.10, "taker": 0.25},
    "okx_eea_spot_com_derivados": {"maker": 0.08, "taker": 0.10},
    "okx_eea_spot_sem_derivados": {"maker": 0.20, "taker": 0.35},
    "okx_perpetuo": {"maker": 0.02, "taker": 0.05},
}
DESLIZE_INVESTIGACAO = 0.10        # % por lado usado nos backtests


def _ler(pasta, nome):
    p = os.path.join(pasta, nome)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def spreads(liq):
    acc = {}
    for _, m in ((liq or {}).get("dias") or {}).items():
        for a, v in m.items():
            if isinstance(v, list) and len(v) > 1 and v[1] is not None:
                acc.setdefault(a, []).append(float(v[1]))
    return {a: st.median(v) for a, v in acc.items()}


def _q(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else None


def ida_volta(fee_lado, spread, deslize_lado=0.0):
    """% do preco: duas comissoes + spread inteiro + deslize alem do spread nos dois lados."""
    return 2 * fee_lado + spread + 2 * deslize_lado


def bybit_operacoes(state, sp):
    out = []
    for x in (state or {}).get("ledger") or []:
        if x.get("status") != "CLOSED" or not x.get("entry") or not x.get("stop"):
            continue
        lado = x.get("side") or "LONG"
        e = float(x["entry"])
        stop_pct = abs(e - float(x["stop"])) / e * 100
        d = None
        if x.get("exec_price"):
            d = (float(x["exec_price"]) / e - 1) * 100 * (1 if lado == "LONG" else -1)
        s = sp.get(x["asset"])
        custo = ida_volta(COMISSOES["bybit_ue_spot"]["taker"], s if s is not None else 0.144)
        out.append({"estrategia": x.get("strategy"), "asset": x["asset"], "lado": lado,
                    "executada": bool(x.get("executed")), "stop_pct": round(stop_pct, 3),
                    "deslize_entrada_pct": None if d is None else round(d, 4),
                    "custo_ida_volta_pct": round(custo, 3), "custo_r": round(custo / stop_pct, 3),
                    "r": x.get("result_r")})
    return out


def resumo(pasta):
    st_ = _ler(pasta, "state.json")
    liq = _ler(pasta, "liquidez.json")
    okx = _ler(pasta, "contabilidade_okx.json")
    sp = spreads(liq)
    vals = list(sp.values())
    by = bybit_operacoes(st_, sp)
    des = [o["deslize_entrada_pct"] for o in by if o["deslize_entrada_pct"] is not None]
    fee = COMISSOES["bybit_ue_spot"]["taker"]
    cen = {}
    for nome, s in (("BTC/ETH (spread ~0,01%)", 0.01), ("moeda mediana", _q(vals, 0.5)),
                    ("quartil caro (p75)", _q(vals, 0.75)), ("p90", _q(vals, 0.9))):
        if s is None:
            continue
        cen[nome] = {"spread_pct": round(s, 4),
                     "taker_taker": round(ida_volta(fee, s), 3),
                     "maker_entrada_taker_saida": round(COMISSOES["bybit_ue_spot"]["maker"] + fee + s / 2, 3),
                     "taker_com_deslize_0_1": round(ida_volta(fee, s, 0.1), 3)}
    ops_okx = (okx or {}).get("operacoes") or []
    return {
        "comissoes": COMISSOES,
        "investigacao_ida_volta_pct": 2 * (fee + DESLIZE_INVESTIGACAO),
        "bybit_spread": {"moedas": len(sp), "dias": len((liq or {}).get("dias") or {}),
                         "mediana": _q(vals, 0.5), "p25": _q(vals, 0.25), "p75": _q(vals, 0.75),
                         "p90": _q(vals, 0.9),
                         "por_moeda": {a: round(v, 4) for a, v in sorted(sp.items(), key=lambda x: x[1])}},
        "bybit_cenarios_ida_volta_pct": cen,
        "bybit_operacoes_reais": {
            "n": len(by), "executadas": sum(1 for o in by if o["executada"]),
            "deslize_entrada_pct": {"n": len(des), "media": round(st.mean(des), 4) if des else None,
                                    "mediana": round(st.median(des), 4) if des else None,
                                    "pior": round(max(des), 4) if des else None},
            "stop_mediano_pct": round(st.median([o["stop_pct"] for o in by]), 3) if by else None,
            "custo_r_mediano": round(st.median([o["custo_r"] for o in by]), 3) if by else None,
            "custo_r_maximo": round(max(o["custo_r"] for o in by), 3) if by else None,
            "operacoes_custo_acima_0_25r": sum(1 for o in by if o["custo_r"] > 0.25),
            "r_medio": round(st.mean([o["r"] for o in by if o["r"] is not None]), 3) if by else None,
            "operacoes": by},
        "okx_operacoes_reais": {
            "n": len(ops_okx),
            "custo_r_medio": round(st.mean([o["custo_r"] for o in ops_okx]), 4) if ops_okx else None,
            "deslize_stop_r_medio": round(st.mean([o["deslize_stop_r"] for o in ops_okx]), 4) if ops_okx else None,
            "pior_deslize_stop_r": round(min(o["deslize_stop_r"] for o in ops_okx), 4) if ops_okx else None,
            "r_liquido_medio": round(st.mean([o["r_liquido"] for o in ops_okx]), 4) if ops_okx else None},
    }


if __name__ == "__main__":
    r = resumo(sys.argv[1])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in r.items() if k not in ("bybit_spread", "bybit_operacoes_reais")},
                     ensure_ascii=False, indent=1))
    b = r["bybit_operacoes_reais"]
    print(json.dumps({k: v for k, v in b.items() if k != "operacoes"}, ensure_ascii=False, indent=1))
