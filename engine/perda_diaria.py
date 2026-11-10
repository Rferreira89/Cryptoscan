"""(ordem do Rui de 10/11, ponto 5) Perda diaria em PERCENTAGEM da conta, sem valores em dinheiro.

Como se obtem uma metrica correta com os dados publicos (o saldo e o lucro em USD estao cifrados):
  % da conta perdida/ganha numa operacao = R da operacao x risco planeado da operacao (% da conta ate ao stop).
  - OKX: R = retorno no preco / distancia ao stop (ret_pct, entrada, stop do registo publico real.hist);
         risco = risco_pct guardado na abertura (desde 08/11). Sem risco_pct -> desconhecido (nunca estimado).
  - Bybit: R = real_r (reconciliacao com as execucoes) ou user_result_r (fecho manual registado);
           risco = risk_pct do plano. Sem R real -> desconhecido (o R do sinal NUNCA entra).
  Limites conhecidos: o risco planeado e % da conta NA ABERTURA; com varias posicoes o erro de composicao e pequeno
  (perdas de 1-3%); as comissoes ja estao no R real da Bybit, na OKX o ret_pct e no preco (sem comissao/financiamento:
  o dia fica marcado "sem custos").
Agrega por dia UTC de FECHO. Um dia com alguma operacao de resultado desconhecido fica "incompleto".
So leitura e calculo: nao bloqueia nada nem esta ligado a nenhum executor."""
import time

DIA = 86400


def da_okx(okx):
    out = []
    for h in ((okx or {}).get("real") or {}).get("hist") or []:
        if h.get("estado") != "fechada":
            continue
        e, s, ret = h.get("entrada"), h.get("stop"), h.get("ret_pct")
        R = None
        if e and s and ret is not None and e > s:
            R = (ret / 100) / ((e - s) / e)
        rp = h.get("risco_pct")
        out.append({"corretora": "okx", "id": h.get("asset"), "t": h.get("fechado"), "R": R, "risco_pct": rp,
                    "pct": None if (R is None or rp is None) else R * rp, "sem_custos": True})
    return out


def da_bybit(state):
    out = []
    for r in (state or {}).get("ledger") or []:
        if r.get("executed") is not True or r.get("status") != "CLOSED":
            continue
        R = r.get("real_r") if r.get("real_r") is not None else r.get("user_result_r")
        rp = r.get("risk_pct")
        out.append({"corretora": "bybit", "id": r.get("id"), "t": r.get("closed_at"), "R": R, "risco_pct": rp,
                    "pct": None if (R is None or rp is None) else R * rp, "sem_custos": False})
    return out


def por_dia(ops):
    """{'AAAA-MM-DD': {'pct': soma conhecida, 'n': k, 'desconhecidas': j, 'completo': bool, 'sem_custos': bool}}"""
    dias = {}
    for o in ops:
        if not o.get("t"):
            continue
        d = time.strftime("%Y-%m-%d", time.gmtime(o["t"]))
        x = dias.setdefault(d, {"pct": 0.0, "n": 0, "desconhecidas": 0, "sem_custos": False})
        x["n"] += 1
        if o["pct"] is None:
            x["desconhecidas"] += 1
        else:
            x["pct"] = round(x["pct"] + o["pct"], 3)
        x["sem_custos"] = x["sem_custos"] or o["sem_custos"]
    for x in dias.values():
        x["completo"] = x["desconhecidas"] == 0
    return dict(sorted(dias.items()))


def pior_dia(dias):
    """Pior dia COMPLETO (os incompletos nao contam como prova de nada)."""
    c = [(d, x["pct"]) for d, x in dias.items() if x["completo"]]
    return min(c, key=lambda z: z[1]) if c else None
