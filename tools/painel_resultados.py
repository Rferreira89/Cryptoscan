"""(12/11) Painel de resultados: o que o CryptoScan fez de facto, por corretora e estrategia, com REAL, PAPEL e
SOMBRA sempre separados, e as oportunidades perdidas com o motivo. So le copias publicas (sem dinheiro: tudo em R).

Bybit UE (state.json, ramo data): ledger -> operacoes REAIS (so as executadas na corretora), PAPEL; promo_lost ->
oportunidades perdidas por motivo e estrategia; piloto e regime atuais.
OKX (okx.json, ramo okx): real.hist -> operacoes REAIS (fechadas com execucao) e ordens que nao encheram; fechadas ->
PAPEL do agente H40; recuo -> H46.
Uso: python3 -m tools.painel_resultados <pasta_publica> [saida.json]"""
import json
import os
import sys
import time
from collections import Counter, defaultdict


def _j(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def metricas(rs):
    rs = [float(r) for r in rs if r is not None]
    if not rs:
        return {"n": 0}
    g, p = [x for x in rs if x > 0], [x for x in rs if x <= 0]
    eq = pk = dd = 0.0
    for r in rs:
        eq += r
        pk = max(pk, eq)
        dd = min(dd, eq - pk)
    return {"n": len(rs), "soma_r": round(sum(rs), 3), "r_op": round(sum(rs) / len(rs), 3),
            "pf": round(sum(g) / -sum(p), 3) if p and sum(p) < 0 else None, "acerto": round(len(g) / len(rs), 3),
            "max_dd_r": round(dd, 3)}


def bybit(St):
    led = St.get("ledger") or []
    por = defaultdict(list)
    for r in sorted(led, key=lambda r: r.get("closed_at") or 0):
        if r.get("status") != "CLOSED" or r.get("result_r") is None:
            continue
        modo = r.get("mode") or "?"
        if modo == "REAL" and r.get("executed") is False:
            modo = "REAL_SEM_EXECUCAO (nao conta)"
        por[(modo, r.get("strategy"))].append(r["result_r"])
    abertas = [{"ativo": r.get("asset"), "estrategia": r.get("strategy"), "modo": r.get("mode")} for r in led
               if r.get("status") in ("OPEN", "WAITING", "ACTIVE", "TRIGGERED")]
    lado, semanas = defaultdict(list), Counter()
    for r in led:
        if r.get("status") == "CLOSED" and r.get("mode") == "REAL" and r.get("executed") is True and r.get("result_r") is not None:
            lado[r.get("side") or "LONG"].append(r["result_r"])
            semanas[time.strftime("%G-S%V", time.gmtime(r.get("closed_at") or 0))] += 1
    pl = St.get("promo_lost") or []
    motivos = Counter((x.get("strategy"), (x.get("reason") or "").split(":")[0]) for x in pl)
    return {"operacoes": {f"{m} | {e}": metricas(v) for (m, e), v in sorted(por.items())},
            "real_por_lado": {k: metricas(v) for k, v in sorted(lado.items())},
            "real_por_semana": dict(sorted(semanas.items())[-8:]),
            "abertas": abertas, "piloto": St.get("piloto"), "regime": (St.get("mercado") or {}).get("regime"),
            "so_papel": St.get("so_papel"),
            "sinais_rejeitados_total": len(pl),
            "oportunidades_perdidas": [{"estrategia": e, "motivo": m, "n": n} for (e, m), n in motivos.most_common(15)],
            "perdidas_recentes": [{"t": x.get("t"), "ativo": x.get("asset"), "estrategia": x.get("strategy"),
                                   "motivo": (x.get("reason") or "")[:90]} for x in pl[-10:]]}


def okx(O):
    real = (O or {}).get("real") or {}
    hist = real.get("hist") or []
    rs, nao = [], Counter()
    for h in hist:
        if h.get("estado") == "fechada" and h.get("entrada") and h.get("stop") and h.get("saida") and h["entrada"] != h["stop"]:
            rs.append((h["saida"] - h["entrada"]) / (h["entrada"] - h["stop"]))
        elif h.get("estado") != "fechada":
            nao[h.get("estado")] += 1
    papel = defaultdict(list)
    for f in (O or {}).get("fechadas") or []:
        if f.get("r") is not None:
            papel[f.get("tipo") or "?"].append(f["r"])
    rec = (O or {}).get("recuo") or {}
    return {"real_h40_h46_bruto": metricas(rs), "ordens_sem_execucao": dict(nao),
            "papel_h40": {k: metricas(v) for k, v in papel.items()},
            "h46": {"fechadas": metricas([f.get("r") for f in rec.get("fechadas") or []]),
                    "abertas": len(rec.get("abertas") or {}), "btc_em_subida": (rec.get("resumo") or {}).get("btc_em_subida")},
            "posicoes_reais_abertas": [h.get("asset") for h in hist if h.get("estado") in ("aberta", "pendente")]}


def decisoes(r):
    """Leitura operacional: o que o painel manda fazer (regras objetivas, sem dinheiro)."""
    out = []
    for k, m in (r["bybit_ue"]["operacoes"] or {}).items():
        if k.startswith("REAL |") and m.get("n", 0) >= 5 and m.get("r_op", 0) < 0:
            out.append(f"{k}: {m['n']} reais com {m['r_op']}R/op: manter fora do real")
    top = r["bybit_ue"]["oportunidades_perdidas"][:1]
    if top:
        out.append(f"maior causa de sinais perdidos: {top[0]['estrategia']} / {top[0]['motivo']} ({top[0]['n']})")
    o = r["okx"]["real_h40_h46_bruto"]
    if o.get("n", 0) and o.get("r_op", 0) < 0:
        out.append(f"OKX real {o['n']} ops a {o['r_op']}R/op: nenhuma estrategia OKX com vantagem demonstrada no real")
    return out


def papel_continuo(P):
    """Papel continuo transversal (ramo papel-transversal): por familia, LONG e SHORT. E PAPEL, nunca real."""
    return {"ultimo_dia": (P or {}).get("ultimo_dia"), "abertas": len((P or {}).get("abertas") or []),
            "por_familia": (P or {}).get("resumo") or {}}


def correr(pasta):
    St, O = _j(os.path.join(pasta, "state.json")), _j(os.path.join(pasta, "okx.json"))
    r = {"bybit_ue": bybit(St), "okx": okx(O), "papel_transversal": papel_continuo(_j(os.path.join(pasta, "papel.json")))}
    pt = St.get("porta_long") or {}
    r["porta_long"] = {"pilotos_em_real": pt.get("pilotos") or [],
                       "a_falhar": {k: v.get("motivos") for k, v in list((pt.get("relatorio") or {}).items())[:40]}}
    pl = St.get("promo_lost") or []
    r["bybit_ue"]["perdidas_por_capacidade"] = sum(1 for x in pl if (x.get("reason") or "").startswith("capacidade"))
    r["decisoes"] = decisoes(r)
    return dict(r, aviso="REAL so com execucao confirmada na corretora; PAPEL e SOMBRA nunca somados ao REAL; tudo em R.")


if __name__ == "__main__":
    r = correr(sys.argv[1])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print(json.dumps(r, ensure_ascii=False, indent=1))
