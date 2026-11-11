"""Filtro de rentabilidade liquida PRE-ENTRADA (auditoria de 2026-11-11; so
investigacao, sem ligacao a execucao real; pre-registado no registo central
como FILTRO_RENTABILIDADE_F1 antes de qualquer resultado).

Pergunta que responde, no instante de cada entrada:
  "a vantagem que esta estrategia JA demonstrou, descontada a incerteza, paga
   o custo DESTA operacao com uma margem?"

  vantagem  = R medio por ACONTECIMENTO das operacoes da mesma estrategia ja
              FECHADAS antes da entrada (operacoes da mesma vela de 4H contam
              como um acontecimento), ja liquido da comissao de 0,25% e do
              deslize de 0,1% por lado que o simulador aplica;
  encolhida para zero com uma priori de N0 acontecimentos (estimativa
              cautelosa com pouca historia);
  incerteza = desvio-padrao por acontecimento (combinado com o da priori,
              SD0 = 1R, para que poucos acontecimentos iguais nao parecam
              certeza) / raiz(k + N0);
  custo extra desta operacao = (spread real da moeda - deslize ja simulado)
              / distancia do stop, mais o juro do short por dia de detencao
              prevista (so shorts);
  aceita se  limite_inferior(vantagem) - custo_extra > MARGEM
             e ha pelo menos MIN_EVENTOS acontecimentos.

Sem historia suficiente a resposta e NAO (inconclusivo nao e vantagem).
Nunca relaxa um filtro existente: so pode tirar operacoes, nunca acrescentar.

Uso:
  python -m tools.filtro_rentabilidade <ops.json[.gz]> [...] --liquidez liquidez.json --saida res.json
  (as operacoes vem de tools/filtro_operacoes.py; as de 11/11 estao em
   backtest/rentabilidade/operacoes_lutadores_2026-11-11.json.gz)
"""
import json
import math
import statistics as st
import sys

DAY, H4 = 86400, 4 * 3600
CORTE = 1778198400                  # 2026-05-08: inicio da reserva (so para separar o relatorio)
PARAMS = {"N0": 10, "Z": 1.645, "MIN_EVENTOS": 20, "MARGEM": 0.05, "SLIP_SIM_IDA_VOLTA": 0.2,
          "JURO_SHORT_DIA": 0.05, "SD0": 1.0, "SPREAD_OMISSAO": 0.1444, "DETENCAO_SHORT_DIAS": 3.0}


def spreads(liquidez):
    """Spread mediano (%, ida e volta = spread inteiro) por moeda, de liquidez.json."""
    acc = {}
    for _, m in ((liquidez or {}).get("dias") or {}).items():
        for a, v in m.items():
            if isinstance(v, list) and len(v) > 1 and v[1] is not None:
                acc.setdefault(a, []).append(float(v[1]))
    return {a: st.median(v) for a, v in acc.items() if v}


def custo_extra_r(op, spread_map, p=PARAMS):
    """Custo em R que o simulador nao conta: spread acima do deslize simulado
    e, nos shorts, o juro do emprestimo."""
    sp = spread_map.get(op["asset"], p["SPREAD_OMISSAO"])
    stop = max(1e-6, float(op["stop_pct"]))
    extra = max(0.0, sp - p["SLIP_SIM_IDA_VOLTA"]) / stop
    if op.get("lado") == "SHORT":
        dias = (op["t_fim"] - op["t"]) / DAY if op.get("t_fim") else p["DETENCAO_SHORT_DIAS"]
        extra += p["JURO_SHORT_DIA"] * dias / stop
    return extra


def custo_total_pct(asset, spread_map, fee_lado=0.25, p=PARAMS):
    """Custo de ida e volta em % do preco: 2 comissoes + spread real."""
    return 2 * fee_lado + spread_map.get(asset, p["SPREAD_OMISSAO"])


