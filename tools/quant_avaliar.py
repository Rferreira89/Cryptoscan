"""(10/11, ordem do Rui) Avaliacao quantitativa RETROSPETIVA, so de investigacao: DSR, PBO (CSCV) e vantagem residual
face ao BTC, por estrategia e por AMBIENTE (OKX real, Bybit real, papel, sombra, backtest — nunca somados).
Nao altera estrategias, nao le chaves das corretoras, nao envia nada. Sai em JSON e Markdown, so em R.

Uso: python3 tools/quant_avaliar.py <pasta com as copias publicas> [--estado estado_completo.json] [--btc btc.json]
                                     [--saida resultado.json] [--md resultado.md]
  --btc: [[t, preco], ...] (por defeito, os precos horarios do BTC em derivados.json)."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest.quant import dados as Q, dsr as D, pbo as P, residual as RS  # noqa: E402

ALVO = ["H40", "H45", "H46", "H52", "H53", "H57", "H58", "H59"]


def avaliar(base, btc_pontos=None):
    ops = base["operacoes"]
    btc = RS.SerieBTC(btc_pontos if btc_pontos is not None else base["btc"])
    tent = D.contar_tentativas(base.get("forma"))
    grupos = {}
    for o in ops:
        grupos.setdefault((o["ambiente"], o["estrategia"]), []).append(o)
    linhas = []
    for (amb, est), L in sorted(grupos.items()):
        L = sorted(L, key=lambda o: RS.seg(o.get("t_saida") or 0))
        rs = [o["R"] for o in L]
        d_min = D.dsr(rs, tent["minimo"])
        d_con = D.dsr(rs, tent["conservador"])
        res = RS.analisar(L, btc, "por_operacao")
        ts = [RS.seg(o["t_saida"]) for o in L if o.get("t_saida")]
        linhas.append({"ambiente": amb, "estrategia": est, "n": len(L), "R_medio": sum(rs) / len(rs), "sem_hora": len(L) - len(ts),
                       "desde": RS.dia(min(ts)) if ts else None, "ate": RS.dia(max(ts)) if ts else None,
                       "dsr_minimo": d_min, "dsr_conservador": d_con, "residual": {k: v for k, v in res.items() if k != "movel"} | {"movel": res.get("movel", [])}})
    for h in ALVO:
        if not any(l["estrategia"] == h for l in linhas):
            linhas.append({"ambiente": "—", "estrategia": h, "n": 0, "estado": "sem operacoes fechadas publicadas"})
    # PBO: selecao entre as estrategias da arena (PAPEL), R por dia UTC de fecho
    arena = {}
    for o in ops:
        if o["estrategia"].startswith("ARENA:") and o["t_saida"]:
            arena.setdefault(o["estrategia"][6:], {}).setdefault(RS.dia(o["t_saida"]), 0.0)
            arena[o["estrategia"][6:]][RS.dia(o["t_saida"])] += o["R"]
    if len(arena) >= 2:
        dias, nomes, M = P.matriz_diaria(arena)
        pbo = {"ambiente": "PAPEL (arena)", "dias": len(dias), "desde": dias[0] if dias else None, "ate": dias[-1] if dias else None, "configuracoes": nomes,
               "resultados": [{k: v for k, v in P.cscv(M, s=s, embargo=e, nomes=nomes).items() if k != "lambdas"} for s, e in ((8, 0), (8, 2), (10, 0), (6, 0))]}
        # variancia do Sharpe entre as tentativas reais da arena (para um DSR mais informado)
        srs = [D.sharpe([r[j] for r in M]) for j in range(len(nomes)) if len({r[j] for r in M}) > 1]
        pbo["var_sharpe_entre_configuracoes"] = (sum((x - sum(srs) / len(srs)) ** 2 for x in srs) / (len(srs) - 1)) if len(srs) > 2 else None
    else:
        pbo = {"estado": "insuficiente", "razao": "sem operacoes da arena com hora (precisa do estado completo)"}
    return {"gerado": int(time.time()), "tentativas": tent, "btc": {"pontos": len(btc.t), "desde": RS.dia(btc.t[0]) if btc.t else None, "ate": RS.dia(btc.t[-1]) if btc.t else None},
            "estrategias": linhas, "pbo_arena": pbo, "notas": base["notas"]}


def _f(x, d=3):
    return "–" if x is None else f"{x:+.{d}f}" if isinstance(x, (int, float)) else str(x)


def markdown(r):
    L = [f"# Avaliacao quantitativa retrospetiva ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(r['gerado']))})", "",
         "So investigacao. Ambientes separados; nada aqui altera estrategias ou risco. Valores em R.", "",
         f"Tentativas contadas: minimo {r['tentativas']['minimo']}, conservador {r['tentativas']['conservador']} ({r['tentativas']['partes']}).",
         f"BTC: {r['btc']['pontos']} pontos, {r['btc']['desde']} a {r['btc']['ate']}.", "",
         "| Ambiente | Estrategia | n | R medio | DSR (N min) | DSR (N cons.) | beta BTC | alfa (p) | Veredito residual |", "|---|---|---|---|---|---|---|---|---|"]
    for l in r["estrategias"]:
        if not l.get("n"):
            L.append(f"| — | {l['estrategia']} | 0 | – | – | – | – | – | {l.get('estado')} |"); continue
        dm, dc, rs = l["dsr_minimo"], l["dsr_conservador"], l["residual"]
        dtx = lambda d: f"{d['dsr']:.3f}" if d["estado"] == "calculado" else f"insuf. ({d['t']})"
        L.append(f"| {l['ambiente']} | {l['estrategia']} | {l['n']} | {_f(l['R_medio'])} | {dtx(dm)} | {dtx(dc)} | "
                 + (f"{_f(rs['beta'], 2)} | {_f(rs['alfa'])} ({rs['p_alfa']:.2f}) | {rs['veredito']} |" if rs["estado"] == "calculado" else f"– | – | {rs['razao']} |"))
    p = r["pbo_arena"]
    L += ["", "## PBO (CSCV) — selecao entre estrategias da arena (PAPEL)"]
    if p.get("resultados"):
        L.append(f"{len(p['configuracoes'])} configuracoes, {p['dias']} dias ({p['desde']} a {p['ate']}).")
        for x in p["resultados"]:
            L.append(f"- S={x['s']}, embargo={x['embargo']}: " + (f"PBO {x['pbo']:.2f}, prob. perda fora {x['prob_perda_fora']:.2f}, degradacao {_f(x['degradacao_inclinacao'], 2)} — {x['veredito']}"
                                                                  if x["estado"] == "calculado" else f"insuficiente: {x['razao']}"))
    else:
        L.append(f"Insuficiente: {p.get('razao')}")
    L += ["", "## Notas"] + [f"- {n}" for n in r["notas"]]
    return "\n".join(L) + "\n"


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("pasta"); a.add_argument("--estado"); a.add_argument("--btc"); a.add_argument("--saida"); a.add_argument("--md")
    x = a.parse_args(argv)
    est = json.load(open(x.estado)) if x.estado and os.path.exists(x.estado) else None
    base = Q.carregar(x.pasta, est)
    btc = json.load(open(x.btc)) if x.btc else None
    r = avaliar(base, btc)
    if x.saida:
        json.dump(r, open(x.saida, "w"), indent=1, default=str)
    md = markdown(r)
    if x.md:
        open(x.md, "w").write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
