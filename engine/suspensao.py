"""(ordem do Rui de 10/11, ponto 2) Estrategia SUSPENSA: o que fazer com o que ja esta na corretora.

Causa da execucao da PARTI (10/11): a suspensao so travava SINAIS NOVOS. Uma ordem limite ja enviada continuava viva
na OKX ate caducar (12 h) e o agente so volta de hora a hora; a PARTI foi enviada as 04:08, a regra "so panico do
mercado todo" entrou no main as 04:14, a ordem executou as 04:38 e a volta seguinte (05:07) ja a encontrou aberta.
A suspensao total (04:48) tambem nao tocava em ordens pendentes. Na Bybit o executor do panico (H45) ja cancela as
ordens pendentes de uma estrategia suspensa ("suspensa"); na OKX nao havia o equivalente.

Esta funcao decide, para cada operacao do executor, uma de quatro acoes, sem nunca enviar nada:
  "cancelar_pendente" - ordem de ENTRADA ainda nao executada de uma estrategia suspensa: cancelar so essa ordem;
  "gerir"             - posicao ja executada (aberta): continua a ser gerida (stop, objetivo, saida por tempo), mesmo
                        com a estrategia suspensa. Suspender NUNCA fecha posicoes nem mexe em protecoes;
  "manter"            - estrategia ativa: nada muda;
  "ja_pedido"         - o cancelamento ja foi pedido nesta ordem (idempotente: nao repete o pedido; o acompanhamento
                        normal confirma o estado na corretora).
Parcialmente executada (estado ainda "pendente" com execucao parcial): "cancelar_pendente" cancela so o RESTO da
ordem; a parte executada passa a posicao e segue "gerir" (e o que o acompanhamento da OKX ja faz com ordens parciais).
Nao esta ligada a nenhum executor: liga-la e uma alteracao de execucao real que so o Rui autoriza."""

ESTRATEGIAS_OKX = {
    # estrategia no registo da operacao -> interruptor em okx_config.json
    "panico": "panico_real", None: "panico_real", "recuo": "recuo_real",
}


def ativa(cfg, estrategia, mapa=ESTRATEGIAS_OKX):
    chave = mapa.get(estrategia, mapa.get(None))
    return bool((cfg or {}).get("real")) and bool((cfg or {}).get(chave))


def decidir(cfg, op, mapa=ESTRATEGIAS_OKX):
    """op: registo do executor ({'estado': 'pendente'|'aberta'|..., 'estrategia', 'cancelar_pedido', 'parcial'})."""
    estado = op.get("estado")
    if estado in ("fechada", "cancelada", "recusada"):
        return "manter"
    if ativa(cfg, op.get("estrategia"), mapa):
        return "manter"
    if estado == "aberta":
        return "gerir"
    if estado == "pendente":
        return "ja_pedido" if op.get("cancelar_pedido") else "cancelar_pendente"
    return "manter"


def plano(cfg, ops, mapa=ESTRATEGIAS_OKX):
    """{ativo: acao} para todas as operacoes; so lista as que nao sao 'manter'."""
    out = {}
    for base, op in (ops or {}).items():
        a = decidir(cfg, op, mapa)
        if a != "manter":
            out[base] = a
    return out
