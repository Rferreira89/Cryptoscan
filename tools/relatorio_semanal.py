"""(06/11, P3) Relatorio semanal UNICO, so de leitura, a partir do registo unico (tools/registo_migrar.py).

Seis blocos rigorosamente separados, que nunca se somam:
  1. Real: operacoes executadas e fechadas com resultado conhecido
  2. Real: posicoes ainda abertas
  3. Real: executadas com resultado desconhecido (fora de todas as metricas; o R do sinal nunca conta)
  4. Papel (simulacao ao vivo)
  5. Sombra (o que a estrategia faria: TF-SHORT sombra e sinais reais nao executados)
  6. Backtests e investigacao (arena: re-simulacoes, nao sao operacoes ao vivo)
Uma operacao que apareca em duas fontes na mesma classe conta uma so vez e aparece em alerta.
So R e contagens: nenhum valor em dinheiro (o repositorio e publico; o texto vai so para o Telegram).

Uso: python3 tools/relatorio_semanal.py --state s.json --okx o.json --tfshort t.json [--sombra x.json]
                                        [--forma f.json] [--scan scan.json] [--enviar]"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import registo as G  # noqa: E402

CAB = "| Estratégia | Fechadas | Sem R | Soma R | Expectativa | PF | Queda (R) | Acerto |"
SEP = "|---|---|---|---|---|---|---|---|"


def _f(x, fmt="+.2f"):
    return "—" if x is None else (format(x, fmt) if isinstance(x, (int, float)) and x != float("inf") else str(x))


def _tabela(ops):
    if not ops:
        return ["Nenhuma.", ""]
    L = [CAB, SEP]
    g = {}
    for o in ops:
        g.setdefault((o["estrategia"], o["classe"]), []).append(o)
    for (e, c), v in sorted(g.items()):
        m = G.metricas(v)
        nome = e if c != "sinal_nao_executado" else f"{e} (sinal real não executado)"
        L.append(f"| {nome} | {m['fechadas']} | {m['sem_r']} | {_f(m['soma_r'])} | {_f(m['expectativa_r'], '+.3f')} | "
                 f"{_f(m['profit_factor'], '.2f')} | {_f(m['queda_max_r'], '.2f')} | {_f(m['acerto_pct'], '.0f')}% |")
    return L + [""]


def _dia(t):
    return time.strftime("%d/%m", time.gmtime(t)) if t else "—"


def blocos(ops, abertas, ag, nucleo_visivel=True):
    """Separacao em seis blocos. Devolve {bloco: lista}; cada operacao fica em exatamente um bloco."""
    ops = G.sem_duplicados(ops)
    b = {"real_fechadas": [o for o in ops if o["classe"] == "executada" and o["R"] is not None],
         "real_desconhecido": [o for o in ops if o["classe"] == "executada" and o["R"] is None],
         "papel": [o for o in ops if o["classe"] == "papel"],
         "sombra": [o for o in ops if o["classe"] in ("sombra", "sinal_nao_executado")],
         "investigacao": [o for o in ops if o["classe"] == "investigacao"],
         "real_abertas": list(abertas or []),
         "arena": [a for a in ag or [] if a["fonte"] == "arena.forma"]}
    return b


def texto(ops, abertas, ag, rec, semana="", nucleo_visivel=True, sombra=None):
    dup = G.duplicados(ops)
    b = blocos(ops, abertas, ag, nucleo_visivel)
    L = [f"Cryptoscan — relatório semanal único {semana}".rstrip(), ""]
    L += ["1. REAL — executadas e fechadas (resultado conhecido)"] + _tabela(b["real_fechadas"])
    L += ["2. REAL — posições abertas"]
    L += [f"- {a['corretora']} {a['moeda']} {a['lado']} desde {_dia(a['desde'])}" for a in b["real_abertas"]] or ["- nenhuma"]
    if not nucleo_visivel:
        L.append("- (tendência BTC: estado só na cópia privada; ver a mensagem da conta)")
    L.append("")
    L += ["3. REAL — executadas com resultado DESCONHECIDO (fora das métricas)"]
    L += [f"- {o['id_origem']} ({o['corretora']}): {o.get('estado_reconciliacao') or 'sem dados reais'}; "
          f"R do sinal {_f(o.get('R_sinal'))} NÃO conta" for o in b["real_desconhecido"]] or ["- nenhuma"]
    L.append("")
    L += ["4. PAPEL (simulação ao vivo)"] + _tabela(b["papel"])
    L += ["5. SOMBRA (o que a estratégia faria; sem ordens)"] + _tabela(b["sombra"])
    if sombra is not None:
        ne = sombra.get("nao_executaveis") or []
        mot = {}
        for x in ne:
            mot[x["motivo"]] = mot.get(x["motivo"], 0) + 1
        mins = sorted(x["capital_minimo_usd"] for x in ne if x.get("motivo") == "abaixo_minimo_do_contrato"
                      and x.get("capital_minimo_usd"))
        L.append(f"TF-SHORT sombra: {len(sombra.get('abertas') or {})} abertas; sinais não executáveis com a conta de 20: "
                 + (", ".join(f"{k} {v}" for k, v in sorted(mot.items())) or "nenhum"))
        if mins:
            L.append(f"Capital mínimo que teria permitido os sinais abaixo do mínimo: mediana {mins[len(mins) // 2]:.0f}")
        L.append("")
    L += ["6. BACKTESTS E INVESTIGAÇÃO (re-simulações; não são operações ao vivo)"]
    L += _tabela(b["investigacao"])[:-1] if b["investigacao"] else []
    if b["arena"]:
        vivos = [a for a in b["arena"] if (a["veredicto"] or "") != "MORTA" and a["n"]]
        L += [f"Arena, últimos 90 dias ({len(b['arena'])} lutadores; {len(vivos)} vivos com dados; os mortos não se listam):"]
        L += [f"- {a['estrategia']}: n {a['n']}, R médio {_f(a['media_r'], '+.3f')}, {a['veredicto'] or '—'}"
              for a in sorted(vivos, key=lambda a: -(a["media_r"] if a["media_r"] is not None else -9))]
    elif not b["investigacao"]:
        L.append("Nenhuma.")
    L.append("")
    alertas = [o for o in ops if o.get("alerta")]
    L += ["Alertas"] + ([f"- {o['id_origem']}: {o['alerta']}" for o in alertas] +
                        [f"- duplicado entre fontes (contado uma vez): {k[1]} {k[3]} {k[0]}" for k in dup] or ["- nenhum"])
    ok = all(r.get("ok") for r in (rec or {}).values())
    L += ["", f"Preservação: {'todas as fontes conferem' if ok else 'HÁ FONTES QUE NÃO CONFEREM'} "
              f"({len(ops)} operações, {len(ag or [])} agregados)"]
    return "\n".join(L) + "\n"


def partes(txt, limite=3900):
    """Telegram aceita ~4000 caracteres por mensagem: corta em linhas."""
    out, cur = [], ""
    for linha in txt.splitlines(keepends=True):
        if len(cur) + len(linha) > limite and cur:
            out.append(cur); cur = ""
        cur += linha
    return out + ([cur] if cur else [])


def _carregar(c):
    return json.load(open(c)) if c and os.path.exists(c) else {}


def saude_e_rejeicoes(ops, pasta):
    """(10/11) Dois blocos de leitura: estrategias ao vivo que se afastam da evidencia (engine/decaimento) e as
    oportunidades que nao chegaram a dinheiro real, com o motivo (tools/rejeicoes)."""
    from engine import decaimento as D
    L = ["", "SAÚDE DAS ESTRATÉGIAS AO VIVO (real, papel e sombra; mínimo 10 operações)"]
    todas = D.vigiar(ops)
    v = [x for x in todas if x["estado"] != "evidencia_insuficiente"]
    L += [f"- {x['estrategia']} ({x['classe']}): {x['estado'].replace('_', ' ')}"
          f"{'' if x.get('definitivo') else ' (preliminar)'}, n {x['n']} em {x['dias_independentes']} dias, "
          f"R médio {x['media_R']:+.2f} (IC90 {x['ic90'][0]:+.2f} a {x['ic90'][1]:+.2f})"
          + (f", referência {x['referencia_R']:+.2f}" if x["referencia_R"] is not None else "")
          for x in v] or ["- nenhuma estratégia com evidência suficiente (10 operações em 5 dias)"]
    poucas = len(todas) - len(v)
    if poucas:
        L.append(f"- evidência insuficiente em {poucas} estratégia(s): nada se conclui ainda")
    if pasta and os.path.isdir(pasta):
        from tools import rejeicoes as RJ
        _, res = RJ.tudo(pasta)
        L += ["", "OPORTUNIDADES QUE NÃO CHEGARAM A REAL (motivo e resultado em papel, quando existe)"]
        L += [f"- [{r['classe']}] {r['estrategia']}: {r['motivo']} — {r['n']}"
              + (f", em papel {r['com_resultado']} com R médio {r['media_R']:+.2f}" if "media_R" in r else "")
              + f" → {r['veredito']}" for r in res[:8]] or ["- nenhuma"]
    return "\n".join(L) + "\n"


def main():
    a = argparse.ArgumentParser()
    for k in ("state", "okx", "tfshort", "sombra", "kronos", "forma", "scan"):
        a.add_argument(f"--{k}")
    a.add_argument("--enviar", action="store_true")
    a.add_argument("--exposicao", action="store_true")
    x = a.parse_args()
    from tools.registo_migrar import migrar
    state, okx = _carregar(x.state), _carregar(x.okx)
    ops, rec, ag = migrar(state, okx, _carregar(x.tfshort), _carregar(x.forma), _carregar(x.scan).get("liga"))
    corpo = _carregar(x.sombra)
    sombra = corpo.get("estado") if corpo else None
    ops += G.do_tfs_sombra(sombra)
    ops += G.do_kronos_sombra((_carregar(x.kronos) or {}).get("estado"))
    semana = time.strftime("semana até %d/%m/%Y", time.gmtime())
    txt = texto(ops, G.abertas_reais(state, okx), ag, rec, semana, G.nucleo_visivel(state), sombra)
    if x.exposicao and x.state:              # (10/11) mapa de exposicao: precisa de precos publicos da OKX (rede)
        try:
            from tools import exposicao_diaria as EX
            txt += EX.texto(EX.correr(os.path.dirname(os.path.abspath(x.state))))
        except Exception as e:               # noqa: BLE001
            txt += f"\n(mapa de exposição indisponível: {type(e).__name__})\n"
    try:                                     # blocos de leitura: uma falha aqui nunca impede o relatorio principal
        txt += saude_e_rejeicoes(ops, os.path.dirname(os.path.abspath(x.state)) if x.state else None)
    except Exception as e:                   # noqa: BLE001
        txt += f"\n(blocos de saúde e rejeições indisponíveis: {type(e).__name__})\n"
    print(txt)
    if x.enviar:
        from engine import alerts
        for p in partes(txt):
            alerts.send(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
