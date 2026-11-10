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
    # PBO por familia de configuracoes que correram sobre os mesmos dados (R por dia UTC de fecho, periodo = uniao)
    familias = {"PAPEL (arena)": lambda o: o["estrategia"].startswith("ARENA:"),
                "BACKTEST H40 (todos vs so panico do mercado)": lambda o: o["ambiente"] == "BACKTEST" and o["estrategia"].startswith("H40"),
                "BACKTEST H46 (RSI<30 vs RSI<35)": lambda o: o["ambiente"] == "BACKTEST" and o["estrategia"].startswith("H46")}
    pbo = {}
    for fam, f in familias.items():
        series = {}
        for o in ops:
            if f(o) and o.get("t_saida"):
                d = RS.dia(o["t_saida"]); series.setdefault(o["estrategia"], {}).setdefault(d, 0.0); series[o["estrategia"]][d] += o["R"]
        if len(series) < 2:
            pbo[fam] = {"estado": "insuficiente", "razao": f"{len(series)} configuracao(oes) com operacoes com hora"}; continue
        dias, nomes, M = P.matriz_diaria(series, periodo="uniao")
        srs = [D.sharpe([r[j] for r in M]) for j in range(len(nomes)) if len({r[j] for r in M}) > 1]
        pbo[fam] = {"dias": len(dias), "desde": dias[0] if dias else None, "ate": dias[-1] if dias else None, "configuracoes": nomes,
                    "var_sharpe_entre_configuracoes": (sum((x - sum(srs) / len(srs)) ** 2 for x in srs) / (len(srs) - 1)) if len(srs) > 2 else None,
                    "resultados": [{k: v for k, v in P.cscv(M, s=s_, embargo=e, nomes=nomes).items() if k != "lambdas"} for s_, e in ((8, 0), (8, 3), (10, 0), (16, 0))]}
    return {"gerado": int(time.time()), "tentativas": tent, "btc": {"pontos": len(btc.t), "desde": RS.dia(btc.t[0]) if btc.t else None, "ate": RS.dia(btc.t[-1]) if btc.t else None},
            "estrategias": linhas, "pbo": pbo, "notas": base["notas"]}


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
    L += ["", "## PBO (CSCV) — configuracoes avaliadas sobre os mesmos dados"]
    for fam, p in r["pbo"].items():
        if not p.get("resultados"):
            L.append(f"- {fam}: insuficiente ({p.get('razao')})"); continue
        L.append(f"- {fam}: {len(p['configuracoes'])} configuracoes, {p['dias']} dias ({p['desde']} a {p['ate']})")
        for x in p["resultados"]:
            L.append(f"  - S={x['s']}, embargo={x['embargo']}: " + (f"PBO {x['pbo']:.2f}, prob. perda fora {x['prob_perda_fora']:.2f}, degradacao {_f(x['degradacao_inclinacao'], 2)}, escolhida {next(iter(x['escolhidas']))} — {x['veredito']}"
                                                                    if x["estado"] == "calculado" else f"insuficiente: {x['razao']}"))
    L += ["", "## Notas"] + [f"- {n}" for n in r["notas"]]
    return "\n".join(L) + "\n"


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("pasta"); a.add_argument("--estado"); a.add_argument("--btc"); a.add_argument("--saida"); a.add_argument("--md")
    a.add_argument("--backtests", help="saida de tools/quant_backtests.py (operacoes de BACKTEST e BTC de 4H)")
    x = a.parse_args(argv)
    est = json.load(open(x.estado)) if x.estado and os.path.exists(x.estado) else None
    base = Q.carregar(x.pasta, est)
    btc = json.load(open(x.btc)) if x.btc else None
    if x.backtests:
        bt = json.load(open(x.backtests))
        base["operacoes"] += bt["operacoes"]
        btc = (btc if btc is not None else base["btc"]) + bt["btc_4h"]
        base["notas"] = [n for n in base["notas"] if not n.startswith("BACKTEST")] + ["BACKTEST: H40, H45 e H46 a partir dos estudos registados (tools/quant_backtests.py), velas de 4H do ramo history"]
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
