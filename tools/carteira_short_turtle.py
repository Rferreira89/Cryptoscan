"""(12/11, ordem do Rui 09:06) Carteira do SHORT_TURTLE com concorrencia: 1 vs 2 (vs 3) posicoes simultaneas com
risco AGREGADO aberto <= teto da conta, sobre as operacoes historicas reais da estrategia (entrada, fim, stop, R).

Dimensionamento como na conta (engine/risk.sizing + piloto): posicao = risco normal (alvo_pct, 0,5% do capital) / stop;
abaixo da ordem minima sobe ate a ordem minima so se o risco real ficar <= teto por operacao. Com capital pequeno quase
tudo fica na ordem minima: o risco de cada operacao e o que a ordem minima impoe (ordem * stop / capital), nunca o teto
inteiro. Uma posicao nova so entra se risco_aberto + risco_nova <= teto AGREGADO (5%). Nao encurta stops.

Custos: comissao 0,25%/lado (ja no R da operacao), deslize extra no stop (gap) sobre o valor da posicao, juro de
emprestimo diario sobre a posicao durante a operacao. Capital composto.
Concorrencia: as operacoes sobrepostas no tempo sao exatamente as historicas (correlacao e stops simultaneos reais).
Risco de cauda: bootstrap por blocos de 30 dias da sequencia diaria da carteira (preserva agrupamentos).
Limites verificados: -3R num dia e -8R acumulado (R = risco da posicao), queda maxima em %.
Uso: python3 -m tools.carteira_short_turtle <operacoes.json> <capital> [saida.json]
Saida so em % e R (o capital nunca e escrito)."""
import json
import random
import sys

DIA = 86400


