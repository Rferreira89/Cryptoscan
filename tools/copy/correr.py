"""(17/11) Volta do CopyTrading: ranking (de hora a hora), posicoes dos traders seguidos (cada volta), deteccao de
entradas/reducoes/fechos, decisao SMART_COPY por corretora, sinais para o piloto OKX e registo de decisoes.
Ficheiros (ramo autonomo, pasta copy/): traders.json (ranking), estado.json (posicoes vistas, oportunidades),
sinais.json (para tools/piloto_okx.py: abertas/fechadas/estrategias), decisoes.jsonl (todas as decisoes).
Nada aqui envia ordens: a execucao real e do piloto OKX (limites partilhados com as outras estrategias)."""
import json
import os
import sys
import time

from tools.copy import fontes as F
from tools.copy import ranking as RK
from tools.copy import smart as SM

RANKING_S = 3600
RANKING_VERSAO = 3            # mudar quando os criterios mudam: obriga a refazer o ranking na volta seguinte
SEGUIR_OKX, SEGUIR_HL = 30, 40
CUSTO_SOMBRA = 0.001          # ida e volta, para o resultado-sombra das decisoes


def _ler(p, padrao):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, default=str)


def atualizar_ranking(trs, now, log=print):
    out = {}
    def um(chave, t, hist, pos):                       # um trader com dados maus nunca para a volta
        try:
            h = hist(t["id"])
            if h is not None:
                out[chave] = {**RK.avaliar(t, h, pos(t["id"])), **{k: t[k] for k in ("dias", "copiadores") if k in t}}
        except Exception as e:
            F.FALHAS.add(f"avaliar {chave}", f"{type(e).__name__}: {e}")

    for t in F.okx_lideres(10):      # a OKX expoe no maximo ~197 lideres publicos (10 paginas), igual em todas as ordenacoes
        um(f"okx:{t['id']}", t, F.okx_historico, F.okx_posicoes)   # posicoes: perdas por fechar (o historico so tem as fechadas)
        time.sleep(0.6)
    for t in F.hl_ranking(300) or []:
        um(f"hyperliquid:{t['id']}", t, F.hl_historico, F.hl_posicoes)
        time.sleep(0.3)
    if not out:
        return trs                                            # fontes em baixo: mantem o ranking anterior
    log(f"ranking: {len(out)} traders, {sum(1 for v in out.values() if v['estado'] == 'APROVADO')} aprovados")
    return {"t": now, "versao": RANKING_VERSAO, "traders": out}


def seguidos(trs):
    """(17/11) Aprovados primeiro; depois os em observacao que operam com frequencia e em pouco tempo (os que podem dar
    sinais copiaveis), nao os de maior pontuacao que seguram posicoes semanas."""
    def prio(kv):
        v = kv[1]
        m = v.get("metricas") or {}
        dur = m.get("duracao_media_h") or 999
        return (0 if v["estado"] == "APROVADO" else 1, 0 if dur <= 12 else 1, -(m.get("freq_dia") or 0), -v.get("score", 0))
    ok = sorted([kv for kv in trs.get("traders", {}).items() if kv[1]["estado"] in ("APROVADO", "OBSERVAR")], key=prio)
    return [k for k, _ in [x for x in ok if x[0].startswith("okx:")][:SEGUIR_OKX] +
            [x for x in ok if x[0].startswith("hyperliquid:")][:SEGUIR_HL]]


def ranking(pasta, now=None, log=print):
    """Trabalho proprio (paralelo ao observador): refaz o ranking quando passou 1 h ou os criterios mudaram."""
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "copy", n)
    os.makedirs(os.path.join(pasta, "copy"), exist_ok=True)
    trs = _ler(p("traders.json"), {"t": 0, "traders": {}})
    if now - int(trs.get("t") or 0) >= RANKING_S or trs.get("versao") != RANKING_VERSAO:
        trs = atualizar_ranking(trs, now, log)
        _gravar(p("traders.json"), trs)
        return True
    return False


