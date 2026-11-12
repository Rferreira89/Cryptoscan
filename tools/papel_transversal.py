"""(12/11 15:44, ordem do Rui: "se ainda nao cumprir os criterios, coloca-o em paper trading continuo") Papel CONTINUO,
para a frente, das familias transversais LONG e SHORT de tools/long_transversal, com dados ao vivo e as mesmas regras
do estudo (nada reescrito para o papel: as mesmas funcoes sinais/indicadores/sair).

Corre uma vez por dia num servidor do GitHub (isolado: nunca ocupa o servidor europeu da conta e do executor).
Universo: as moedas com par USDC na Bybit UE (lista da conta publica); SHORT so nas que a Bybit UE deixa pedir
emprestado (margem). Para cada dia UTC fechado ainda nao processado: sinais no fecho; entrada na abertura do dia
seguinte (so quando esse dia ja existe: nada e preenchido com precos futuros); saida por stop ou tempo.
R liquido com custos da Bybit UE (0,35%/lado) e juro do emprestimo nos SHORT. Tudo em R: nunca dinheiro.

Estado: papel.json (ramo papel-transversal): abertas, fechadas, ultimo_dia. Resumo por familia com
tools/painel_resultados.metricas. Este papel e a validacao em papel que a porta do LONG real exige.
Uso: python3 -m tools.papel_transversal <estado_publico.json> <papel.json> [--dias 260]"""
import json
import os
import sys
import time

from tools import long_transversal as L

DAY = 86400


def carregar_series(moedas, dias, agora, buscar=None):
    """{moeda: [velas diarias]} a partir de velas de 4h recentes (fetch publico do ringue)."""
    if buscar is None:
        from tools import arena_ringue as AR

        def buscar(b):
            return AR.fetch(b, int(agora), need=dias * 6)
    out, erros = {}, {}
    for b in sorted(set(moedas) | {"BTC"}):
        try:
            c4 = buscar(b)
        except Exception as e:                           # noqa: BLE001
            erros[type(e).__name__ + ": " + str(e)[:80]] = erros.get(type(e).__name__ + ": " + str(e)[:80], 0) + 1
            continue
        dd = L.diario([x for x in c4 if x["t"] + 4 * 3600 <= agora])
        if len(dd) >= 61:
            out[b] = dd
    if erros:
        print("papel_transversal: falhas a buscar velas:", erros)
    return out


def _fase(btc_ind, dia):
    b = btc_ind.get(dia) or {}
    if not b.get("ma200"):
        return None
    if b["c"] > b["ma200"] and b["c"] > b["ma50"]:
        return "subida"
    if b["c"] < b["ma200"] and b["c"] < b["ma50"]:
        return "queda"
    return "lateral"


