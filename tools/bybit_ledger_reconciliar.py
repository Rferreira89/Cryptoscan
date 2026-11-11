"""(11/11, auditoria P6) Reconciliacao dos registos REAL da Bybit que ficaram "OPEN" sem terem sido executados.

Caso: AVAX-SHORT_TURTLE-1792670417 e ICP-SHORT_TURTLE-1792684818 (22/10) estao no ledger com status OPEN e
executed: false, e a conta tem 0 posicoes (ordens_ok, 11/11 01:05). Sao sinais cuja ordem nunca entrou.

Por omissao e um ENSAIO (dry-run): le e mostra o que faria. So corrige com --aplicar e so os registos em que os
TRES criterios estao provados com leituras bem-sucedidas da Bybit (so GET):
  1. zero execucoes do par desde a emissao do sinal (/v5/execution/list, todas as janelas lidas sem erro);
  2. sem posicao: sem moedas acima do nucleo nem divida da moeda (/v5/account/wallet-balance);
  3. sem ordem ativa do par (/v5/order/realtime, com e sem filtro).
Uma leitura falhada = criterio NAO provado = o registo nao e tocado.
A correcao nao apaga nada: status passa a CANCELLED, o estado anterior fica em `antes` e a prova em `reconciliacao`
(trilho de auditoria); o resultado em R fica None (nao conta como operacao). Nao envia ordens nem mexe na conta.
Uso: python3 tools/bybit_ledger_reconciliar.py <state.json> [--aplicar]"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

JANELA = 7 * 86400 - 60


class LeituraFalhou(Exception):
    pass


def _get(path, params):
    from engine import account
    try:
        return account.get(path, params)
    except account.AccountError as e:
        raise LeituraFalhou(str(e)) from None


def candidatos(ledger):
    return [r for r in ledger or [] if r.get("mode") == "REAL" and r.get("status") == "OPEN" and r.get("executed") is False]


def simbolo(r):
    return (r.get("pair") or "").replace("/", "")


def execucoes(sym, t0, t1, get=_get):
    """Todas as execucoes do par entre t0 e t1; levanta LeituraFalhou se alguma janela falhar."""
    out, a = [], t0
    while a < t1:
        b = min(t1, a + JANELA)
        res = get("/v5/execution/list", {"category": "spot", "symbol": sym, "limit": 100,
                                         "startTime": int(a * 1000), "endTime": int(b * 1000)})
        out += res.get("list") or []
        a = b
    return out


def ordens_ativas(sym, get=_get):
    vistas = {}
    for flt in (None, "Order", "StopOrder", "tpslOrder"):
        prm = {"category": "spot", "symbol": sym, "limit": 50}
        if flt:
            prm["orderFilter"] = flt
        for o in get("/v5/order/realtime", prm).get("list") or []:
            vistas[o.get("orderId") or id(o)] = o
    return list(vistas.values())


def posicao(moeda, nucleo_q, get=_get):
    """(tem_posicao, detalhe) com o saldo da conta unificada; moedas do nucleo nao contam."""
    res = get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    for conta in res.get("list") or []:
        for c in conta.get("coin") or []:
            if (c.get("coin") or "").upper() == moeda.upper():
                tem = float(c.get("walletBalance") or 0) - float(nucleo_q or 0)
                divida = float(c.get("borrowAmount") or 0)
                return (tem > 1e-9 or divida > 1e-9), {"acima_do_nucleo": tem > 1e-9, "divida": divida > 1e-9}
    return False, {"acima_do_nucleo": False, "divida": False}


def provar(r, now, nucleo=None, get=_get):
    """Criterios para um registo. Cada um: True (provado), False (falhou: ha atividade) ou None (leitura falhou)."""
    sym, moeda = simbolo(r), (r.get("asset") or "")
    t0 = float(r.get("issued_at") or r.get("opened_at") or 0)
    prova = {}
    try:
        ex = execucoes(sym, t0, now, get)
        prova["zero_execucoes"] = len(ex) == 0
        prova["n_execucoes"] = len(ex)
    except LeituraFalhou as e:
        prova["zero_execucoes"], prova["erro_execucoes"] = None, str(e)[:80]
    try:
        tem, det = posicao(moeda, ((nucleo or {}).get(moeda) or {}).get("qty"), get)
        prova["sem_posicao"] = not tem
        prova.update(det)
    except LeituraFalhou as e:
        prova["sem_posicao"], prova["erro_posicao"] = None, str(e)[:80]
    try:
        od = ordens_ativas(sym, get)
        prova["sem_ordem_ativa"] = len(od) == 0
    except LeituraFalhou as e:
        prova["sem_ordem_ativa"], prova["erro_ordens"] = None, str(e)[:80]
    prova["provado"] = all(prova.get(k) is True for k in ("zero_execucoes", "sem_posicao", "sem_ordem_ativa"))
    return prova


def corrigir(r, prova, now):
    """Correcao com trilho de auditoria; so chamada com prova completa."""
    assert prova.get("provado"), "correcao sem prova completa"
    antes = {k: r.get(k) for k in ("status", "executed", "opened_at", "entry", "tp_hit")}
    r.update(status="CANCELLED", closed_at=int(now), result_r=None, reason="NUNCA_EXECUTADA",
             antes=antes, reconciliacao={"t": int(now), "ferramenta": "bybit_ledger_reconciliar", "prova": prova})
    return r


def nucleo_do_executor():
    """Nucleo da carteira (moedas que nao sao de operacoes) do estado cifrado do executor (ramo execucoes)."""
    from engine import execucao
    ex = execucao.load()
    if ex is None:
        raise LeituraFalhou("exec.json (nucleo) ilegivel: sem DATA_KEY ou sem rede")
    return ex.get("nucleo") or {}


def correr(state, now=None, aplicar=False, get=_get, nucleo=None):
    """nucleo: {moeda: {qty}}; None -> le do executor; ilegivel -> nenhum registo fica provado."""
    now = now or time.time()
    if nucleo is None:
        try:
            nucleo = nucleo_do_executor()
        except LeituraFalhou as e:
            return [{"id": r["id"], "acao": "manter (nucleo ilegivel)", "prova": {"provado": False, "erro_nucleo": str(e)}}
                    for r in candidatos(state.get("ledger"))]
    plano = []
    for r in candidatos(state.get("ledger")):
        prova = provar(r, now, nucleo, get)
        acao = "corrigir" if prova["provado"] else "manter (prova incompleta)"
        if aplicar and prova["provado"]:
            corrigir(r, prova, now)
            acao = "corrigido"
        plano.append({"id": r["id"], "acao": acao, "prova": prova})
    return plano


if __name__ == "__main__":
    caminho, aplicar = sys.argv[1], "--aplicar" in sys.argv
    st = json.load(open(caminho))
    for p in correr(st, aplicar=aplicar):
        print(p["id"], "->", p["acao"], json.dumps(p["prova"]))
    if aplicar:
        json.dump(st, open(caminho, "w"))
        print("estado gravado (so os registos com prova completa foram alterados)")
    else:
        print("ensaio: nada foi alterado (use --aplicar)")
