"""(2026-11-11) Auditoria do universo da Bybit UE: separa o universo de DESCOBERTA (fontes externas) do universo de
EXECUCAO (o que a conta Bybit UE pode negociar). So copias publicas; nao chama corretoras; nunca dinheiro da conta.

O que o codigo faz (verificado a 11/11 no main 428c5a0):
  - descoberta: engine/sources.ALL = Binance (data-api.binance.vision), OKX (www.okx.com) e KuCoin, pares USDT a vista.
    scan.json counts.pairs_seen = numero de MOEDAS BASE na uniao destas tres fontes (nao sao pares da Bybit).
    engine/sources.Bybit (api.bybit.com, internacional) existe mas NAO esta em sources.ALL: nao e usada.
  - execucao: o servidor europeu le a API da Bybit UE (https://api.bybit.eu, engine/account.py): /v5/market/tickers
    (spot, so pares USDC) -> state.bybit_tickers; /v5/market/instruments-info (spot, quoteCoin USDC, marginTrading
    both/utaOnly, status Trading) -> state.margem_bybit. A CoinGecko (exchanges/bybit-eu) e recurso, nao a fonte.
  - minimo de ordem: so o executor o le na hora (/v5/market/instruments-info, lotSizeFilter.minOrderAmt); nao e
    publicado. Aqui fica "lido na hora pelo executor" e usa-se o valor de configuracao como referencia.
  - nao ha WebSocket da Bybit (o unico WebSocket do codigo e o de liquidacoes da Binance em tools/eu/liquidacoes.py).
Uso: python3 -m tools.universo_bybit_ue <pasta_publica> <saida.json> [<saida.md>]"""
import json
import os
import statistics
import sys

MIN_VOL_EXTERNO = 1_000_000          # engine/scanner.MIN_VOLUME_USD (soma das fontes externas)
MAX_SPREAD_EXTERNO_BPS = 20          # engine/scanner.MAX_SPREAD_BPS


