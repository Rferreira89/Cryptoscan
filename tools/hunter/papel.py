"""Paper trading continuo do Hunter (SO PAPEL: sem chaves, sem executores, sem ordens; nunca ocupa vagas reais e
nunca se mistura com os resultados reais - ficheiro proprio no ramo autonomo).

Cada volta (depois de cada fecho de 30 min):
  1. universo completo dos X-Perps (dados publicos) e velas recentes de 30 min (reamostradas a 1H/4H);
  2. para cada estrategia de hunter/papel_estrategias.json cujo timeframe acabou de fechar: sinais na ultima vela;
  3. funil: descobertos -> dados validos -> candidatos -> rejeitados (motivo) -> aprovados -> abertas -> fechadas ->
     resultado liquido; falhas tecnicas (API) contam como oportunidades perdidas;
  4. cada operacao em papel e re-simulada com a MESMA funcao do backtest (tools/hunter/geometria.simular) sobre as
     velas que entretanto fecharam: entrada na abertura da vela seguinte, stop/alvos/saidas da estrategia, custos e
     funding real da OKX; fecha quando a saida acontece;
  5. aprendizagem/degradacao: por estrategia, R acumulado e motor de sobrevivencia (tools/autonomo.sobrevivencia):
     com limites ultrapassados deixa de abrir operacoes novas dessa estrategia; as abertas continuam geridas.

Uso: python -m tools.hunter.papel <pasta_autonomo>
"""
import json
import os
import sys
import time

import numpy as np

from tools import autonomo as AU
from tools.hunter import dados as DD, familias as FA, geometria as GE, motor as MO

VELAS = 300               # velas por timeframe (um pedido por moeda e por timeframe: 30m, 1H e 4H da propria OKX)
RISCO_PAPEL_PCT = 0.5     # dimensionamento simulado (Kelly = 0 sem vantagem demonstrada: usa-se um minimo fixo)


def _carregar(p, padrao):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return padrao


def velas_tf(inst, tf, now, request=DD.get):
    d = request("/api/v5/market/history-candles", {"instId": inst, "bar": tf, "limit": VELAS})
    if d is None:
        return None
    out = [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
            "v": float(x[5])} for x in d if len(x) > 8 and str(x[8]) == "1"]
    return sorted((b for b in out if b["t"] + DD.BAR[tf] <= now), key=lambda b: b["t"])


def recentes(uni, now, tfs, workers=6):
    """{tf: {base: velas}} recentes de todos os X-Perps e a lista de (base, tf) que falharam (falha tecnica)."""
    from concurrent.futures import ThreadPoolExecutor
    pares = [(b, tf) for b in sorted(uni) for tf in tfs]

    def um(x):
        b, tf = x
        return b, tf, velas_tf(uni[b]["inst"], tf, now)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(um, pares))
    out = {tf: {} for tf in tfs}
    falhas = []
    for b, tf, v in got:
        if v is None:
            falhas.append(f"{b} {tf}")
        elif v:
            out[tf][b] = v
    return out, falhas


def _series(velas_por_tf):
    import numpy as np
    SS = {tf: {} for tf in DD.BAR}
    for tf, porb in velas_por_tf.items():
        for b, v in porb.items():
            S = {k: np.array([x[k] for x in v], dtype=float) for k in "ohlcv"}
            S["t"] = np.array([x["t"] for x in v], dtype=np.int64)
            S["atr"] = np.array([np.nan if a is None else a for a in GE.atr_serie(v)], dtype=float)
            S["v_list"] = v
            SS[tf][b] = S
    return SS


