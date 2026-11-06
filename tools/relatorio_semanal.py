"""(06/11, P3) Relatorio semanal UNICO, so de leitura, a partir do registo unico (tools/registo_migrar.py).
Blocos separados que nunca se somam: real (executadas) | sinais reais nao executados | papel | sombra | investigacao
(agregados da arena) | liga (derivada do papel). Inclui campos em falta, alertas e a prova de preservacao.
Nao envia nada nem muda nenhum subsistema. Uso: python3 tools/relatorio_semanal.py <registo_unico.json>"""
import json
import sys

ORDEM = (("executada", "Real: operações executadas com dinheiro"),
         ("sinal_nao_executado", "Sinais reais que não chegaram a ser executados (sombra)"),
         ("papel", "Papel (simulação ao vivo)"),
         ("sombra", "Sombra (o que a estratégia faria)"))


def _f(x, fmt="+.2f"):
    return "—" if x is None else (format(x, fmt) if isinstance(x, (int, float)) and x != float("inf") else str(x))


def texto(reg, semana=""):
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from engine import registo as G
    ops, ag, rec = reg["ops"], reg.get("agregados") or [], reg.get("reconciliacao") or {}
    t = G.tabela(ops)
    L = [f"# Cryptoscan — relatório semanal único {semana}".rstrip(), ""]
    for classe, titulo in ORDEM:
        linhas = [(e, m) for (e, c), m in t.items() if c == classe]
        L.append(f"## {titulo}")
        if not linhas:
            L += ["Sem operações fechadas.", ""]; continue
        L.append("| Estratégia | Fechadas | Sem R | Soma R | Expectativa | PF | Queda (R) | Acerto | Por semana |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for e, m in linhas:
            L.append(f"| {e} | {m['fechadas']} | {m['sem_r']} | {_f(m['soma_r'])} | {_f(m['expectativa_r'], '+.3f')} | "
                     f"{_f(m['profit_factor'], '.2f')} | {_f(m['queda_max_r'], '.2f')} | {_f(m['acerto_pct'], '.0f')}% | {_f(m['por_semana'], '.1f')} |")
        L.append("")
    inv = [a for a in ag if a["fonte"] == "arena.forma"]
    L += ["## Investigação: arena (últimos 90 dias re-simulados, não são operações ao vivo)",
          "| Lutador | n | R médio | Soma R | Veredicto |", "|---|---|---|---|---|"]
    L += [f"| {a['estrategia']} | {a['n']} | {_f(a['media_r'], '+.3f')} | {_f(a['soma_r'])} | {a['veredicto'] or '—'} |"
          for a in sorted(inv, key=lambda a: -(a["media_r"] or -9))]
    liga = [a for a in ag if a["fonte"] == "liga"]
    L += ["", "## Liga semanal (derivada do papel e da sombra; não se soma)", "| Estratégia | n | R médio |", "|---|---|---|"]
    L += [f"| {a['estrategia']} | {a['n']} | {_f(a['media_r'], '+.3f')} |" for a in liga]
    falta = {}
    for o in ops:
        for k in o["em_falta"]:
            falta.setdefault(k, set()).add(o["classe"])
    L += ["", "## Campos em falta nas fontes (não inventados)"]
    L += [f"- {k}: em operações de {', '.join(sorted(v))}" for k, v in sorted(falta.items())]
    alertas = [o for o in ops if o.get("alerta")]
    L += ["", "## Alertas"] + ([f"- {o['id_origem']}: {o['alerta']}" for o in alertas] or ["- nenhum"])
    ok = all(r.get("ok") for r in rec.values())
    L += ["", f"## Preservação: {'todas as fontes conferem' if ok else 'HÁ FONTES QUE NÃO CONFEREM'} "
              f"({len(ops)} operações, {len(ag)} agregados)"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    print(texto(json.load(open(sys.argv[1])), sys.argv[2] if len(sys.argv) > 2 else ""))
