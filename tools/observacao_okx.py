"""(19/11, ordem do Rui "OKX Autonomous Profit Engine") Periodo de observacao operacional da OKX: 7 dias seguidos.

So LEITURA e registo. Nao envia ordens, nao mexe em posicoes, stops, estrategias, risco nem parametros: le o que os
executores ja publicam e guarda fotografias periodicas e, no fim, o relatorio consolidado.

Entradas (copias dos ramos, lidas pelo workflow observacao-okx.yml):
  piloto_publico.json          ramo piloto-okx   (piloto real: portas, orcamento, operacoes, funil de oportunidades)
  okx.json                     ramo okx          (executor antigo: espelho/recuo/panico; so estado, sem precos aqui)
  contabilidade_okx.json       ramo contabilidade (R bruto e liquido confirmados na OKX, custos, deslize)
  contabilidade_okx_privado.json  (opcional, decifrado com DATA_KEY: dinheiro; SO para a mensagem do Telegram)
  estrategias_registo.json     ramo autonomo     (r_medio do backtest de cada estrategia, para comparar)
  runs.json                    (opcional) voltas do piloto e do agente no GitHub Actions durante o periodo
  observacao_okx.json          ramo observacao-okx (estado desta ferramenta)

Saidas (ramo observacao-okx, PUBLICO: so contagens, R e %; verificado com contabilidade.sem_dinheiro):
  observacao_okx.json, relatorio_final.txt (so no fim).
Telegram: uma fotografia por dia (UTC) e o relatorio final uma vez; o dinheiro so aparece no Telegram.

Regras do periodo (ordem do Rui): sem otimizar sobre estes resultados, sem mudar estrategias a meio por perdas
normais; sete dias sao observacao inicial, nao prova estatistica.
Uso: python3 tools/observacao_okx.py <pasta> [--sem-telegram]"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import contabilidade as C  # noqa: E402

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CFG_FICHEIRO = os.path.join(RAIZ, "observacao_okx.json")
DIA = 86400


def ler(pasta, nome, omissao=None):
    try:
        with open(os.path.join(pasta, nome), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return omissao


def _chave(o):
    return "|".join(str(o.get(k)) for k in ("executor", "estrategia", "ativo", "lado", "dia_fecho", "motivo", "r_liquido"))


def _r(x, n=3):
    return None if x is None else round(float(x), n)


# ------------------------------------------------------------------ fotografia ------------------------------------
def posicoes_piloto(piloto):
    return [{"executor": "piloto", "ativo": o.get("base"), "estrategia": o.get("estrategia"), "lado": o.get("lado"),
             "tf": o.get("tf"), "stop_confirmado": bool(o.get("stop_confirmado")), "r_aberto": _r(o.get("r_aberto"))}
            for o in (piloto or {}).get("ops") or [] if o.get("estado") == "aberta"]


def posicoes_antigo(okx, now):
    out = []
    for ativo, o in (((okx or {}).get("real") or {}).get("ops") or {}).items():
        if o.get("estado") != "aberta":
            continue
        ok = o.get("stop_ok")
        out.append({"executor": "executor antigo", "ativo": ativo, "estrategia": o.get("estrategia_bybit") or o.get("estrategia"),
                    "lado": o.get("lado") or "LONG", "stop_conferido_ha_min": int((now - ok) // 60) if ok else None,
                    "stop_confirmado": bool(ok) and now - ok < 3 * 3600})
    return out


def funil(piloto, desde):
    por_cat, por_dec, n = {}, {}, 0
    for o in (piloto or {}).get("oportunidades") or []:
        if (o.get("t") or 0) < desde:
            continue
        n += 1
        por_cat[o.get("categoria") or "?"] = por_cat.get(o.get("categoria") or "?", 0) + 1
        por_dec[o.get("decisao") or "?"] = por_dec.get(o.get("decisao") or "?", 0) + 1
    return {"sinais": n, "por_categoria": por_cat, "por_decisao": por_dec}


def ops_piloto_janela(piloto, desde):
    abertas = fechadas = 0
    rs = []
    for o in (piloto or {}).get("ops") or []:
        if (o.get("t_execucao") or 0) >= desde:
            abertas += 1
        if o.get("estado") == "fechada" and (o.get("t_fecho") or 0) >= desde and o.get("r") is not None:
            fechadas += 1
            rs.append(o["r"])
    return {"executadas": abertas, "fechadas": fechadas, "soma_r_estado_piloto": _r(sum(rs)) if rs else 0.0}


def fotografia(piloto, okx, cfg, now):
    p = piloto or {}
    portas = p.get("portas") or {}
    orc = p.get("orcamento") or {}
    return {"t": now,
            "piloto_t_idade_min": int((now - p["t"]) // 60) if p.get("t") else None,
            "piloto_operacional": bool(p.get("operacional")), "piloto_bloqueado": bool(p.get("bloqueado")),
            "piloto_suspenso": bool(p.get("suspenso")), "piloto_motivo": p.get("motivo"),
            "portas_fechadas": sorted(k for k, v in portas.items() if not (v or {}).get("ok")),
            "estrategias_ativas": len(p.get("ativas") or []),
            "orcamento": {k: orc.get(k) for k in ("abertas", "maximo", "risco_usado_pct", "nocional_usado_pct",
                                                  "margem_usada_pct", "risco_por_direcao_pct")},
            "posicoes": posicoes_piloto(p) + posicoes_antigo(okx, now),
            "funil_desde_inicio": funil(p, cfg["inicio"]),
            "piloto_desde_inicio": ops_piloto_janela(p, cfg["inicio"])}


# ------------------------------------------------------------------ contabilidade ---------------------------------
def ops_janela(contab, base):
    """Operacoes fechadas confirmadas pela contabilidade que NAO existiam no inicio do periodo."""
    vistos = set(base or [])
    return [o for o in (contab or {}).get("operacoes") or [] if _chave(o) not in vistos]


def resultados(ops, registo=None):
    est_bt = {}
    for e in ((registo or {}).get("estrategias") or {}).values():
        bt = e.get("backtest") or {}
        if bt.get("r_medio") is not None:
            est_bt["piloto:" + e["id"]] = bt["r_medio"]
    out = {"total": C.resumo(ops), "total_bruto": C.resumo(ops, "r_bruto"),
           "incompletas": sum(1 for o in ops if not o.get("completa"))}
    for chave in ("executor", "estrategia", "lado"):
        out["por_" + chave] = {k: C.resumo(v) for k, v in sorted(C.agrupar(ops, chave).items())}
    for k, v in out["por_estrategia"].items():
        if k in est_bt:
            v["backtest_r_medio"] = est_bt[k]
    return out


def dinheiro_janela(privado, inicio):
    """So para o Telegram: totais em dinheiro das operacoes fechadas desde o inicio (contabilidade privada)."""
    ops = [o for o in (privado or {}).get("operacoes") or [] if (o.get("t_fecho") or 0) >= inicio]
    tot = {k: round(sum(o.get(k) or 0.0 for o in ops), 4) for k in C.CAMPOS_DINHEIRO
           if any(o.get(k) is not None for o in ops)}
    return {"n": len(ops), **tot}


def disponibilidade(runs, inicio, fim):
    """runs: {workflow: [{"t": inicio_da_volta, "ok": bool}]}. Maior intervalo sem voltas e falhas por workflow."""
    out = {}
    for wf, lst in (runs or {}).items():
        ts = sorted(r["t"] for r in lst if inicio <= r["t"] <= fim)
        marcos = [inicio] + ts + [min(fim, int(time.time()))]
        maior = max((b - a for a, b in zip(marcos, marcos[1:])), default=None)
        out[wf] = {"voltas": len(ts), "falhadas": sum(1 for r in lst if inicio <= r["t"] <= fim and not r.get("ok")),
                   "maior_intervalo_min": int(maior // 60) if maior is not None else None}
    return out


# ------------------------------------------------------------------ texto -----------------------------------------
def _linha_res(nome, r):
    if not r.get("n_com_dados"):
        return f"  {nome}: {r.get('n', 0)} op. (sem dados)"
    pf = r.get("profit_factor")
    bt = f"; backtest {r['backtest_r_medio']:+.3f}R" if r.get("backtest_r_medio") is not None else ""
    return (f"  {nome}: {r['n']} op., {r['soma_r']:+.2f}R (média {r['expectativa_r']:+.3f}R, acerto "
            f"{r['acerto_pct']:.0f}%, PF {pf if pf is not None else '—'}, DD {r['drawdown_r']:+.2f}R){bt}")


def texto(estado, cfg, final=False, dinheiro=None):
    f = estado["fotografias"][-1]
    res = estado.get("resultados") or {}
    ini = time.strftime("%d/%m %H:%M UTC", time.gmtime(cfg["inicio"]))
    fim = time.strftime("%d/%m %H:%M UTC", time.gmtime(cfg["inicio"] + cfg["dias"] * DIA))
    dias = (f["t"] - cfg["inicio"]) / DIA
    L = [("📊 OKX: relatório FINAL dos 7 dias" if final else f"📸 OKX: observação, dia {min(dias, cfg['dias']):.1f} de {cfg['dias']}"),
         f"Período: {ini} → {fim}"]
    L.append(f"Piloto: {'operacional' if f['piloto_operacional'] else 'PARADO'}"
             + (f", portas fechadas: {', '.join(f['portas_fechadas'])}" if f["portas_fechadas"] else ", todas as portas abertas")
             + f"; {f['estrategias_ativas']} estratégias ativas; risco usado {f['orcamento'].get('risco_usado_pct')}% do orçamento")
    for p in f["posicoes"]:
        L.append(f"  aberta {p['executor']}: {p['ativo']} {p['lado']} ({p['estrategia']}) stop "
                 f"{'confirmado' if p['stop_confirmado'] else 'POR CONFIRMAR'}"
                 + (f", {p['r_aberto']:+.2f}R por realizar" if p.get("r_aberto") is not None else ""))
    fu = f["funil_desde_inicio"]
    L.append(f"Sinais do piloto desde o início: {fu['sinais']}; decisões {fu['por_decisao']}; motivos {fu['por_categoria']}")
    tot = res.get("total") or {}
    L.append("Fechadas confirmadas na OKX (R líquido):")
    L.append(_linha_res("total", tot))
    if final:
        for chave in ("por_executor", "por_estrategia", "por_lado"):
            for k, v in (res.get(chave) or {}).items():
                L.append(_linha_res(k, v))
        if res.get("incompletas"):
            L.append(f"  {res['incompletas']} operação(ões) com contabilidade incompleta")
        for wf, d in (estado.get("disponibilidade") or {}).items():
            L.append(f"Disponibilidade {wf}: {d['voltas']} voltas, {d['falhadas']} falhadas, maior intervalo {d['maior_intervalo_min']} min")
        L.append("Sete dias são observação inicial, não prova estatística: com poucas operações o resultado é dominado pelo acaso.")
    if dinheiro and dinheiro.get("n"):
        L.append(f"Dinheiro (privado, {dinheiro['n']} op.): " + ", ".join(f"{k} {v:+.4f}" for k, v in dinheiro.items() if k != "n"))
    return "\n".join(L)


# ------------------------------------------------------------------ volta -----------------------------------------
def volta(estado, cfg, piloto, okx, contab, registo=None, runs=None, privado=None, now=None):
    """Devolve (estado_novo, mensagens, relatorio_final_publico_ou_None)."""
    now = int(now or time.time())
    estado = dict(estado or {})
    fim = cfg["inicio"] + cfg["dias"] * DIA
    if now < cfg["inicio"]:
        return estado, [], None
    if "base" not in estado:                          # primeira volta: operacoes ja fechadas antes do inicio
        estado["base"] = sorted(_chave(o) for o in (contab or {}).get("operacoes") or [])
        estado["inicio"] = cfg["inicio"]
    estado.setdefault("fotografias", [])
    if estado.get("final_t"):                         # o periodo acabou: nada mais a registar
        return estado, [], None
    estado["fotografias"] = (estado["fotografias"] + [fotografia(piloto, okx, cfg, now)])[-200:]
    estado["resultados"] = resultados(ops_janela(contab, estado["base"]), registo)
    estado["disponibilidade"] = disponibilidade(runs, cfg["inicio"], min(now, fim)) if runs else estado.get("disponibilidade")
    estado["t"] = now
    msgs, final_txt = [], None
    dinheiro = dinheiro_janela(privado, cfg["inicio"]) if privado else None
    if now >= fim:
        estado["final_t"] = now
        final_txt = texto(estado, cfg, final=True)
        msgs.append(texto(estado, cfg, final=True, dinheiro=dinheiro))
    else:
        dia = now // DIA
        if estado.get("ultimo_dia_aviso") != dia:
            estado["ultimo_dia_aviso"] = dia
            msgs.append(texto(estado, cfg, dinheiro=dinheiro))
    maus = C.sem_dinheiro(estado)
    if maus:
        raise ValueError(f"estado publico com campos proibidos: {maus[:5]}")
    return estado, msgs, final_txt


def main(argv):
    pasta = argv[0]
    with open(CFG_FICHEIRO, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("ativo", True):
        print("observacao desligada")
        return 0
    estado, msgs, final_txt = volta(ler(pasta, "observacao_okx.json", {}), cfg, ler(pasta, "piloto_publico.json"),
                                    ler(pasta, "okx.json"), ler(pasta, "contabilidade_okx.json"),
                                    ler(pasta, "estrategias_registo.json"), ler(pasta, "runs.json"),
                                    ler(pasta, "contabilidade_okx_privado.json"))
    with open(os.path.join(pasta, "observacao_okx.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    if final_txt:
        with open(os.path.join(pasta, "relatorio_final.txt"), "w", encoding="utf-8") as f:
            f.write(final_txt + "\n")
    for m in msgs:
        print(m)
        if "--sem-telegram" not in argv:
            try:
                from engine import alerts
                if alerts.configured():
                    alerts.send(m)
            except Exception as e:                    # o Telegram nunca impede o registo
                print("telegram falhou:", type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