def _j(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def mediana_liquidez(L, dias=20):
    """{base: (volume mediano, spread mediano %)} dos ultimos 'dias' dias do historico diario da Bybit UE."""
    ds = sorted((L or {}).get("dias") or {})[-dias:]
    acc = {}
    for d in ds:
        for b, v in (L["dias"][d] or {}).items():
            if v and v[0] is not None:
                acc.setdefault(b, ([], []))
                acc[b][0].append(v[0])
                if v[1] is not None:
                    acc[b][1].append(v[1])
    return {b: (statistics.median(a), statistics.median(s) if s else None, len(a)) for b, (a, s) in acc.items()}


def tabela(St, S, L, cfg_min_vol=25_000, cfg_max_spread=0.3, min_ordem=5.0):
    tk = ((St or {}).get("bybit_tickers") or {}).get("m") or {}
    mg = set(((St or {}).get("margem_bybit") or {}).get("moedas") or [])
    uni = {r["asset"]: r for r in (S or {}).get("universe") or []}
    med = mediana_liquidez(L)
    linhas = []
    for b in sorted(tk, key=lambda x: -(tk[x][3] or 0)):
        last, bid, ask, vol = tk[b]
        sp = (ask - bid) / ((ask + bid) / 2) * 100 if bid and ask and ask >= bid else None
        mv = med.get(b)
        r = uni.get(b)
        motivos = []
        if b in ("EURC", "USDT", "USDE", "PYUSD"):
            motivos.append("estavel ou indexada: nao e ativo de negociacao")
        if r is None:
            motivos.append("fora da analise: nao passa o filtro de DESCOBERTA externo (volume >= 1 M USD e spread <= 20 bps "
                           "nas fontes Binance/OKX/KuCoin, ou nao existe nelas)")
        vol_ref = mv[0] if mv else vol
        if (vol_ref or 0) < cfg_min_vol:
            motivos.append(f"volume da Bybit UE abaixo do piso ({cfg_min_vol:.0f} USD/24h, mediana de 20 dias)")
        sp_ref = mv[1] if mv and mv[1] is not None else sp
        if sp_ref is None or sp_ref > cfg_max_spread:
            motivos.append(f"spread da Bybit UE acima de {cfg_max_spread}%")
        dec = ((r or {}).get("decision") or {}).get("reason")
        linhas.append({
            "instrumento": f"{b}/USDC", "fonte_dados_execucao": "api.bybit.eu (servidor europeu)",
            "fonte_velas_sinal": "Binance/OKX/KuCoin USDT (externa)" if r else None,
            "mercado": "Spot + Spot Margin" if b in mg else "Spot",
            "disponivel_bybit_ue": True, "negociavel_conta": "spot: sim (lista de tickers ativa)",
            "short_possivel": b in mg, "volume_24h_usd": round(vol or 0), "volume_mediano_20d_usd": round(mv[0]) if mv else None,
            "spread_pct": None if sp is None else round(sp, 4), "spread_mediano_20d_pct": None if not mv or mv[1] is None else round(mv[1], 4),
            "minimo_ordem": f"lido na hora pelo executor (referencia de configuracao {min_ordem:g} USDC)",
            "analisado_pelo_scan": r is not None, "decisao_scan": dec,
            "incluido_execucao": not motivos, "motivos": motivos or ["inclui: liquidez e spread da Bybit UE dentro dos limites"]})
    fora_bybit = sorted(a for a in uni if a not in tk)
    resumo = {
        "descoberta_moedas_externas": (S.get("counts") or {}).get("pairs_seen"),
        "descoberta_fontes": {k: v.get("pairs") for k, v in (S.get("sources") or {}).items()},
        "bybit_ue_pares_usdc": len(tk), "bybit_ue_com_margem_short": len(mg),
        "analisados_pelo_scan": sum(1 for x in linhas if x["analisado_pelo_scan"]),
        "incluidos_execucao": sum(1 for x in linhas if x["incluido_execucao"]),
        "short_e_liquidez_ok": sum(1 for x in linhas if x["incluido_execucao"] and x["short_possivel"]),
        "volume_ge_1M": sum(1 for x in linhas if (x["volume_mediano_20d_usd"] or x["volume_24h_usd"]) >= 1e6),
        "volume_ge_250k": sum(1 for x in linhas if (x["volume_mediano_20d_usd"] or x["volume_24h_usd"]) >= 2.5e5),
        "no_universo_mas_fora_da_bybit_ue": fora_bybit,
        "margem_sem_par_nos_tickers": sorted(mg - set(tk)),
        "idade_tickers_s": None}
    return linhas, resumo


def markdown(linhas, resumo):
    out = ["| Instrumento | Mercado | Short | Volume 20d (USD) | Spread 20d % | Analisado | Execucao | Motivo |",
           "|---|---|---|---|---|---|---|---|"]
    for x in linhas:
        out.append(f"| {x['instrumento']} | {x['mercado']} | {'sim' if x['short_possivel'] else 'nao'} | "
                   f"{x['volume_mediano_20d_usd'] if x['volume_mediano_20d_usd'] is not None else x['volume_24h_usd']} | "
                   f"{x['spread_mediano_20d_pct'] if x['spread_mediano_20d_pct'] is not None else x['spread_pct']} | "
                   f"{'sim' if x['analisado_pelo_scan'] else 'nao'} | {'inclui' if x['incluido_execucao'] else 'exclui'} | "
                   f"{'; '.join(x['motivos'])} |")
    return "\n".join(out)


def correr(pasta):
    St, S, L = _j(os.path.join(pasta, "state.json")), _j(os.path.join(pasta, "scan.json")), _j(os.path.join(pasta, "liquidez.json"))
    cfg = S.get("config") or {}
    from engine import config as C
    base = C.DEFAULTS if hasattr(C, "DEFAULTS") else {}
    linhas, resumo = tabela(St, S, L, cfg.get("min_venue_volume_usd") or base.get("min_venue_volume_usd") or 25_000,
                            cfg.get("max_venue_spread_pct") or 0.3, cfg.get("min_order_usdc") or base.get("min_order_usdc") or 5.0)
    t = ((St.get("bybit_tickers") or {}).get("t"))
    resumo["idade_tickers_s"] = None if not t or not S.get("generated_at") else int(S["generated_at"] - t)
    return {"resumo": resumo, "instrumentos": linhas}


if __name__ == "__main__":
    r = correr(sys.argv[1])
    json.dump(r, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w", encoding="utf-8").write(markdown(r["instrumentos"], r["resumo"]) + "\n")
    print(json.dumps(r["resumo"], ensure_ascii=False, indent=1))
