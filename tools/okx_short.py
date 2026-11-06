"""(06/11, P1, preparacao isolada; NAO LIGADO ao agente nem ao okx_exec) Executor de SHORT para os X-Perps da OKX Europa.

INTERRUPTOR ABSOLUTO: SHORT_REAL_PERMITIDO = False (constante no codigo). Enquanto for False, NENHUM pedido que mude
a conta (ordens, cancelamentos, alavancagem, algos) sai deste modulo, seja qual for a configuracao ou o transporte:
`_enviar` recusa antes de tocar no transporte. Passar a True exige um commit proprio, revisto e autorizado pelo Rui,
alem do interruptor de configuracao "short_real" e de um transporte real injetado.

Ciclo de uma operacao (conta em net_mode, margem isolada, como o okx_exec):
  planear  -> tamanho pelo risco (stop ACIMA da entrada), minimo do contrato, margem livre, tetos e bloqueio por
              instrumento da arquitetura A1 (engine/multiestrategia), dados frescos;
  abrir    -> define a alavancagem minima necessaria; ordem SELL limite (ou mercado) com etiqueta da estrategia no
              clOrdId (idempotente: o mesmo sinal da sempre o mesmo clOrdId e nunca e reenviado);
  acompanhar -> estado da ordem: viva / parcial / preenchida / cancelada / caducada; ao haver quantidade preenchida,
              garante a protecao OCO de COMPRA reduce-only (stop acima, objetivo abaixo) com o tamanho preenchido;
  fechar   -> cancela os algos e compra reduce-only a mercado o que estiver aberto.
Falhas: codigo != "0" -> regista e nao repete as cegas; falha de comunicacao num envio -> estado "incerto", e a volta
seguinte reconcilia pelo clOrdId antes de qualquer reenvio (nunca duplica)."""
import zlib

from engine import multiestrategia as M

SHORT_REAL_PERMITIDO = False          # <- interruptor absoluto (ver docstring). NAO mudar sem autorizacao do Rui.
CODIGO = "tfs"                        # estrategia dona por omissao (TF-SHORT U2)
MAX_IDADE_PRECO_S = 120               # dados mais velhos do que isto: nao abre
VALIDADE_ORDEM_S = 8 * 3600
ESCRITA = ("/api/v5/trade/", "/api/v5/account/set-leverage", "/api/v5/account/position/margin-balance")


_SOMBRA = object()                    # senha da corretora sombra (simulacao sem rede); ver _enviar


class EnvioBloqueado(RuntimeError):
    """Tentativa de mudar a conta com o interruptor desligado."""


class Recusa(RuntimeError):
    """A corretora respondeu com erro (codigo != 0)."""


class SemComunicacao(RuntimeError):
    """Falha de rede/tempo: nao se sabe se o pedido chegou."""


# ---------- interruptor ----------
def real_permitido(cfg):
    return SHORT_REAL_PERMITIDO is True and bool((cfg or {}).get("short_real")) is True


def _enviar(cli, cfg, metodo, path, corpo=None):
    """Unica porta para a corretora. Leituras passam; escritas so com o interruptor absoluto E o de configuracao."""
    escrita = metodo != "GET"                              # qualquer POST/DELETE muda a conta
    # unica excecao: a corretora SOMBRA deste repositorio (tools/okx_sombra.CorretoraSombra), simulacao em memoria
    # sem rede, identificada pelo objeto-senha _SOMBRA (nao e um nome nem uma configuracao que se possa imitar)
    sombra = getattr(cli, "senha", None) is _SOMBRA
    if escrita and not sombra and not real_permitido(cfg):
        raise EnvioBloqueado(f"short real desligado: {metodo} {path} nao enviado")
    try:
        r = cli(metodo, path, corpo)
    except Exception as e:                                 # rede, tempo, resposta ilegivel
        raise SemComunicacao(type(e).__name__) from None
    if not isinstance(r, dict) or str(r.get("code")) != "0":
        raise Recusa(f"{path}: {(r or {}).get('code')} {(r or {}).get('msg', '')}"[:160])
    return r.get("data") or []