def volta(pasta, now=None, fontes=F, log=print):
    """Observador: posicoes dos traders seguidos -> entradas/reducoes/fechos -> decisoes. Nunca espera pelo ranking."""
    now = int(now or time.time())
    p = lambda n: os.path.join(pasta, "copy", n)
    os.makedirs(os.path.join(pasta, "copy"), exist_ok=True)
    trs = _ler(p("traders.json"), {"t": 0, "traders": {}})
    st = _ler(p("estado.json"), {"posicoes": {}, "oportunidades": {}, "vistos": []})
    intervalo = now - int(st.get("t") or now)
    sin = _ler(p("sinais.json"), {"abertas": [], "fechadas": []})
    xp = fontes.xperps_eea()
    info_b = {}
    spot_b = fontes.bybit_eu_spot(info_b) if hasattr(fontes, "bybit_eu_spot") else None
    cache_v, cache_p = {}, {}

    def mercado(base):
        inst = xp.get(base)
        if not inst:
            return None, None
        if base not in cache_v:
            cache_v[base], cache_p[base] = fontes.velas_1h(inst), fontes.preco(inst)
        return cache_p[base], cache_v[base]

    atuais, falhou = {}, []
    for k in seguidos(trs):
        fonte, tid = k.split(":", 1)
        try:
            pos = fontes.okx_posicoes(tid) if fonte == "okx" else fontes.hl_posicoes(tid)
        except Exception as e:
            F.FALHAS.add(f"posicoes {k}", f"{type(e).__name__}: {e}")
            pos = None
        time.sleep(0.3)
        if pos is None:
            falhou.append(k)
            continue
        atuais[k] = {x["id"]: x for x in pos}
    consenso = {}
    for k, pos in atuais.items():
        if trs["traders"][k]["estado"] == "APROVADO":
            for x in pos.values():
                consenso[(x["base"], x["lado"])] = consenso.get((x["base"], x["lado"]), 0) + 1
    decisoes, fechadas_novas = [], []
    for k, pos in atuais.items():                             # 1.o fechos e reducoes (uma inversao fecha antes de abrir)
        for pid, a in (st["posicoes"].get(k) or {}).items():
            if pid not in pos:
                fechadas_novas.append((f"copy|{k}|{pid}", "trader fechou"))
            elif float(a.get("tamanho") or 0) and float(pos[pid].get("tamanho") or 0) <= float(a["tamanho"]) * (1 - SM.C["reducao_fecho"]):
                fechadas_novas.append((f"copy|{k}|{pid}", "trader reduziu >= 50%"))
    fechar_ids = {i for i, _ in fechadas_novas}
    abertas_bases = {o["b"] for o in sin["abertas"] if o["id_op"] not in fechar_ids}
    for k, pos in atuais.items():
        antes = st["posicoes"].get(k)
        tr = trs["traders"][k]
        for pid, x in pos.items():
            if antes is None:
                continue                                      # primeira vez que se segue este trader: nada e "novo"
            if pid in antes:
                continue
            x = dict(x)
            if x.get("t_abre") is None:                       # Hyperliquid: so sabemos que abriu desde a ultima volta
                x["t_visto"] = int(st.get("t") or now)
            px, v = mercado(x["base"])
            ctx = {"now": now, "xperps": xp, "preco": px, "velas": v,
                   "consenso": consenso.get((x["base"], x["lado"]), 0) - (1 if tr["estado"] == "APROVADO" else 0),
                   "ja_ha_copia": x["base"] in abertas_bases}
            dec, mot, plano = SM.decidir(x, tr, ctx)
            dec_b, mot_b = SM.decidir_bybit(x, spot_b)
            idop = f"copy|{k}|{pid}"
            if idop in st["oportunidades"]:
                continue                                      # evento ja tratado (reinicio ou repeticao)
            reg = {"t": now, "id": idop, "trader": k, "fonte": k.split(":")[0], "base": x["base"], "lado": x["lado"],
                   "px_trader": x["px_abre"], "px_ref": px, "okx": {"decisao": dec, "motivo": mot}, "bybit_eu": {"decisao": dec_b, "motivo": mot_b}}
            decisoes.append(reg)
            st["oportunidades"][idop] = {**reg, "aberta": True}
            if plano:
                abertas_bases.add(x["base"])
                sin["abertas"].append({
                    "id_op": idop, "origem": "copy", "estrategia": f"copy:{k}", "b": x["base"], "inst": plano["inst"],
                    "lado": x["lado"], "tf": "1H", "t_sinal": now, "t_ref": int(x.get("t_abre") or x["t_visto"]),
                    "atr_ref": plano["atr"], "saida": {"tipo": "fixa", "k": SM.C["k_stop_atr"], "tp": SM.C["tp_r"], "hold": SM.C["hold_h"]},
                    "regime": None, "decisao": {"fecho": x["px_abre"]}, "decisao_copy": dec, "motivo": mot, "aberta_em": now})
    for idop, mot in fechadas_novas:
        o = st["oportunidades"].get(idop)
        if o and o.get("aberta"):
            o["aberta"] = False
            px, _ = mercado(o["base"])
            if px and o.get("px_ref"):
                d = 1 if o["lado"] == "LONG" else -1
                o["resultado_sombra"] = round(d * (px - o["px_ref"]) / o["px_ref"] - CUSTO_SOMBRA, 5)
            o["fecho"] = {"t": now, "motivo": mot}
        if any(a["id_op"] == idop for a in sin["abertas"]):
            sin["abertas"] = [a for a in sin["abertas"] if a["id_op"] != idop]
            sin["fechadas"].append({"id_op": idop, "motivo": mot, "fechada_em": now})
    # sinais de copia velhos (o piloto ja nao os pode usar e o trader continua aberto): saem das abertas ao fim de 4 h
    for a in list(sin["abertas"]):
        if now - a["aberta_em"] > SM.C["hold_h"] * 3600:
            sin["abertas"].remove(a)
            sin["fechadas"].append({"id_op": a["id_op"], "motivo": "duracao maxima", "fechada_em": now})
    for k, pos in atuais.items():
        st["posicoes"][k] = pos
    st["oportunidades"] = dict(sorted(st["oportunidades"].items(), key=lambda kv: kv[1]["t"])[-3000:])
    st["consultas"] = (st.get("consultas") or [])[-500:] + [{"t": now, "intervalo_s": intervalo, "seguidos": len(atuais),
                                                             "falhados": len(falhou), "oportunidades": len(decisoes)}]
    st.update(t=now, falhas=F.FALHAS[-20:], traders_falhados=falhou, seguidos=len(atuais),
              ultima_consulta={k: now for k in atuais}, recuperacao=(intervalo > 600),
              bybit_eu_lista_spot={"bases": len(spot_b) if spot_b else 0, **info_b})
    sin["fechadas"] = sin["fechadas"][-500:]
    aprovados = {k: v for k, v in trs.get("traders", {}).items() if v["estado"] == "APROVADO"}
    sin.update(t=now, aviso="CopyTrading: sinais para o piloto OKX (execucao real so la, com os limites do piloto)",
               estrategias={f"copy:{k}": {
                   "id": f"copy:{k}", "versao": f"copy:{k}", "estado": "EXPERIMENTAL_REAL", "lado": "AMBOS",
                   "tf": "1H", "definicao": {"tf": "1H", "saida": {"tipo": "fixa", "k": SM.C["k_stop_atr"], "tp": SM.C["tp_r"],
                                                                   "hold": SM.C["hold_h"]}},
                   "auditoria_tecnica": {"ok": True, "falhas": [], "sinal": "posicao publica do trader + preco atual da OKX EEA"},
                   "backtest": {"r_medio": round((v.get("validacao") or {}).get("r_medio") or 0, 5)}, "origem": "copy"}
                   for k, v in aprovados.items()})
    _gravar(p("estado.json"), st)
    _gravar(p("sinais.json"), sin)
    with open(p("decisoes.jsonl"), "a", encoding="utf-8") as f:
        for d in decisoes:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    resumo = {"t": now, "traders": len(trs.get("traders", {})), "aprovados": len(aprovados), "seguidos": len(atuais),
              "oportunidades": len(decisoes), "por_decisao": {}, "copias_para_okx": sum(1 for d in decisoes if d["okx"]["decisao"]
                                                                                       in ("COPY_DIRECT", "CONFIRM_AND_COPY")),
              "fechos": len(fechadas_novas), "falhas": len(F.FALHAS)}
    for d in decisoes:
        resumo["por_decisao"][d["okx"]["decisao"]] = resumo["por_decisao"].get(d["okx"]["decisao"], 0) + 1
    return resumo


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "ranking":
        print(json.dumps({"ranking_refeito": ranking(sys.argv[1])}))
        sys.exit(0)
    r = volta(sys.argv[1])
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r.get("copias_para_okx") else 3)            # 3 = sem copias novas (o lancador so chama o piloto com 0)
