"""(18/11, ordem do Rui: categoria D) Oportunidades potenciais que o sistema NAO detetou.

Em cada volta horaria do papel, para todos os X-Perps com velas de 1 h validas:
  1. movimentos relevantes nas ultimas 24 h: a partir do fecho de uma vela, o preco andou >= max(3%, 3 x ATR14%) a
     favor de um lado em <= 4 h (o maior por moeda e lado; janelas que se sobrepoem contam uma vez);
  2. detetado = algum sinal do papel (qualquer estrategia, qualquer carteira) nessa moeda e nesse lado entre 4 h antes
     e o inicio do movimento; senao e categoria D;
  3. so para os D: havia na vela de inicio (so com dados ate ao fecho dela, sem olhar para a frente) uma condicao
     observavel em tempo real? volume >= 2x a media de 20, rompimento do maximo/minimo de 24 velas, forca/fraqueza
     relativa ao BTC nas 4 h anteriores, extensao >= 2 ATR da media de 20 (reversao). Sem nenhuma: o movimento so se ve
     depois -> nao conta como falha de cobertura.
O "resultado hipotetico" e a excursao maxima menos custos: e um TETO (escolhido depois de ver o movimento), nunca uma
oportunidade realizavel nem resultado real. Serve para orientar a investigacao (familias/timeframes em falta), nao
para decidir entradas. Escreve hunter/cobertura.json."""
import json
import os
import statistics
import time

H = 3600
MOV_MIN, MOV_ATR, JANELA_H, CUSTO = 0.03, 3.0, 4, 0.0012


def _atr_pct(v, i, n=14):
    if i < n:
        return None
    tr = [max(v[k]["h"] - v[k]["l"], abs(v[k]["h"] - v[k - 1]["c"]), abs(v[k]["l"] - v[k - 1]["c"])) for k in range(i - n + 1, i + 1)]
    return statistics.mean(tr) / v[i]["c"]


def condicoes(v, i, btc=None):
    """Condicoes observaveis no fecho da vela i (so v[..i])."""
    out = []
    if i < 24:
        return out
    vol = [b.get("v") or 0 for b in v[i - 20:i]]
    if vol and statistics.mean(vol) > 0 and (v[i].get("v") or 0) >= 2 * statistics.mean(vol):
        out.append("volume")
    hi, lo = max(b["h"] for b in v[i - 24:i]), min(b["l"] for b in v[i - 24:i])
    if v[i]["c"] > hi:
        out.append("rompimento_alta")
    if v[i]["c"] < lo:
        out.append("rompimento_baixa")
    a = _atr_pct(v, i)
    ma = statistics.mean(b["c"] for b in v[i - 20:i + 1])
    if a and abs(v[i]["c"] / ma - 1) >= 2 * a:
        out.append("extensao_alta" if v[i]["c"] > ma else "extensao_baixa")
    if btc and i >= 4:
        bt = {b["t"]: b["c"] for b in btc}
        t0, t1 = v[i - 4]["t"], v[i]["t"]
        if t0 in bt and t1 in bt:
            r, rb = v[i]["c"] / v[i - 4]["c"] - 1, bt[t1] / bt[t0] - 1
            if r - rb >= 0.02:
                out.append("forca_relativa")
            if rb - r >= 0.02:
                out.append("fraqueza_relativa")
    return out


def movimentos(v, now, horas=24):
    out = []
    for i in range(len(v) - 1):
        if v[i]["t"] + H < now - horas * H:
            continue
        a = _atr_pct(v, i)
        if not a:
            continue
        lim = max(MOV_MIN, MOV_ATR * a)
        fim = v[i + 1:i + 1 + JANELA_H]
        if not fim:
            continue
        up = max(b["h"] for b in fim) / v[i]["c"] - 1
        dn = 1 - min(b["l"] for b in fim) / v[i]["c"]
        for lado, x in (("LONG", up), ("SHORT", dn)):
            if x >= lim:
                out.append({"i": i, "t": v[i]["t"] + H, "lado": lado, "mov": round(x, 4), "limite": round(lim, 4)})
    escolhidos = []
    for m in sorted(out, key=lambda m: -m["mov"]):              # o maior por lado; janelas sobrepostas contam uma vez
        if all(not (e["lado"] == m["lado"] and abs(e["t"] - m["t"]) < JANELA_H * H) for e in escolhidos):
            escolhidos.append(m)
    return escolhidos


def atualizar(pasta, velas_1h, uni, now, papel):
    sinais = {}
    for o in (papel.get("abertas") or []) + (papel.get("fechadas") or []):
        sinais.setdefault((o.get("b"), o.get("lado")), []).append(int(o.get("t_sinal") or 0) + 3600 * {"30m": 0.5, "1H": 1, "4H": 4}.get(o.get("tf"), 1))
    btc = velas_1h.get("BTC")
    eventos = []
    for b, v in velas_1h.items():
        for m in movimentos(v, now):
            t_sin = sinais.get((b, m["lado"]), [])
            det = any(m["t"] - JANELA_H * H <= t <= m["t"] + 1800 for t in t_sin)
            ev = {"base": b, "classe": (uni.get(b) or {}).get("classe"), "lado": m["lado"], "inicio": m["t"], "movimento": m["mov"],
                  "limite": m["limite"], "detetado": det}
            if not det:
                ev["condicoes_em_tempo_real"] = condicoes(v, m["i"], btc)
                ev["identificavel"] = bool(ev["condicoes_em_tempo_real"])
                ev["teto_hipotetico"] = round(m["mov"] - CUSTO, 4)
            eventos.append(ev)
    p = os.path.join(pasta, "hunter", "cobertura.json")
    try:
        with open(p, encoding="utf-8") as f:
            ant = json.load(f)
    except (OSError, ValueError):
        ant = {"eventos": []}
    chave = lambda e: (e["base"], e["lado"], e["inicio"])
    junto = {chave(e): e for e in ant.get("eventos") or []}
    junto.update({chave(e): e for e in eventos})
    todos = sorted(junto.values(), key=lambda e: e["inicio"])[-3000:]
    ult = [e for e in todos if e["inicio"] >= now - 24 * H]
    D = [e for e in ult if not e["detetado"]]
    cond = {}
    for e in D:
        for c in e.get("condicoes_em_tempo_real") or ["nenhuma"]:
            cond[c] = cond.get(c, 0) + 1
    resumo = {"t": int(now), "janela_h": 24, "instrumentos_com_1h": len(velas_1h), "movimentos": len(ult),
              "detetados": len(ult) - len(D), "nao_detetados_D": len(D), "D_identificaveis": sum(1 for e in D if e.get("identificavel")),
              "D_por_condicao": cond, "D_por_lado": {l: sum(1 for e in D if e["lado"] == l) for l in ("LONG", "SHORT")},
              "D_por_classe": {c: sum(1 for e in D if e.get("classe") == c) for c in {e.get("classe") for e in D}},
              "aviso": "teto_hipotetico = excursao maxima menos custos, escolhida depois do movimento: NAO e resultado real nem realizavel"}
    out = {"resumo": resumo, "eventos": todos}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    return resumo
