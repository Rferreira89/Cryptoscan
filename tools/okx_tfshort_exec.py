"""(11/11, PREPARACAO; NAO ATIVO) Executor da TF-SHORT U2 na OKX X-Perps: short com stop anexado, fecho pela regra,
reconciliacao, protecao contra duplicados e tratamento de falhas/reinicios.

Desligado por omissao: so faz pedidos de escrita se okx_config.json tiver "tfshort_real": true (NAO existe hoje).
O cliente e injetado (cliente(metodo, caminho, corpo) -> dict da OKX), por isso os testes correm sem rede.

Decisoes de sinal: as do papel (tools/okx_tfshort.correr, livro "conta"): entradas = moedas novas em conta.abertas,
saidas = moedas que sairam de conta.abertas (regra s >= 3 ou stop). O executor nao decide sinais.
Tamanho: tools/okx_tfshort_plano.plano_entrada (peso por volatilidade, minimo do contrato sem subir o risco,
<= 5 posicoes, bruta <= 0,5x, risco no stop <= tfshort_risco_max_pct).

Regras de seguranca:
  - clOrdId deterministico por sinal (tf<MOEDA><t>): um reinicio nunca duplica; 51016 (clOrdId repetido) -> adota;
  - uma moeda com op registada (pendente/aberta/a fechar) nunca recebe outra entrada;
  - posicao na OKX sem registo (estado perdido) -> adotada e assinalada, nunca duplicada;
  - registo "aberta" sem posicao na OKX -> fechada (stop ou fecho), com o preco das execucoes se houver;
  - posicao aberta sem stop pendente na OKX -> alerta prioritario (nao se repoe sozinho: decisao do Rui);
  - falha de rede/limite (codigo "rede", 50011, 50013) -> nada muda, tenta na volta seguinte;
  - recusa definitiva da OKX -> registada uma vez por sinal, sem nova tentativa desse sinal;
  - o fecho e sempre reduceOnly (nunca abre long)."""
import time

from tools import okx_tfshort_plano as TP

TRANSITORIOS = {"rede", "50011", "50013", "50001", "50004", "HTTP"}


def decisoes(R, conta_abertas, info, eq, cfg):
    """Acoes a tomar: [("abrir", moeda, sinal, corpo, resumo)] e [("fechar", moeda)]. Pura."""
    ops = R.setdefault("ops", {})
    acoes, recusas = [], []
    for moeda, op in list(ops.items()):
        if op.get("estado") == "aberta" and moeda not in conta_abertas:
            acoes.append(("fechar", moeda))
    abertas = {m: {"nocional": o.get("nocional", 0)} for m, o in ops.items() if o.get("estado") in ("pendente", "aberta", "a_fechar")}
    for moeda in sorted(conta_abertas):                       # alfabetico, como o papel
        sinal = conta_abertas[moeda]
        cl = f"tf{moeda[:8]}{int(sinal.get('t', 0)) % 100000000}"[:32]
        if moeda in ops or cl in R.setdefault("tentados", []):
            continue
        i = info.get(moeda)
        if not i:
            recusas.append((moeda, "sem X-Perp negociavel"))
            continue
        sig = {"entrada": sinal["entrada"], "atr": sinal["atr_pct"] * sinal["entrada"], "w": sinal["w"], "t": sinal.get("t", 0)}
        corpo, res = TP.plano_entrada(moeda, sig, i, eq, abertas, cfg)
        if not corpo:
            recusas.append((moeda, res))
            continue
        acoes.append(("abrir", moeda, sinal, corpo, res))
        abertas[moeda] = {"nocional": res["contratos"] * i["ctVal"] * sinal["entrada"]}
    return acoes, recusas