class Estimador:
    """Vantagem de uma estrategia com operacoes fechadas ate um instante."""

    def __init__(self, p=PARAMS):
        self.p = p
        self.pend = []           # operacoes ainda nao fechadas (t_fim, op)
        self.ev = {}             # vela de entrada -> [R]

    def juntar(self, op):
        self.pend.append(op)

    def avancar(self, t):
        """Passa a contar as operacoes com fecho <= t (nunca as outras)."""
        ficam = []
        for op in self.pend:
            if op["t_fim"] <= t:
                self.ev.setdefault(op["t"] // H4, []).append(op["r"])
            else:
                ficam.append(op)
        self.pend = ficam

    def estimativa(self):
        medias = [sum(v) / len(v) for v in self.ev.values()]
        k = len(medias)
        n0 = self.p["N0"]
        mu = sum(medias) / (k + n0) if k else 0.0
        s2 = st.variance(medias) if k >= 2 else 0.0
        sd = math.sqrt((k * s2 + n0 * self.p["SD0"] ** 2) / (k + n0))   # a priori tambem tem incerteza
        se = sd / math.sqrt(k + n0)
        return {"k": k, "mu": mu, "se": se, "lb": mu - self.p["Z"] * se,
                "media_crua": (sum(medias) / k) if k else None}


def decidir(est, extra, modo="F1", p=PARAMS):
    base = est["lb"] if modo == "F1" else est["mu"]
    liquido = base - extra
    if est["k"] < p["MIN_EVENTOS"]:
        return False, "historia insuficiente", liquido
    if liquido <= p["MARGEM"]:
        return False, "vantagem nao paga o custo com margem", liquido
    return True, "aceite", liquido


def avaliar(ops_por_estrategia, spread_map, modo="F1", p=PARAMS):
    """Percorre todas as operacoes por ordem de entrada. Cada decisao so ve
    operacoes da mesma estrategia ja fechadas. Devolve a lista de decisoes."""
    todas = sorted(((k, op) for k, ops in ops_por_estrategia.items() for op in ops), key=lambda x: (x[1]["t"], x[0]))
    est = {k: Estimador(p) for k in ops_por_estrategia}
    out = []
    for k, op in todas:
        e = est[k]
        e.avancar(op["t"])
        s = e.estimativa()
        extra = custo_extra_r(op, spread_map, p)
        ok, motivo, liq = decidir(s, extra, modo, p)
        out.append({"estrategia": k, "asset": op["asset"], "lado": op.get("lado", "LONG"), "t": op["t"],
                    "t_fim": op["t_fim"], "r_bruto": op["r"], "custo_extra_r": round(extra, 4),
                    "r_liquido": round(op["r"] - extra, 4), "aceite": ok, "motivo": motivo,
                    "lb": round(s["lb"], 4), "k": s["k"], "liquido_previsto": round(liq, 4)})
        e.juntar(op)
    return out


def queda_maxima(rows):
    """Maior queda do R acumulado (por ordem de fecho), em R."""
    eq = pico = 0.0
    q = 0.0
    for r in sorted(rows, key=lambda x: x["t_fim"]):
        eq += r["r_liquido"]
        pico = max(pico, eq)
        q = min(q, eq - pico)
    return round(q, 3)


def metricas(rows):
    if not rows:
        return {"n": 0, "acontecimentos": 0}
    ev = {}
    for r in rows:
        ev.setdefault((r["estrategia"], r["t"] // H4), []).append(r["r_liquido"])
    em = [sum(v) / len(v) for v in ev.values()]
    out = {"n": len(rows), "acontecimentos": len(ev),
           "r_bruto_medio": round(sum(r["r_bruto"] for r in rows) / len(rows), 4),
           "r_liquido_medio": round(sum(r["r_liquido"] for r in rows) / len(rows), 4),
           "r_liquido_total": round(sum(r["r_liquido"] for r in rows), 2),
           "r_por_acontecimento": round(sum(em) / len(em), 4),
           "acerto": round(sum(1 for r in rows if r["r_liquido"] > 0) / len(rows), 3),
           "queda_maxima_r": queda_maxima(rows)}
    if len(em) >= 2:
        se = st.stdev(em) / math.sqrt(len(em))
        out["ic90_por_acontecimento"] = [round(out["r_por_acontecimento"] - 1.645 * se, 4),
                                         round(out["r_por_acontecimento"] + 1.645 * se, 4)]
    return out


def comparar(decisoes):
    """Sem filtro, aceites, rejeitadas e oportunidades perdidas, no total e
    separado em exploracao (antes do CORTE) e reserva (depois)."""
    def bloco(rs):
        ac = [r for r in rs if r["aceite"]]
        rj = [r for r in rs if not r["aceite"]]
        perdidas = [r for r in rj if r["r_liquido"] > 0]
        return {"sem_filtro": metricas(rs), "aceites": metricas(ac), "rejeitadas": metricas(rj),
                "oportunidades_perdidas": {"n": len(perdidas),
                                           "r_total": round(sum(r["r_liquido"] for r in perdidas), 2)},
                "r_evitado": round(-sum(r["r_liquido"] for r in rj), 2)}
    return {"total": bloco(decisoes),
            "exploracao": bloco([r for r in decisoes if r["t"] < CORTE]),
            "reserva": bloco([r for r in decisoes if r["t"] >= CORTE])}


def por_estrategia(ops_por_estrategia, spread_map, p=PARAMS):
    """Expectativa liquida de cada estrategia em toda a historia, com IC90
    por acontecimento: POSITIVA (IC todo > 0), NEGATIVA (IC todo < 0) ou
    INCONCLUSIVA; e a decisao que o filtro tomaria HOJE para uma operacao
    tipica (stop e spread medianos da propria estrategia)."""
    out = {}
    for k, ops in ops_por_estrategia.items():
        rows = [{"estrategia": k, "t": o["t"], "t_fim": o["t_fim"], "r_bruto": o["r"],
                 "r_liquido": o["r"] - custo_extra_r(o, spread_map, p)} for o in ops]
        m = metricas(rows)
        ic = m.get("ic90_por_acontecimento")
        m["veredicto"] = ("POSITIVA" if ic and ic[0] > 0 else "NEGATIVA" if ic and ic[1] < 0 else "INCONCLUSIVA")
        e = Estimador(p)
        for o in ops:
            e.juntar(o)
        e.avancar(10 ** 12)
        s = e.estimativa()
        tip = {"asset": "?", "stop_pct": st.median([o["stop_pct"] for o in ops]) if ops else 5.0,
               "lado": ops[0].get("lado", "LONG") if ops else "LONG", "t": 0,
               "t_fim": int(st.median([o["t_fim"] - o["t"] for o in ops])) if ops else 3 * DAY}
        ok, motivo, liq = decidir(s, custo_extra_r(tip, spread_map, p), "F1", p)
        m["hoje"] = {"aceita": ok, "motivo": motivo, "lb": round(s["lb"], 4), "acontecimentos": s["k"],
                     "stop_mediano_pct": round(tip["stop_pct"], 2)}
        out[k] = m
    return out


def carregar(caminhos):
    ops, meta = {}, {}
    import gzip
    for c in caminhos:
        d = json.load(gzip.open(c, "rt", encoding="utf-8") if c.endswith(".gz") else open(c, encoding="utf-8"))
        ops.update(d["ops"])
        meta = {"inicio": d.get("inicio"), "fim": d.get("fim"), "moedas": d.get("moedas")}
    return ops, meta


def main(argv):
    liq = argv[argv.index("--liquidez") + 1]
    dest = argv[argv.index("--saida") + 1] if "--saida" in argv else None
    fontes = [a for a in argv if a.endswith((".json", ".json.gz")) and a not in (liq, dest)]
    ops, meta = carregar(fontes)
    sp = spreads(json.load(open(liq, encoding="utf-8")))
    res = {"params": PARAMS, "meta": meta, "por_estrategia": por_estrategia(ops, sp)}
    for modo in ("F1", "F1p"):
        d = avaliar(ops, sp, modo)
        res[modo] = comparar(d)
        res[modo]["por_estrategia_aceites"] = {k: sum(1 for r in d if r["estrategia"] == k and r["aceite"])
                                               for k in ops}
    if dest:
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    r = main(sys.argv[1:])
    print(json.dumps({k: v for k, v in r.items() if k != "por_estrategia"}, ensure_ascii=False, indent=1)[:6000])