def passo(estado, series, margem, agora):
    """Processa os dias fechados em falta. Devolve o estado atualizado (abertas/fechadas/ultimo_dia)."""
    est = dict(estado or {})
    est.setdefault("abertas", [])
    est.setdefault("fechadas", [])
    ind = {a: L.indicadores(dd) for a, dd in series.items() if a not in L.ESTAVEIS}
    btc = ind.pop("BTC", {})
    hoje = int(agora // DAY)
    ultimo = est.get("ultimo_dia") or (hoje - 2)
    # 1) gerir as abertas (entrada ja conhecida) com as velas que existem
    ainda = []
    for o in est["abertas"]:
        dd = series.get(o["a"])
        if not dd:
            ainda.append(o)
            continue
        idx = {x["t"] // DAY: i for i, x in enumerate(dd)}
        i_ent = idx.get(o["t"] // DAY)
        if o.get("ent") is None:
            if i_ent is None:
                ainda.append(o)
                continue
            o["ent"] = dd[i_ent]["o"]
            atr = o.pop("atr")
            o["stop"] = o["ent"] + o["m_atr"] * atr if o["lado"] == "SHORT" else o["ent"] - o["m_atr"] * atr
        h = o["h"]
        if i_ent is None or i_ent + h > len(dd):
            # ainda nao ha velas suficientes para a saida por tempo: ve so se o stop ja foi tocado
            sub = dd[i_ent:] if i_ent is not None else []
            tocou = any((x["h"] >= o["stop"]) if o["lado"] == "SHORT" else (x["l"] <= o["stop"]) for x in sub)
            if not tocou:
                ainda.append(o)
                continue
        fn = L.sair_short if o["lado"] == "SHORT" else L.sair
        px, t_fim = fn(dd, i_ent, o["stop"], h)
        frac = abs(o["stop"] - o["ent"]) / o["ent"]
        if o["lado"] == "SHORT":
            dias = max(0.0, (t_fim - o["t"]) / DAY)
            r = (1 - px / o["ent"] - L.CUSTO_BYBIT - L.JURO_DIA * dias) / frac
        else:
            r = (px / o["ent"] - 1 - L.CUSTO_BYBIT) / frac
        est["fechadas"].append(dict(o, saida=px, t_fim=int(t_fim), r=round(r, 4)))
    est["abertas"] = ainda
    # 2) sinais dos dias fechados em falta (o dia de hoje ainda nao fechou)
    abertas_k = {(o["k"], o["a"]) for o in est["abertas"]}
    for dia in range(ultimo + 1, hoje):
        if dia not in btc:
            continue
        fase = _fase(btc, dia)
        for k, moedas in L.sinais(dia, ind, btc).items():
            h, m_atr = L.REGRAS[k]
            lado = "SHORT" if k in L.SHORTS else "LONG"
            for a in moedas:
                if a == "BTC" or (k, a) in abertas_k or (lado == "SHORT" and a not in margem):
                    continue
                x = ind[a][dia]
                est["abertas"].append({"k": k, "a": a, "lado": lado, "fase": fase, "sinal_dia": dia,
                                       "t": (dia + 1) * DAY, "ent": None, "atr": x["atr"], "m_atr": m_atr, "h": h})
                abertas_k.add((k, a))
        est["ultimo_dia"] = dia
    est["t"] = int(agora)
    est["resumo"] = resumo(est)
    return est


def resumo(est):
    from tools.painel_resultados import metricas
    por = {}
    for o in sorted(est.get("fechadas") or [], key=lambda o: o["t_fim"]):
        por.setdefault(o["k"], []).append(o["r"])
    out = {k: dict(metricas(v), lado="SHORT" if k in L.SHORTS else "LONG") for k, v in sorted(por.items())}
    for k in L.REGRAS:
        out.setdefault(k, {"n": 0, "lado": "SHORT" if k in L.SHORTS else "LONG"})
        out[k]["abertas"] = sum(1 for o in est.get("abertas") or [] if o["k"] == k)
    return out


def correr(estado_pub, saida, dias=260, agora=None, buscar=None):
    agora = int(agora or time.time())
    St = json.load(open(estado_pub)) if estado_pub and os.path.exists(estado_pub) else {}
    moedas = sorted(((St.get("bybit_tickers") or {}).get("m") or {}).keys())
    margem = set((St.get("margem_bybit") or {}).get("moedas") or [])
    est = json.load(open(saida)) if os.path.exists(saida) else {}
    series = carregar_series(moedas, dias, agora, buscar)
    est = passo(est, series, margem, agora)
    est["universo"] = {"moedas": len(series), "margem": len(margem & set(series))}
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=1)
    return est


if __name__ == "__main__":
    a = sys.argv
    d = int(a[a.index("--dias") + 1]) if "--dias" in a else 260
    r = correr(a[1], a[2], d)
    print(json.dumps({"ultimo_dia": r.get("ultimo_dia"), "universo": r.get("universo"), "abertas": len(r["abertas"]),
                      "fechadas": len(r["fechadas"]), "resumo": r["resumo"]}, ensure_ascii=False))
