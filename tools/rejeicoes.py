"""(10/11, ordem executiva do Rui) Analise de REJEICOES: oportunidades detetadas que nao chegaram a dinheiro real,
porque, e o que teriam dado.

So leitura das copias publicas (state.json, okx.json, okx_tfshort.json, okx_tfshort_sombra.json, kronos_sombra.json).
Sem rede, sem chaves, sem ordens.

Cada rejeicao e classificada:
  operacional  - a ordem nao podia existir (sem contrato na corretora, abaixo do minimo do contrato com o capital atual,
                 sem livro de ordens, ordem recusada pela corretora)
  estatistico  - o sinal esta fora do que a evidencia suporta (fora do universo validado, panico isolado, estrategia
                 suspensa ou em papel por falta de prova)
  risco        - um limite de risco fez o seu trabalho (maximo de posicoes, teto de risco/exposicao)

O resultado so e mostrado quando a MESMA oportunidade foi seguida em papel ou em sombra pelas regras da estrategia
(sem look-ahead: o papel abre e fecha com os dados da altura). Sem par em papel, o resultado fica "desconhecido".
Veredito por motivo (so com resultados conhecidos):
  - "bloqueio justificado"   se o intervalo de 90% da media de R fica todo <= 0
  - "rever: perdeu-se R"     se o intervalo fica todo > 0
  - "inconclusivo"           caso contrario ou com menos de 10 resultados
Uso: python3 tools/rejeicoes.py <pasta com as copias publicas>"""
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CLASSE = {
    # OKX executor (prefixos em real.avisados)
    "p": ("H40 suspensa do dinheiro real (decisao)", "estatistico"),
    "i": ("H40 panico isolado (so_mercado)", "estatistico"),
    "x": ("sem X-Perp negociavel na conta", "operacional"),
    "m": ("H40 no maximo de posicoes", "risco"),
    "r": ("teto de risco aberto", "risco"),
    # TF-SHORT papel/sombra, Kronos
    "fora_do_universo_validado": ("fora do universo validado", "estatistico"),
    "abaixo_minimo": ("abaixo do minimo do contrato (capital)", "operacional"),
    "abaixo_minimo_do_contrato": ("abaixo do minimo do contrato (capital)", "operacional"),
    "sem_instrumento_okx_eea": ("sem X-Perp negociavel", "operacional"),
    "sem_livro_de_ordens": ("sem livro de ordens", "operacional"),
    "livro_sem_profundidade": ("livro sem profundidade", "operacional"),
    "maximo_posicoes": ("maximo de posicoes", "risco"),
    "exposicao_bruta": ("teto de exposicao bruta", "risco"),
    "alavancagem_total": ("teto de alavancagem total", "risco"),
    "ja_aberta": ("ja havia posicao no ativo", "risco"),
    # Bybit
    "h45_suspensa": ("H45 suspensa do dinheiro real (decisao)", "estatistico"),
    "bybit_recusada": ("ordem recusada pela Bybit", "operacional"),
}


def _carregar(pasta, nome):
    p = os.path.join(pasta, nome)
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    return d.get("estado", d) if isinstance(d, dict) and "soma" in d else d


def rej(fonte, estrategia, ativo, t, motivo, R=None):
    nome, classe = CLASSE.get(motivo, (motivo, "desconhecida"))
    return {"fonte": fonte, "estrategia": estrategia, "ativo": ativo, "t": t, "motivo": nome, "classe": classe,
            "R": R}


def da_okx(okx):
    """real.avisados ('p:BASE:t_sig', ...) cruzado com o papel da H40 (fechadas: asset, t_sig, r)."""
    if not okx:
        return []
    papel = {(f.get("asset"), int(f.get("t_sig") or 0)): f.get("r") for f in okx.get("fechadas") or []}
    out, vistos = [], set()
    for a in ((okx.get("real") or {}).get("avisados") or []):
        partes = a.split(":")
        if len(partes) != 3 or partes[0] not in CLASSE:
            continue
        pre, base, t = partes[0], partes[1], int(float(partes[2]))
        if (pre, base, t) in vistos:
            continue
        vistos.add((pre, base, t))
        out.append(rej("okx", "H40", base, t, pre, papel.get((base, t))))
    return out