def executar(R, acoes, info, cliente, now, msgs):
    ops = R.setdefault("ops", {})
    tent = R.setdefault("tentados", [])
    for a in acoes:
        if a[0] == "abrir":
            _, moeda, sinal, corpo, res = a
            i = info[moeda]
            lv = cliente("POST", "/api/v5/account/set-leverage", {"instId": i["inst"], "lever": str(res["alav"]), "mgnMode": "isolated"})
            if str(lv.get("code")) in TRANSITORIOS:
                msgs.append(f"⏳ TF-SHORT {moeda}: falha transitória ao preparar a alavancagem; tento na volta seguinte.")
                continue
            r = cliente("POST", "/api/v5/trade/order", corpo)
            d = (r.get("data") or [{}])[0]
            sc = str(d.get("sCode") or r.get("code"))
            if sc == "51016":                                   # clOrdId repetido: ja existe (reinicio) -> adota
                q = cliente("GET", f"/api/v5/trade/order?instId={i['inst']}&clOrdId={corpo['clOrdId']}", None)
                qd = (q.get("data") or [{}])[0]
                if qd.get("ordId"):
                    d, sc = {"ordId": qd["ordId"]}, "0"
            if sc in TRANSITORIOS:
                msgs.append(f"⏳ TF-SHORT {moeda}: falha transitória ({sc}); nada enviado de novo nesta volta.")
                continue
            tent.append(corpo["clOrdId"])
            if sc not in ("0", "None") or not d.get("ordId"):
                R.setdefault("recusas", []).append({"moeda": moeda, "t": int(now), "codigo": sc, "msg": str(d.get("sMsg") or r.get("msg"))[:80]})
                msgs.append(f"⚠️ TF-SHORT {moeda}: a OKX recusou a entrada ({sc}).")
                continue
            ops[moeda] = {"inst": i["inst"], "ordId": d["ordId"], "clOrdId": corpo["clOrdId"], "estado": "pendente",
                          "t_sinal": sinal.get("t"), "criado": int(now), "stop": res["stop"], "contratos": res["contratos"],
                          "nocional": res["contratos"] * i["ctVal"] * sinal["entrada"]}
            msgs.append(f"📌 TF-SHORT {moeda}: short a mercado enviado, stop {res['stop']:.6g} anexado "
                        f"(risco no stop {res['risco_pct_no_stop']:.2f}% da conta).")
        elif a[0] == "fechar":
            moeda = a[1]
            op = ops[moeda]
            corpo = TP.plano_saida(moeda, info.get(moeda) or {"inst": op["inst"], "minSz": 1, "lotSz": 1}, op["contratos"])
            corpo["clOrdId"] = f"tx{moeda[:8]}{int(op.get('t_sinal') or 0) % 100000000}"[:32]
            r = cliente("POST", "/api/v5/trade/order", corpo)
            d = (r.get("data") or [{}])[0]
            sc = str(d.get("sCode") or r.get("code"))
            if sc in ("0", "51016"):
                op.update(estado="a_fechar", pedido_fecho=int(now))
                msgs.append(f"🔚 TF-SHORT {moeda}: fecho pela regra enviado (só reduz).")
            elif sc in TRANSITORIOS:
                msgs.append(f"⏳ TF-SHORT {moeda}: falha transitória no fecho; tento na volta seguinte.")
            else:
                op["recusa_fecho"] = {"t": int(now), "codigo": sc}
                msgs.append(f"🚨 TF-SHORT {moeda}: a OKX recusou o FECHO ({sc}). Verificar a posição.")