def volta(pasta, now=None, uni=None, velas=None, funding_fn=None, falhas=None):
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "hunter", n)
    os.makedirs(os.path.join(pasta, "hunter"), exist_ok=True)
    est = _carregar(p("papel_estrategias.json"), {"estrategias": []})["estrategias"]
    st = _carregar(p("papel_estado.json"), {"abertas": [], "fechadas": [], "funil_total": {}, "voltas": 0,
                                             "bloqueadas": {}})
    if uni is None:
        uni = DD.universo()
    tfs_agora = sorted({e["tf"] for e in est if not (now // 1800 * 1800) % DD.BAR[e["tf"]]} |
                       {o["tf"] for o in st["abertas"]} | {o["stop_ref"] for o in st["abertas"]} |
                       {e["stop_ref"] for e in est})
    if velas is None:
        velas, falhas = recentes(uni, now, tfs_agora)
    falhas = falhas or []
    funding_fn = funding_fn or (lambda inst: DD.funding(inst) or [])
    validos, rej_dados = {}, {}
    for tf, porb in velas.items():
        validos[tf] = {}
        for b, v in porb.items():
            ok, mot = DD.validar(v, DD.BAR[tf], now)
            if ok:
                validos[tf][b] = v
            else:
                rej_dados[f"{b} {tf}"] = mot
    SS = _series(validos)
    dados_ctx = {b: {"info": uni.get(b, {}), "funding": []} for tf in validos for b in validos[tf]}
    if any(e["familia"] == "funding_extremo" for e in est):
        for b in dados_ctx:
            dados_ctx[b]["funding"] = funding_fn(uni[b]["inst"]) if b in uni else []
    MM = {tf: MO.contexto(SS, dados_ctx, tf) for tf in DD.BAR}
    funil = {"instrumentos_descobertos": len(uni), "com_dados_validos": len({b for tf in validos for b in validos[tf]}),
             "falhas_tecnicas": len(falhas), "excluidos_por_dados": len(rej_dados),
             "candidatos": 0, "rejeitados": {}, "aprovados": 0, "abertas_novas": 0, "fechadas_agora": 0}

    def rejeita(m):
        funil["rejeitados"][m] = funil["rejeitados"].get(m, 0) + 1

    abertas_chave = {(o["estrategia"], o["b"]) for o in st["abertas"]}
    for e in est:
        tf = e["tf"]
        s = DD.BAR[tf]
        if (now // 1800 * 1800) % s or tf not in SS:            # o tf desta estrategia nao fechou nesta volta
            continue
        if st["bloqueadas"].get(e["id"]):
            rejeita("estrategia bloqueada pelo motor de sobrevivencia")
            continue
        with np.errstate(all="ignore"):
            for b, S in SS[tf].items():
                L, Sh = FA.FAMILIAS[e["familia"]][0](S, MM[tf][b], e["parametros"])
                ii = L if e["lado"] == "LONG" else Sh
                i = len(S["c"]) - 1
                if not len(ii) or ii[-1] != i:
                    continue
                funil["candidatos"] += 1
                if S["t"][i] + s > now:
                    rejeita("vela ainda aberta")
                    continue
                if (e["id"], b) in abertas_chave:
                    rejeita("ja ha posicao desta estrategia nesta moeda")
                    continue
                f = MO.FILTROS.get(e.get("filtro"))
                if f and not f(MM, tf, b, i, dados_ctx):
                    rejeita(f"filtro {e.get('filtro')}")
                    continue
                a = MO.atr_ref(SS, b, tf, i, e["stop_ref"])
                if not a:
                    rejeita("ATR de referencia indisponivel")
                    continue
                stop_pct = float(100 * e["saida"]["k"] * a / S["c"][i])
                dim = AU.dimensionar(RISCO_PAPEL_PCT, stop_pct, 5, 2 * (GE.COMISSAO + GE.DESLIZE), {"risco_max_pct": 5.0})
                funil["aprovados"] += 1
                st["abertas"].append({"id_op": f"{e['id']}|{b}|{int(S['t'][i])}", "estrategia": e["id"], "familia": e["familia"],
                                      "veredicto_origem": e.get("veredicto"), "b": b, "exchange": "OKX X-Perp (papel)",
                                      "inst": (uni.get(b) or {}).get("inst"), "lado": e["lado"], "tf": tf,
                                      "t_sinal": int(S["t"][i]), "atr_ref": a, "saida": e["saida"],
                                      "stop_ref": e["stop_ref"], "tamanho": dim, "aberta_em": now})
                abertas_chave.add((e["id"], b))
                funil["abertas_novas"] += 1
    # acompanhar e fechar
    ficam = []
    for o in st["abertas"]:
        v = (velas.get(o["tf"]) or {}).get(o["b"]) or []
        i = next((k for k, x in enumerate(v) if x["t"] == o["t_sinal"]), None)
        if i is None:
            if now - o["t_sinal"] > 3 * 86400:
                o.update(fechada_em=now, motivo="dados indisponiveis (fecho administrativo, sem resultado)", r=None)
                st["fechadas"].append(o)
            else:
                ficam.append(o)
            continue
        if i + 1 >= len(v):
            ficam.append(o)                          # ainda nao abriu (espera a vela seguinte)
            continue
        fund = funding_fn(o["inst"]) if o.get("inst") else []
        r = GE.simular(v, i, o["lado"], o["atr_ref"], o["saida"], fund, None)
        if r is None:
            ficam.append(o)
            continue
        ultimo = len(v) - 1
        terminou = r["saida"] != "tempo" or i + o["saida"]["hold"] <= ultimo
        o["entrada"] = v[i + 1]["o"]
        if terminou:
            o.update(fechada_em=now, r=round(r["r"], 4), bruto_r=round(r["bruto_r"], 4), custos_r=round(r["custos_r"], 4),
                     funding_pct=r["funding_pct"], funding_fonte=r["funding_fonte"], motivo=r["saida"],
                     velas=r["velas"], permanencia_min=r["velas"] * DD.BAR[o["tf"]] // 60,
                     resultado_liquido_pct_capital=round(r["r"] * (o.get("tamanho") or {}).get("risco_pct", 0), 4))
            st["fechadas"].append(o)
            funil["fechadas_agora"] += 1
        else:
            o["r_atual"] = round(r["r"], 4)
            ficam.append(o)
    st["abertas"] = ficam
    # aprendizagem: sobrevivencia por estrategia
    por = {}
    for o in st["fechadas"]:
        if o.get("r") is not None:
            por.setdefault(o["estrategia"], []).append(o["r"])
    resumo = {}
    for k, rs in por.items():
        sv = AU.sobrevivencia(rs)
        resumo[k] = {"n": len(rs), "r_medio": round(sum(rs) / len(rs), 4), "r_total": round(sum(rs), 3),
                     "acerto": round(sum(1 for x in rs if x > 0) / len(rs), 3), "drawdown_r": sv["drawdown_r"],
                     "novas_entradas": sv["novas_entradas"], "motivos": sv["motivos"]}
        if not sv["novas_entradas"]:
            st["bloqueadas"][k] = sv["motivos"]
    st["resumo"] = resumo
    st["funil_ultima"] = {**funil, "t": now}
    tot = st["funil_total"]
    for k, v in funil.items():
        if isinstance(v, int):
            tot[k] = tot.get(k, 0) + v if k not in ("instrumentos_descobertos", "com_dados_validos") else v
    for m, n in funil["rejeitados"].items():
        tot.setdefault("rejeitados", {})[m] = tot.get("rejeitados", {}).get(m, 0) + n
    st["voltas"] += 1
    st["t"] = now
    st["aviso"] = "PAPEL: simulado, nunca somado aos resultados reais; sem ordens"
    st["fechadas"] = st["fechadas"][-5000:]
    with open(p("papel_estado.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=0)
    return st


if __name__ == "__main__":
    s = volta(sys.argv[1])
    print(json.dumps(s["funil_ultima"], ensure_ascii=False), "abertas", len(s["abertas"]), "fechadas", len(s["fechadas"]))