def do_tfshort(tfs):
    """Paper TF-SHORT: sinais ignorados pela conta de 20 USD; o resultado vem do livro de sinais quando fechar."""
    if not tfs:
        return []
    fech = {}
    for f in ((tfs.get("sinais") or {}).get("fechadas") or []):
        fech[(f.get("moeda") or f.get("asset"), int(f.get("t") or f.get("t_sig") or 0))] = f.get("R", f.get("r"))
    return [rej("okx", "TF-SHORT papel", x.get("moeda"), x.get("t"), x.get("motivo"),
                fech.get((x.get("moeda"), int(x.get("t") or 0))))
            for x in ((tfs.get("conta") or {}).get("ignoradas") or [])]


def das_sombras(sombra, nome):
    if not sombra:
        return []
    return [rej("okx", nome, x.get("moeda"), x.get("t") or x.get("dia"), x.get("motivo"), None)
            for x in sombra.get("nao_executaveis") or []]


def da_bybit(state):
    """H45 (panico Bybit) suspensa: o papel segue os sinais; ordens reais recusadas pela Bybit."""
    if not state:
        return []
    pp = state.get("papel_panico") or {}
    out = [rej("bybit", "H45", f.get("asset"), f.get("t_sig"), "h45_suspensa", f.get("r")) for f in pp.get("fechadas") or []]
    for k, v in (pp.get("real") or {}).items():
        if v.get("estado") == "recusada":
            out.append(rej("bybit", "H45", v.get("asset"), v.get("t_sig"), "bybit_recusada", None))
    return out


def _ic90(R, grupos, n=2000):
    """Mesma reamostragem por dia de sinal do vigia de decaimento (sinais do mesmo dia nao sao independentes)."""
    from engine.decaimento import _ic90 as ic
    return ic(R, n=n, grupos=grupos)


def resumo(rejs):
    """Por (estrategia, motivo): n, quantos com resultado, R medio, PF, intervalo de 90% e veredito."""
    g = {}
    for r in rejs:
        g.setdefault((r["fonte"], r["estrategia"], r["motivo"], r["classe"]), []).append(r)
    out = []
    for (fonte, est, mot, cl), xs in g.items():
        com = [x for x in xs if x["R"] is not None]
        R = [x["R"] for x in com]
        dias = [int((x["t"] or 0) // 86400) for x in com]
        linha = {"fonte": fonte, "estrategia": est, "motivo": mot, "classe": cl, "n": len(xs), "com_resultado": len(R)}
        if R:
            gp, gl = sum(r for r in R if r > 0), -sum(r for r in R if r < 0)
            linha.update(media_R=round(st.mean(R), 3), pf=round(gp / gl, 2) if gl else None)
            if len(R) >= 10 and len(set(dias)) >= 5:
                lo, hi = _ic90(R, dias)
                linha["ic90"] = [round(lo, 3), round(hi, 3)]
                linha["veredito"] = ("bloqueio justificado" if hi <= 0 else "rever: perdeu-se R" if lo > 0 else "inconclusivo")
            else:
                linha["veredito"] = "inconclusivo (menos de 10 resultados ou de 5 dias independentes)"
        else:
            linha["veredito"] = "resultado desconhecido (sem par em papel/sombra)"
        out.append(linha)
    return sorted(out, key=lambda x: -x["n"])


def tudo(pasta):
    st_ = _carregar(pasta, "state.json")
    rejs = (da_okx(_carregar(pasta, "okx.json")) + do_tfshort(_carregar(pasta, "okx_tfshort.json")) +
            das_sombras(_carregar(pasta, "okx_tfshort_sombra.json"), "TF-SHORT sombra") +
            das_sombras(_carregar(pasta, "kronos_sombra.json"), "Kronos sombra") + da_bybit(st_))
    return rejs, resumo(rejs)


def texto(res):
    L = ["Rejeicoes (oportunidades que nao chegaram a dinheiro real)", ""]
    por_classe = {}
    for r in res:
        por_classe[r["classe"]] = por_classe.get(r["classe"], 0) + r["n"]
    L.append("Por classe: " + ", ".join(f"{k} {v}" for k, v in sorted(por_classe.items(), key=lambda x: -x[1])))
    L.append("")
    for r in res:
        extra = f", R medio {r['media_R']:+.3f}, PF {r.get('pf')}" if "media_R" in r else ""
        ic = f", IC90 {r['ic90']}" if "ic90" in r else ""
        L.append(f"- [{r['classe']}] {r['estrategia']} ({r['fonte']}): {r['motivo']} - {r['n']} "
                 f"(com resultado {r['com_resultado']}{extra}{ic}) -> {r['veredito']}")
    return "\n".join(L)


if __name__ == "__main__":
    _, res = tudo(sys.argv[1])
    print(texto(res))