def simular(ops, capital, vagas=1, teto_pct=5.0, alvo_pct=0.5, min_ordem=5.0, gap=0.0, juro_dia=0.0003, fase="lateral",
            limite_dia_r=-3.0, limite_acum_r=-8.0):
    ops = sorted((o for o in ops if fase is None or o.get("fase") == fase), key=lambda o: o["t"])
    cap, abertas, feitas, recusas = float(capital), [], [], {"teto": 0, "vagas": 0, "mesma_moeda": 0, "suspenso": 0}
    acum_r, por_dia, suspenso = 0.0, {}, False
    curva = [(ops[0]["t"] if ops else 0, cap)]

    def fechar_ate(t):
        nonlocal cap, acum_r, suspenso
        for p in sorted([p for p in abertas if p["t_fim"] <= t], key=lambda p: p["t_fim"]):
            abertas.remove(p)
            dias = max(0.0, (p["t_fim"] - p["t"]) / DIA)
            res = p["r"] * p["risco"] - (gap * p["pos"] if p["r"] < 0 else 0.0) - juro_dia * dias * p["pos"]
            cap += res
            r_eq = res / p["risco"] if p["risco"] else 0.0
            acum_r += r_eq
            d = int(p["t_fim"] // DIA)
            por_dia[d] = por_dia.get(d, 0.0) + r_eq
            feitas.append({"t": p["t"], "t_fim": p["t_fim"], "a": p["a"], "r": round(r_eq, 4),
                           "risco_pct": round(100 * p["risco"] / p["cap0"], 3), "res_pct": round(100 * res / p["cap0"], 4),
                           "sobreposta": p["sobreposta"]})
            curva.append((p["t_fim"], cap))
            if acum_r <= limite_acum_r:
                suspenso = True

    for o in ops:
        fechar_ate(o["t"])
        if suspenso:
            recusas["suspenso"] += 1
            continue
        if por_dia.get(int(o["t"] // DIA), 0.0) <= limite_dia_r:
            recusas["suspenso"] += 1
            continue
        if any(p["a"] == o["a"] for p in abertas):
            recusas["mesma_moeda"] += 1
            continue
        if len(abertas) >= vagas:
            recusas["vagas"] += 1
            continue
        stop = abs(o["stop"])
        pos = max(min_ordem, cap * alvo_pct / 100 / stop)
        risco = pos * stop
        aberto = sum(p["risco"] for p in abertas)
        if risco > cap * teto_pct / 100 + 1e-9 or (aberto + risco) > cap * teto_pct / 100 + 1e-9 \
                or pos + sum(p["pos"] for p in abertas) > cap:
            recusas["teto"] += 1
            continue
        abertas.append({"t": o["t"], "t_fim": o["t_fim"], "a": o["a"], "r": o["r"], "pos": pos, "risco": risco,
                        "cap0": cap, "sobreposta": bool(abertas)})
    fechar_ate(float("inf"))
    return feitas, curva, recusas, cap


def metricas(feitas, curva, capital, anos):
    rs = [f["r"] for f in feitas]
    pico, dd = capital, 0.0
    for _, c in curva:
        pico = max(pico, c)
        dd = min(dd, c / pico - 1)
    g = sum(r for r in rs if r > 0)
    p = -sum(r for r in rs if r < 0)
    seg = [f for f in feitas if f["sobreposta"]]
    return {"ops": len(rs), "ops_ano": round(len(rs) / anos, 1), "ops_semana": round(len(rs) / anos / 52, 2),
            "R_op": round(sum(rs) / len(rs), 3) if rs else None, "pf": round(g / p, 2) if p else None,
            "acerto": round(sum(r > 0 for r in rs) / len(rs), 3) if rs else None,
            "retorno_total_pct": round(100 * (curva[-1][1] / capital - 1), 1), "pior_queda_pct": round(100 * dd, 1),
            "retorno_anual_pct": round(100 * ((curva[-1][1] / capital) ** (1 / anos) - 1), 1) if curva[-1][1] > 0 else -100,
            "risco_medio_pct": round(sum(f["risco_pct"] for f in feitas) / len(feitas), 2) if feitas else None,
            "ops_em_sobreposicao": len(seg),
            "R_op_sobrepostas": round(sum(f["r"] for f in seg) / len(seg), 3) if seg else None}


def cauda(feitas, capital, dias_tot, n=3000, semente=7):
    """Bootstrap por blocos de 30 dias do resultado diario em % (composto): P(queda >= 20%/30%) num ano."""
    if not feitas:
        return {}
    d0 = int(min(f["t"] for f in feitas) // DIA)
    diario = [0.0] * (dias_tot + 1)
    for f in feitas:
        i = int(f["t_fim"] // DIA) - d0
        if 0 <= i < len(diario):
            diario[i] += f["res_pct"] / 100
    blocos = [diario[i:i + 30] for i in range(0, max(1, len(diario) - 30), 30)]
    rnd = random.Random(semente)
    q20 = q30 = 0
    fins = []
    for _ in range(n):
        eq = pico = 1.0
        dd = 0.0
        for _ in range(12):
            for x in rnd.choice(blocos):
                eq *= 1 + x
                pico = max(pico, eq)
                dd = min(dd, eq / pico - 1)
        q20 += dd <= -0.20
        q30 += dd <= -0.30
        fins.append(eq - 1)
    fins.sort()
    return {"P_queda>=20%_1ano": round(q20 / n, 3), "P_queda>=30%_1ano": round(q30 / n, 3),
            "retorno_1ano_p05_pct": round(100 * fins[int(0.05 * n)], 1), "retorno_1ano_p50_pct": round(100 * fins[n // 2], 1)}


def dias_piores(feitas):
    por = {}
    for f in feitas:
        d = int(f["t_fim"] // DIA)
        por[d] = por.get(d, 0.0) + f["r"]
    return round(min(por.values()), 2) if por else 0.0


def correr(ops, capital, fase="lateral"):
    ts = [o["t"] for o in ops if o.get("fase") == fase] or [0]
    anos = max(1e-9, (max(o["t_fim"] for o in ops) - min(ts)) / DIA / 365)
    dias_tot = int((max(o["t_fim"] for o in ops) - min(ts)) / DIA) + 1
    out = {}
    for vagas in (1, 2, 3):
        for gap in (0.0, 0.005, 0.01):
            f, c, rec, _ = simular(ops, capital, vagas=vagas, gap=gap, fase=fase)
            m = metricas(f, c, capital, anos)
            m.update(cauda(f, capital, dias_tot), recusas=rec, pior_dia_R=dias_piores(f))
            out[f"{vagas} vagas|gap {gap}"] = m
    return {"anos": round(anos, 2), "fase": fase, "teto_agregado_pct": 5.0, "resultados": out}


if __name__ == "__main__":
    ops = json.load(open(sys.argv[1]))
    r = correr([o for o in ops if o.get("k", "SHORT_TURTLE") == "SHORT_TURTLE"], float(sys.argv[2]))
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=1)
    for k, v in r["resultados"].items():
        print(k, json.dumps({x: v[x] for x in ("ops_ano", "R_op", "pf", "retorno_anual_pct", "pior_queda_pct",
                                              "P_queda>=20%_1ano", "risco_medio_pct", "ops_em_sobreposicao",
                                              "R_op_sobrepostas", "pior_dia_R", "recusas")}, ensure_ascii=False))
