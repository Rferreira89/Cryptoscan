"""Troca automatica do filtro de producao (Rui, 21/10: "a troca tem de ser
feita automaticamente de quem obtiver melhores resultados").

Regra fixada antes de haver resultados (nao se afina depois de os ver):
- Uma vez por dia regista quem cada filtro (atual e novo) aprova na fase do
  mercado desse dia.
- Mede para a frente: as operacoes do ringue de 1 ano de cada lutador aprovado,
  com entrada nos 7 dias seguintes ao registo (sinais que a aprovacao ainda nao
  tinha visto). Cada operacao conta uma vez.
- Ao fim de pelo menos MIN_DIAS dias de registo, com pelo menos MIN_OPS
  operacoes medidas em cada filtro: o filtro com o R medio para a frente mais
  alto passa a decidir, se for melhor por mais de MARGEM_R e acima de zero.
  Se o filtro novo nao aprovar ninguem, nao ha medicao e fica o atual.
- A troca pode voltar para tras pela mesma regra. Cada troca e avisada no
  Telegram. So muda QUEM e campeao; o risco, a alavancagem e o nucleo ficam.
"""
DIA = 86400
MIN_DIAS, MIN_OPS, MARGEM_R, HORIZONTE = 21, 20, 0.05, 7 * DIA


def registar(state, rel, fase, now):
    """Guarda (uma vez por dia) quem cada filtro aprova na fase atual."""
    tf = state.setdefault("troca_filtro", {"ativo": "atual", "desde": int(now), "dias": {}})
    if not fase or not rel or not rel.get("fases") or not (rel.get("acaso") or {}):
        return tf                               # sem ronda do ringue com o filtro novo: nada a registar
    d = str(int(now) // DIA)
    if d not in tf["dias"]:
        x = (rel.get("fases") or {}).get(fase) or {}
        tf["dias"][d] = {"fase": fase, "atual": list(x.get("atual") or []), "novo": list(x.get("novo") or [])}
        for k in sorted(tf["dias"], key=int)[:-120]:
            del tf["dias"][k]
    return tf


def medir(state, now):
    """{filtro: {n, r}}: R para a frente de quem cada filtro aprovou."""
    tf = state.get("troca_filtro") or {}
    lut = (((state.get("arena") or {}).get("longo") or {}).get("lutadores")) or {}
    out = {}
    for filtro in ("atual", "novo"):
        vistos, rs = set(), []
        for d, reg in (tf.get("dias") or {}).items():
            t0 = int(d) * DIA + DIA                   # a partir do fim do dia do registo
            for k in reg.get(filtro) or []:
                for t, r in (lut.get(k) or {}).get("recentes") or []:
                    if t0 <= t < t0 + HORIZONTE and t <= now and (k, t) not in vistos:
                        vistos.add((k, t))
                        rs.append(r)
        out[filtro] = {"n": len(rs), "r": round(sum(rs) / len(rs), 3) if rs else None}
    return out


def decidir(state, now):
    """Aplica a regra; devolve a mensagem de troca ou None."""
    tf = state.get("troca_filtro")
    if not tf or len(tf.get("dias") or {}) < MIN_DIAS:
        return None
    m = medir(state, now)
    tf["medicao"] = dict(m, t=int(now))
    a, n = m["atual"], m["novo"]
    if a["n"] < MIN_OPS or n["n"] < MIN_OPS:
        return None
    ativo = tf.get("ativo", "atual")
    melhor = "novo" if n["r"] > a["r"] + MARGEM_R and n["r"] > 0 else \
        "atual" if a["r"] > n["r"] + MARGEM_R and a["r"] > 0 else ativo
    if melhor == ativo:
        return None
    tf.update(ativo=melhor, desde=int(now))
    tf.setdefault("historico", []).append({"t": int(now), "ativo": melhor, "atual": a, "novo": n})
    nome = {"novo": "o filtro novo", "atual": "o filtro anterior"}[melhor]
    return (f"🔁 <b>Troca automática do filtro</b>: passa a decidir {nome}. Para a frente, "
            f"o filtro novo deu {n['r']:+.2f}R em {n['n']} operações e o anterior {a['r']:+.2f}R em {a['n']}. "
            "Só muda quem é campeão; o risco e o núcleo ficam iguais.")