# ---------- planeamento (sem rede) ----------
def dados_frescos(px, t_px, agora):
    return bool(px) and px > 0 and t_px and agora - t_px <= MAX_IDADE_PRECO_S


def planear(sinal, capital, margem_livre, info, registo, abertas, posicoes_donos, agora):
    """Plano de short ou {"ok": False, "motivo"}. sinal: moeda, inst, px, t_px, stop, objetivo (opcional), id."""
    cod = sinal.get("cod") or CODIGO
    est = (registo.get("estrategias") or {}).get(cod)
    if not est:
        return {"ok": False, "motivo": "estrategia nao registada"}
    px, stop = float(sinal.get("px") or 0), float(sinal.get("stop") or 0)
    if not dados_frescos(px, sinal.get("t_px"), agora):
        return {"ok": False, "motivo": "dados desatualizados ou sem preco"}
    if stop <= px:
        return {"ok": False, "motivo": "stop tem de ficar acima da entrada num short"}
    obj = sinal.get("objetivo")
    if obj is not None and obj >= px:
        return {"ok": False, "motivo": "objetivo tem de ficar abaixo da entrada num short"}
    ok, m = M.pode_abrir(posicoes_donos, sinal["inst"], cod)
    if not ok:
        return {"ok": False, "motivo": m}
    t = M.tamanho(capital, float(est["risco_pct"]), px, stop, info, alav_max_estr=est.get("alav_max", 1),
                  alav_max_contrato=info.get("alav_max", M.ALAV_TETO), margem_livre=margem_livre)
    if not t.get("cabe"):
        return {"ok": False, "motivo": t.get("motivo")}
    ok, m = M.cabe_nos_tetos(abertas, {"cod": cod, "nocional": t["nocional"], "risco_usd": t["risco_usd"]},
                             capital, registo["tetos"], est)
    if not ok:
        return {"ok": False, "motivo": m}
    # deterministico (crc32, nao o hash do Python): o mesmo sinal da sempre o mesmo clOrdId em qualquer volta
    cl = M.etiqueta(cod, zlib.crc32(str(sinal["id"]).encode()) % 36 ** 4, int(sinal.get("t_sinal") or 0))
    return {"ok": True, "cod": cod, "inst": sinal["inst"], "moeda": sinal.get("moeda"), "px": px, "stop": stop,
            "objetivo": obj, "sz": round(t["contratos"], 10), "nocional": t["nocional"], "risco_usd": t["risco_usd"],
            "alav": t["alav"], "cl_id": cl, "sinal": sinal["id"]}


def _fmt(x):
    return f"{x:.10g}"


# ---------- execucao (so passa pelo _enviar) ----------
def abrir(cli, cfg, plano, estado, agora, mercado=False):
    """Envia a entrada SELL. Idempotente: se o clOrdId ja esta no estado (qualquer estado), nao reenvia."""
    ops = estado.setdefault("ops", {})
    if plano["cl_id"] in ops:
        return ops[plano["cl_id"]]
    op = dict(plano, estado="a_enviar", criado=int(agora), valido_ate=int(agora) + VALIDADE_ORDEM_S, preenchido=0.0)
    ops[plano["cl_id"]] = op
    try:
        _enviar(cli, cfg, "POST", "/api/v5/account/set-leverage",
                {"instId": plano["inst"], "lever": str(plano["alav"]), "mgnMode": "isolated"})
        corpo = {"instId": plano["inst"], "tdMode": "isolated", "side": "sell", "clOrdId": plano["cl_id"],
                 "ordType": "market" if mercado else "limit", "sz": _fmt(plano["sz"])}
        if not mercado:
            corpo["px"] = _fmt(plano["px"])
        d = _enviar(cli, cfg, "POST", "/api/v5/trade/order", corpo)
        op.update(estado="pendente", ordId=(d[0] if d else {}).get("ordId"))
    except EnvioBloqueado as e:
        op.update(estado="bloqueada", motivo=str(e))
    except Recusa as e:
        op.update(estado="recusada", motivo=str(e))
    except SemComunicacao as e:
        op.update(estado="incerto", motivo=f"sem comunicacao ({e}); reconciliar pelo clOrdId antes de reenviar")
    return op


