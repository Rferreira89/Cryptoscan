"""(10/11, ordem do Rui) Verificacao PRIVADA e atual da protecao das posicoes reais da OKX. SO LEITURA.

So faz pedidos GET (posicoes e ordens algo pendentes). Nunca cria, altera nem cancela ordens, nem fecha posicoes.
Para cada posicao que o estado local segue (okx.json, real.ops) e para qualquer posicao na OKX que o estado NAO segue:
  quantidade aberta, direcao, preco medio; stops ativos (lado, preco de disparo, quantidade ou "fecha tudo");
  cobertura pela engine/protecao.stop_cobre; correspondencia com o estado local (entrada, stop, existencia).
Classificacao: VERIFICADA | INSUFICIENTE | NAO VERIFICADA (consulta falhou ou falta um elemento: nunca se assume).
Os valores privados (quantidades) vao SO para o Telegram; o registo publico mostra so a classificacao e os motivos.
Se houver protecao INSUFICIENTE: alerta prioritario no Telegram e mais nada (a decisao e do Rui).
Uso: python3 tools/okx_protecao_verifica.py <okx.json do ramo okx> [--sem-telegram]"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import protecao as P  # noqa: E402

TOL_PRECO = 0.005            # 0,5%: diferenca aceite entre o preco local e o da OKX (arredondamento ao tick)


def _ler(get, path):
    r = get(path)
    return (r.get("data") or []) if isinstance(r, dict) and r.get("code") == "0" else None


def verificar(local_ops, get):
    """local_ops: real.ops do estado local. get(path) -> resposta da OKX (so GET). Devolve {ativo: relatorio}."""
    pos = _ler(get, "/api/v5/account/positions?instType=FUTURES")
    if pos is None:
        return {"_geral": {"classe": "NAO VERIFICADA", "motivos": ["consulta de posicoes falhou"]}}
    abertas = {x.get("instId"): x for x in pos if float(x.get("pos") or 0) != 0}
    out = {}
    insts = {op.get("inst"): base for base, op in (local_ops or {}).items() if op.get("estado") == "aberta"}
    for inst in set(insts) | set(abertas):
        base = insts.get(inst) or inst.split("-")[0]
        op = (local_ops or {}).get(base) or {}
        rel = {"inst": inst, "motivos": [], "privado": {}}
        x = abertas.get(inst)
        if not x:
            rel.update(classe="INSUFICIENTE" if op.get("estado") == "aberta" else "VERIFICADA",
                       motivos=["o estado local diz aberta mas a OKX nao tem posicao"] if op else [])
            out[base] = rel
            continue
        q = float(x.get("pos") or 0)
        lado = "LONG" if (x.get("posSide") == "long" or (x.get("posSide") in (None, "", "net") and q > 0)) else "SHORT"
        avg = float(x.get("avgPx") or 0) or None
        rel["privado"].update(quantidade=abs(q), preco_medio=avg)
        rel.update(lado=lado)
        a1 = _ler(get, f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
        a2 = _ler(get, f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
        if a1 is None or a2 is None:
            rel.update(classe="NAO VERIFICADA", motivos=["consulta das ordens de stop falhou"])
            out[base] = rel
            continue
        algos = a1 + a2
        rel["privado"]["stops"] = [{"lado": a.get("side"), "disparo": a.get("slTriggerPx"), "quantidade": a.get("sz"),
                                    "fecha_tudo": a.get("closeFraction") == "1", "reduce_only": a.get("reduceOnly")}
                                   for a in algos if a.get("slTriggerPx")]
        ok, mot = P.stop_cobre(algos, abs(q), lado, avg)
        rel["motivos"] += mot
        if not op:
            rel["motivos"].append("posicao na OKX que o estado local NAO segue")
        else:
            if lado != "LONG":
                rel["motivos"].append("o executor so abre LONG: direcao diferente do esperado")
            e = op.get("entrada") or op.get("lim")
            if e and avg and abs(avg / e - 1) > TOL_PRECO:
                rel["motivos"].append(f"preco medio na OKX difere da entrada local ({avg:.6g} vs {e:.6g})")
            sl = [float(a["slTriggerPx"]) for a in algos if a.get("slTriggerPx")]
            if op.get("stop") and sl and not any(abs(s / op["stop"] - 1) <= TOL_PRECO for s in sl):
                rel["motivos"].append(f"nenhum stop no preco do plano ({op['stop']:.6g})")
        rel["classe"] = "VERIFICADA" if ok and not rel["motivos"] else "INSUFICIENTE"
        out[base] = rel
    return out


def textos(rel):
    """(publico, privado). O publico nao tem quantidades."""
    pub, priv = [], []
    for base, r in sorted(rel.items()):
        pub.append(f"{base}: {r['classe']}" + (f" — {'; '.join(r['motivos'])}" if r.get("motivos") else ""))
        p = r.get("privado") or {}
        stops = "; ".join(f"{s['lado']} disparo {s['disparo']} qtd {'tudo' if s['fecha_tudo'] else s['quantidade']}"
                          for s in p.get("stops") or []) or "nenhum"
        priv.append(f"{'✅' if r['classe'] == 'VERIFICADA' else '🚨'} OKX {base}: {r['classe']} | {r.get('lado', '?')} "
                    f"qtd {p.get('quantidade', '?')} a {p.get('preco_medio', '?')} | stops: {stops}"
                    + (f" | {'; '.join(r['motivos'])}" if r.get("motivos") else ""))
    return pub, priv


def main(argv):
    import okx_exec as E                                  # so para a assinatura dos pedidos; aqui so se faz GET

    def get(path):
        return E.privado("GET", path)
    if not all(E._chaves()):
        print("NAO VERIFICADA: chaves da OKX indisponiveis neste ambiente"); return 0
    st = json.load(open(argv[0])) if argv and os.path.exists(argv[0]) else {}
    rel = verificar(((st.get("real") or {}).get("ops")) or {}, get)
    pub, priv = textos(rel)
    print("\n".join(pub))
    if "--sem-telegram" not in argv:
        from engine import alerts
        alerta = any(r.get("classe") != "VERIFICADA" for r in rel.values())
        alerts.send(("🚨 ALERTA PRIORITÁRIO — proteção das posições OKX\n" if alerta else
                     "🛡️ Verificação da proteção das posições OKX\n") + "\n".join(priv)
                    + ("\nNada foi alterado. A decisão é tua." if alerta else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
