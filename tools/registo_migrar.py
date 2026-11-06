"""(06/11, P3) Migracao de demonstracao para o registo unico: le os ficheiros publicados pelos agentes, converte para a
forma comum, prova que nada se perdeu (contagens, somas de R e registos intactos) e mostra as metricas uniformes.
So leitura: nao escreve em nenhum ramo nem muda subsistemas. Uso:
  python3 tools/registo_migrar.py --state state.json --okx okx.json --tfshort okx_tfshort.json [--saida registo.json]"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import registo as G  # noqa: E402


def carregar(caminho):
    return json.load(open(caminho)) if caminho and os.path.exists(caminho) else {}


def migrar(state, okx, tfs, forma=None, liga=None):
    ops = G.do_ledger(state) + G.do_state_papel(state) + G.do_okx(okx) + G.do_tfshort(tfs)
    agregados, controlos = G.do_arena(state, forma, liga)
    G.juntar_controlos(ops, controlos)
    fontes = {"state.ledger": ([r for r in state.get("ledger") or [] if r.get("status") == "CLOSED"], "real_r"),
              "state.papel_panico": ((state.get("papel_panico") or {}).get("fechadas") or [], "r"),
              "state.paper_trend": ((state.get("paper_trend") or {}).get("closed") or [], "r"),
              "state.paper_shadow": ((state.get("paper_shadow") or {}).get("closed") or [], "r"),
              "okx.real.hist": ([h for h in (okx.get("real") or {}).get("hist") or [] if h.get("estado") == "fechada"], "ret_pct"),
              "okx.fechadas": (okx.get("fechadas") or [], "r"),
              "okx.recuo.fechadas": ((okx.get("recuo") or {}).get("fechadas") or [], "r"),
              "okx_tfshort.sinais": ((tfs.get("sinais") or {}).get("fechadas") or [], "R"),
              "okx_tfshort.conta": ((tfs.get("conta") or {}).get("fechadas") or [], "R")}
    for nome, v in (state.get("paper_ring") or {}).items():
        fontes[f"state.paper_ring.{nome}"] = ((v or {}).get("closed") or [], "r")
    for g, v in ((state.get("paper_bounce") or {}).get("geo") or {}).items():
        fontes[f"state.paper_bounce.{g}"] = ((v or {}).get("closed") or [], "r")
    for fase in ("lateral", "subida"):
        fontes[f"state.papel_fases.{fase}"] = (((state.get("papel_fases") or {}).get(fase) or {}).get("fechadas") or [], "r")
    rec = G.reconciliar(fontes, ops)
    # agregados: tudo o que existia na arena e na liga tem de estar presente e intacto
    for fonte, orig in (("arena.forma", list(((forma or {}).get("lutadores") or {}).values())),
                        ("liga", list((liga or {}).get("tabela") or []))):
        mig = [a["bruto"] for a in agregados if a["fonte"] == fonte]
        rec[fonte] = {"originais": len(orig), "migrados": len(mig), "intactos": sum(1 for a, b in zip(mig, orig) if a == b),
                      "soma_r_original": None, "soma_r_migrada": None, "ok": mig == orig, "agregado": True}
    ctrl = (state.get("arena") or {}).get("ctrl") or {}
    ligados = sum(1 for o in ops if o.get("controlo_acaso"))
    rec["arena.ctrl"] = {"originais": len(ctrl), "migrados": len(controlos), "intactos": sum(1 for k in ctrl if controlos.get(k) == list(ctrl[k])),
                         "ligados_a_operacoes": ligados, "soma_r_original": None, "soma_r_migrada": None,
                         "ok": all(controlos.get(k) == list(ctrl[k]) for k in ctrl), "agregado": True}
    return ops, rec, agregados


def explicar(ops):
    """Contagem por classe e operacoes reais sem R, para o relatorio."""
    por = {}
    for o in ops:
        por[o["classe"]] = por.get(o["classe"], 0) + 1
    reais = [o for o in ops if o["classe"] == "executada"]
    sem_r = [o for o in reais if o["R"] is None]
    return {"por_classe": por, "reais": len(reais), "reais_com_r": len(reais) - len(sem_r),
            "reais_sem_r": [{"id": o["id_origem"], "estrategia": o["estrategia"], "moeda": o["moeda"], "fonte": o["fonte"],
                             "em_falta": o["em_falta"], "campos_da_fonte": {k: o["bruto"].get(k) for k in
                             ("status", "executed", "real", "reason", "tp_hit", "entry", "exec_price", "exit", "result_r",
                              "real_r", "user_result_r", "kind")}, "alerta": o.get("alerta")}
                            for o in sem_r],
            "reais_r_de_fecho_manual": [o["id_origem"] for o in reais if o.get("r_fonte") == "user_result_r"],
            "alertas": [(o["id_origem"], o["alerta"]) for o in ops if o.get("alerta")]}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--state"); a.add_argument("--okx"); a.add_argument("--tfshort"); a.add_argument("--saida")
    a.add_argument("--forma"); a.add_argument("--scan")
    x = a.parse_args()
    ops, rec, ag = migrar(carregar(x.state), carregar(x.okx), carregar(x.tfshort), carregar(x.forma),
                          carregar(x.scan).get("liga"))
    print("== PRESERVACAO (por fonte)")
    for f, r in rec.items():
        if r["originais"] or r["migrados"]:
            print(f"  {'OK ' if r['ok'] else 'ERRO'} {f}: {r['originais']} originais -> {r['migrados']} migrados, "
                  f"{r['intactos']} intactos; soma original {r['soma_r_original']} = migrada {r['soma_r_migrada']}")
    print(f"  total: {len(ops)} operacoes e {len(ag)} agregados; todas as fontes ok: {all(r['ok'] for r in rec.values())}")
    e = explicar(ops)
    print("== CLASSES", e["por_classe"], "| reais:", e["reais"], "(com R:", e["reais_com_r"], ")")
    for r in e["reais_sem_r"]:
        print("  REAL SEM R:", json.dumps(r, ensure_ascii=False))
    print("  R real vindo de fecho manual (user_result_r):", e["reais_r_de_fecho_manual"])
    for a_ in e["alertas"]:
        print("  ALERTA:", a_)
    print("== METRICAS UNIFORMES (estrategia | origem)")
    for (e, o), m in G.tabela(ops).items():
        print(f"  {e:22s} {o:19s} fechadas {m['fechadas']:3d} (sem R {m['sem_r']}) soma {m['soma_r']:+7.2f}R "
              f"expectativa {m['expectativa_r'] if m['expectativa_r'] is None else format(m['expectativa_r'], '+.3f')} "
              f"PF {m['profit_factor']} queda {m['queda_max_r']}R acerto {m['acerto_pct']}% por semana {m['por_semana']}")
    if x.saida:
        json.dump({"ops": ops, "agregados": ag, "reconciliacao": rec}, open(x.saida, "w"), ensure_ascii=False)
    return 0 if all(r["ok"] for r in rec.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