def reconciliar(R, cliente, now, msgs):
    """Compara o registo com a OKX (posicoes, ordens e stops). Nunca envia ordens."""
    ops = R.setdefault("ops", {})
    pos = cliente("GET", "/api/v5/account/positions?instType=FUTURES", None)
    if str(pos.get("code")) != "0":
        msgs.append("⏳ TF-SHORT: não consegui ler as posições; registo inalterado nesta volta.")
        return False
    na_okx = {}
    for p in pos.get("data") or []:
        try:
            q = float(p.get("pos") or 0)
        except (TypeError, ValueError):
            continue
        if q:
            na_okx[p.get("instId")] = {"pos": q, "avgPx": float(p.get("avgPx") or 0)}
    inst_ops = {o["inst"]: m for m, o in ops.items()}
    for iid, p in na_okx.items():                              # posicao sem registo (reinicio com estado perdido)
        m = iid.split("-")[0]
        if iid not in inst_ops and "XPERP" in iid and p["pos"] < 0 and m not in ops and m in (R.get("universo") or []):
            if True:
                ops[m] = {"inst": iid, "estado": "aberta", "adotada": True, "entrada": p["avgPx"], "contratos": abs(p["pos"]),
                          "criado": int(now), "nocional": 0}
                msgs.append(f"🧩 TF-SHORT {m}: posição curta na OKX sem registo; adotada (não duplico).")
    algo = cliente("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=FUTURES", None)
    com_stop = {a.get("instId") for a in (algo.get("data") or [])} if str(algo.get("code")) == "0" else None
    for m, op in list(ops.items()):
        p = na_okx.get(op["inst"])
        if op["estado"] == "pendente":
            if p and p["pos"] < 0:
                op.update(estado="aberta", entrada=p["avgPx"], t_fill=int(now))
            elif now - op.get("criado", now) > 3600:
                q = cliente("GET", f"/api/v5/trade/order?instId={op['inst']}&ordId={op['ordId']}", None)
                st = ((q.get("data") or [{}])[0]).get("state")
                if st in ("canceled", "mmp_canceled"):
                    R.setdefault("hist", []).append({"moeda": m, **ops.pop(m), "estado": "cancelada", "fechado": int(now)})
                continue
        if op["estado"] in ("aberta", "a_fechar"):
            if not p:
                fills = cliente("GET", f"/api/v5/trade/fills-history?instType=FUTURES&instId={op['inst']}", None)
                compras = [f for f in (fills.get("data") or []) if f.get("side") == "buy"
                           and int(f.get("ts") or 0) / 1000 >= op.get("t_fill", op.get("criado", 0))]
                saida = None
                if compras:
                    qt = sum(float(f.get("fillSz") or 0) for f in compras)
                    saida = sum(float(f.get("fillPx") or 0) * float(f.get("fillSz") or 0) for f in compras) / qt if qt else None
                motivo = "regra" if op["estado"] == "a_fechar" else "stop (posição fechada na OKX)"
                R.setdefault("hist", []).append({"moeda": m, **ops.pop(m), "estado": "fechada", "saida": saida,
                                                 "motivo": motivo, "fechado": int(now)})
                msgs.append(f"✅ TF-SHORT {m}: posição fechada ({motivo}).")
            elif com_stop is not None and op["inst"] not in com_stop and op["estado"] == "aberta":
                k = op.setdefault("sem_stop", 0) + 1
                op["sem_stop"] = k
                if k == 1 or k % 6 == 0:
                    msgs.append(f"🚨 TF-SHORT {m}: posição aberta SEM stop pendente na OKX. Verificar já.")
            else:
                op.pop("sem_stop", None)
    del R.setdefault("hist", [])[:-300]
    return True


def volta(R, papel_conta_abertas, info, eq, cliente, cfg, now=None):
    """Uma volta completa: reconcilia, decide e (so com tfshort_real) executa. Devolve as mensagens."""
    now = now or time.time()
    msgs = []
    if not reconciliar(R, cliente, now, msgs):
        return msgs
    if not (cfg or {}).get("tfshort_real"):
        return msgs                                            # desligado: so reconcilia (nunca escreve)
    acoes, recusas = decisoes(R, papel_conta_abertas, info, eq, cfg)
    for m, motivo in recusas:
        chave = f"{m}:{(papel_conta_abertas.get(m) or {}).get('t')}"
        if chave not in R.setdefault("avisados", []):
            R["avisados"].append(chave)
            msgs.append(f"⏭️ TF-SHORT {m}: não entrou ({motivo}).")
    del R.setdefault("avisados", [])[:-500]
    executar(R, acoes, info, cliente, now, msgs)
    return msgs
