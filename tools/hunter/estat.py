"""Estatistica do Hunter (corrige a metodologia de 17/11).

Problemas corrigidos:
- 17/11 (qo_descoberta) comparava as operacoes com 5 controlos por operacao num teste de Welch como se os 5 fossem
  independentes entre si e das operacoes: inflava n. Aqui cada operacao tem o SEU controlo (media de k entradas ao
  acaso da mesma moeda, mesmo lado, mesma geometria, mesmo periodo) e o teste e sobre a DIFERENCA EMPARELHADA.
- Operacoes do mesmo dia/acontecimento de mercado nao sao independentes (um despejo dispara dezenas de moedas).
  O intervalo de confianca e o p vem de um bootstrap por BLOCOS (um bloco = um dia UTC: reamostra dias inteiros).
- Hipoteses multiplas: Holm sobre TODAS as hipoteses avaliadas na ronda E nas rondas anteriores (contador cumulativo
  guardado no registo), para que rondas sucessivas nao "pesquem" no mesmo periodo.
- Treino / validacao / teste: 50% / 25% / 25% do tempo. A descoberta so ve treino e validacao. O teste final e
  intocado: cada hipotese so pode ser avaliada no teste UMA vez e cada acesso fica no registo (hash da regra).
"""
import hashlib
import json
import math
import os
import random
import time

FRACOES = (0.50, 0.25, 0.25)


def cortes(t0, t1, fr=FRACOES):
    a = t0 + int(fr[0] * (t1 - t0))
    b = a + int(fr[1] * (t1 - t0))
    return a, b


def periodo(t, c):
    return "treino" if t < c[0] else "validacao" if t < c[1] else "teste"


def media(xs):
    return sum(xs) / len(xs) if xs else None


def bootstrap_blocos(ops, campo="d", n=2000, seed=11, bloco=86400):
    """ops: [{t, campo}] -> (media, ic95, p unilateral de media <= 0) reamostrando blocos (dias) inteiros."""
    if not ops:
        return None, None, 1.0
    blocos = {}
    for o in ops:
        blocos.setdefault(int(o["t"]) // bloco, []).append(float(o[campo]))
    bl = list(blocos.values())
    m0 = media([x for b in bl for x in b])
    if len(bl) < 2:
        return m0, None, 1.0
    rng = random.Random(seed)
    ms = []
    for _ in range(n):
        s = c = 0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]
            s += sum(b)
            c += len(b)
        ms.append(s / c)
    ms.sort()
    p = (sum(1 for m in ms if m <= 0) + 1) / (n + 1)
    return m0, [round(ms[int(0.025 * (n - 1))], 4), round(ms[int(0.975 * (n - 1))], 4)], p


def holm(ps, m_total=None):
    """{k: p} -> {k: p_holm}; m_total >= len(ps) conta tambem as hipoteses ja gastas em rondas anteriores."""
    ordem = sorted(ps, key=lambda k: ps[k])
    m = max(len(ordem), int(m_total or 0))
    out, acc = {}, 0.0
    for j, k in enumerate(ordem):
        acc = max(acc, min(1.0, (m - j) * ps[k]))
        out[k] = round(acc, 6)
    return out


def regra_id(regra):
    return hashlib.sha256(json.dumps(regra, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


class Registo:
    """Registo persistente (ramo autonomo): hipoteses ja avaliadas (contador para Holm) e acessos ao teste final."""

    def __init__(self, caminho=None):
        self.caminho = caminho
        self.d = {"hipoteses_avaliadas": 0, "rondas": [], "acessos_teste": {}}
        if caminho and os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                self.d.update(json.load(f))

    def nova_ronda(self, n_hipoteses, nota=""):
        self.d["hipoteses_avaliadas"] += int(n_hipoteses)
        self.d["rondas"].append({"t": int(time.time()), "hipoteses": int(n_hipoteses), "nota": nota})
        return self.d["hipoteses_avaliadas"]

    def pode_testar(self, rid):
        return rid not in self.d["acessos_teste"]

    def marcar_teste(self, rid, resultado):
        if rid in self.d["acessos_teste"]:
            raise ValueError(f"teste final ja usado para {rid}: nao se reavalia no mesmo periodo")
        self.d["acessos_teste"][rid] = {"t": int(time.time()), "resultado": resultado}

    def guardar(self):
        if self.caminho:
            with open(self.caminho, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=1)


def resumo(ops, nome_periodo):
    """Metricas de um conjunto de operacoes emparelhadas [{t, r, ctrl, d, regime}]."""
    if not ops:
        return {"periodo": nome_periodo, "n": 0}
    rs = [o["r"] for o in ops]
    m_r, ic_r, p_r = bootstrap_blocos(ops, "r")
    m_d, ic_d, p_d = bootstrap_blocos(ops, "d")
    eq = pk = dd = 0.0
    for x in sorted(ops, key=lambda o: o["t"]):
        eq += x["r"]
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    reg = {}
    for o in ops:
        reg.setdefault(o.get("regime") or "?", []).append(o["r"])
    dias = len({int(o["t"]) // 86400 for o in ops})
    return {"periodo": nome_periodo, "n": len(ops), "dias_com_operacoes": dias,
            "r_medio": round(m_r, 4), "ic95_r": ic_r, "p_r_positivo": round(p_r, 5),
            "controlo_medio": round(media([o["ctrl"] for o in ops]), 4),
            "vantagem_sobre_acaso": round(m_d, 4), "ic95_vantagem": ic_d, "p_vantagem": round(p_d, 5),
            "acerto": round(sum(1 for x in rs if x > 0) / len(rs), 3), "drawdown_r": round(dd, 2),
            "por_regime": {k: [len(v), round(media(v), 3)] for k, v in sorted(reg.items())}}


def ic_proporcao_wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 4), round(c + h, 4)]
