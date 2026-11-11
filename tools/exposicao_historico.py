"""(11/11, auditoria P7) Historico agregado do mapa diario de exposicao, publico e sem dados privados.

Antes: o mapa so ia para o Telegram (sem historico), e o ciclo do scan saltava o envio diario sempre que ja houvesse
QUALQUER execucao no dia, incluindo uma manual (10/11: a manual das 06:23 fez saltar a das 07:13).

Agora:
  - uma linha por dia e por tipo (diario | manual) em historico_exposicao.jsonl (ramo `exposicao`): so contagens,
    LONG/SHORT, apostas independentes, numero de conflitos e dados em falta. Correr outra vez no mesmo dia SUBSTITUI
    a linha desse dia e tipo (idempotente), nunca duplica;
  - o Telegram diario so e enviado uma vez por dia (campo `enviado` da linha diaria); uma execucao manual envia com a
    marca "(execucao manual)" e nao conta como a diaria;
  - `ja_houve_diario` e o que o ciclo do scan usa para decidir se lanca o mapa: so as execucoes diarias contam.
Uso:
  python3 tools/exposicao_historico.py registar <mapa.json> <historico.jsonl> <diario|manual>
  python3 tools/exposicao_historico.py ja-enviado <historico.jsonl> <AAAA-MM-DD>     (sai 0 se ja foi enviado)"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def entrada(mapa_, dia, tipo):
    blocos = {}
    for k, b in (mapa_.get("blocos") or {}).items():
        c = b.get("conflitos") or {}
        blocos[k] = {"n": b.get("n", 0), "long": b.get("long", 0), "short": b.get("short", 0),
                     "apostas_efetivas": b.get("apostas_efetivas"),
                     "grupos_correlacionados": len(b.get("grupos_correlacionados") or []),
                     "maior_grupo": max([g.get("n", 0) for g in b.get("grupos_correlacionados") or []] or [0]),
                     "conflitos_mesmo_ativo_oposto": len(c.get("mesmo_ativo_oposto") or {}),
                     "conflitos_grupo_oposto": len(c.get("grupo_oposto") or []),
                     "conflitos_mesma_exposicao": len(c.get("mesma_exposicao") or {}),
                     "sem_precos": len(b.get("sem_precos") or [])}
    return {"dia": dia, "tipo": tipo, "t": int(mapa_.get("t") or time.time()), "blocos": blocos,
            "dados_em_falta": list(mapa_.get("dados_em_falta") or []), "enviado": False}


def ler(caminho):
    out = []
    if os.path.exists(caminho):
        for ln in open(caminho):
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue                             # linha partida: ignorada, nunca apaga as outras
    return out


def atualizar(hist, nova):
    """Substitui a linha do mesmo dia e tipo (mantendo `enviado` ja registado); acrescenta se nao houver."""
    out, feito = [], False
    for h in hist:
        if h.get("dia") == nova["dia"] and h.get("tipo") == nova["tipo"]:
            nova = {**nova, "enviado": bool(h.get("enviado")) or nova.get("enviado", False)}
            out.append(nova)
            feito = True
        else:
            out.append(h)
    if not feito:
        out.append(nova)
    return sorted(out, key=lambda h: (h.get("dia") or "", h.get("tipo") or ""))


def ja_houve_diario(hist, dia):
    return any(h.get("dia") == dia and h.get("tipo") == "diario" and h.get("enviado") for h in hist)


def marcar_enviado(hist, dia, tipo):
    for h in hist:
        if h.get("dia") == dia and h.get("tipo") == tipo:
            h["enviado"] = True
    return hist


def gravar(caminho, hist):
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        for h in hist:
            f.write(json.dumps(h, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, caminho)


def sem_privados(hist):
    from engine.contabilidade import sem_dinheiro
    return sem_dinheiro(hist)


if __name__ == "__main__":
    acao = sys.argv[1]
    if acao == "registar":
        mapa_ = json.load(open(sys.argv[2]))
        caminho, tipo = sys.argv[3], sys.argv[4]
        dia = time.strftime("%Y-%m-%d", time.gmtime(mapa_.get("t") or time.time()))
        hist = atualizar(ler(caminho), entrada(mapa_, dia, tipo))
        maus = sem_privados(hist)
        if maus:
            sys.exit(f"historico com campos privados: {maus[:3]}")
        gravar(caminho, hist)
        print(f"historico: {len(hist)} linhas ({dia} {tipo})")
    elif acao == "ja-enviado":
        sys.exit(0 if ja_houve_diario(ler(sys.argv[2]), sys.argv[3]) else 1)
    elif acao == "enviado":
        caminho, dia, tipo = sys.argv[2], sys.argv[3], sys.argv[4]
        gravar(caminho, marcar_enviado(ler(caminho), dia, tipo))