def _proteger(cli, cfg, op, sz):
    """OCO de COMPRA reduce-only para o tamanho preenchido: stop acima, objetivo abaixo (se houver)."""
    corpo = {"instId": op["inst"], "tdMode": "isolated", "side": "buy", "reduceOnly": "true", "sz": _fmt(sz),
             "slTriggerPx": _fmt(op["stop"]), "slOrdPx": "-1"}
    if op.get("objetivo"):
        corpo.update(ordType="oco", tpTriggerPx=_fmt(op["objetivo"]), tpOrdPx="-1")
    else:
        corpo["ordType"] = "conditional"
    d = _enviar(cli, cfg, "POST", "/api/v5/trade/order-algo", corpo)
    op.update(algoId=(d[0] if d else {}).get("algoId"), protegido=sz)


def acompanhar(cli, cfg, op, agora):
    """Uma volta: estado da ordem e protecao. Devolve o estado final da op (texto)."""
    if op["estado"] in ("fechada", "cancelada", "recusada", "bloqueada"):
        return op["estado"]
    try:
        q = f"/api/v5/trade/order?instId={op['inst']}&clOrdId={op['cl_id']}"
        d = _enviar(cli, cfg, "GET", q)
    except SemComunicacao as e:
        op["aviso"] = f"sem comunicacao ({e}); repete na proxima volta"
        return op["estado"]
    except Recusa:
        if op["estado"] == "incerto":                       # a ordem nunca chegou: pode ser marcada como nao enviada
            op.update(estado="cancelada", motivo="o envio nao chegou a corretora (reconciliado)")
            return op["estado"]
        raise
    o = d[0] if d else {}
    st, cheio = o.get("state"), float(o.get("accFillSz") or 0)
    op["preenchido"] = cheio
    try:
        if cheio > 0 and op.get("protegido", 0) + 1e-12 < cheio:
            if op.get("algoId"):                            # parcial que cresceu: troca a protecao pelo tamanho novo
                _enviar(cli, cfg, "POST", "/api/v5/trade/cancel-algos", [{"instId": op["inst"], "algoId": op["algoId"]}])
            _proteger(cli, cfg, op, cheio)
        if st == "filled":
            op["estado"] = "aberta"
        elif st in ("canceled", "mmp_canceled"):
            op["estado"] = "aberta" if cheio > 0 else "cancelada"
        elif st in ("live", "partially_filled"):
            op["estado"] = "parcial" if cheio > 0 else "pendente"
            if agora >= op["valido_ate"]:
                _enviar(cli, cfg, "POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "clOrdId": op["cl_id"]})
                op["estado"] = "aberta" if cheio > 0 else "cancelada"
                op["motivo"] = "caducou: restante cancelado" if cheio > 0 else "caducou (8 h) sem executar"
    except EnvioBloqueado as e:
        op["aviso"] = str(e)
    except SemComunicacao as e:
        op["aviso"] = f"sem comunicacao ({e}); repete na proxima volta"
    return op["estado"]


def fechar(cli, cfg, op):
    """Cancela a protecao e compra reduce-only a mercado o tamanho aberto."""
    if op.get("algoId"):
        _enviar(cli, cfg, "POST", "/api/v5/trade/cancel-algos", [{"instId": op["inst"], "algoId": op["algoId"]}])
    if op.get("preenchido", 0) > 0:
        _enviar(cli, cfg, "POST", "/api/v5/trade/order", {"instId": op["inst"], "tdMode": "isolated", "side": "buy",
                                                         "ordType": "market", "reduceOnly": "true",
                                                         "sz": _fmt(op["preenchido"]), "clOrdId": op["cl_id"][:28] + "f"})
    op["estado"] = "fechada"
    return op
