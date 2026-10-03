# Executor (SIMULAÇÃO)

Transforma os sinais do motor em ordens. **Nesta fase não coloca nenhuma
ordem**: não tem chaves, não liga à Bybit e só escreve o que faria.

- Vive só no ramo `executor`. O scanner (ramo `main`) nunca o vê.
- Só lê `state.json` (ramo `data`). Não altera o motor, a configuração,
  o estado nem o Telegram.

## Usar

    git fetch origin data && git show FETCH_HEAD:state.json > /tmp/state.json
    python -m executor.simulate /tmp/state.json executor_out

Escreve em `executor_out/`:
- `orders.jsonl`: uma linha por ordem que seria colocada, alterada ou cancelada
- `book.json`: o que o executor já fez por sinal (para não repetir)

Testes: `python -m unittest discover -q -s executor/tests -t .`

## Regras

| Estado do sinal | Ação |
|---|---|
| ACTIVE (novo) | ordem limite de entrada no limite da zona (topo nas compras, base nos shorts) |
| TRIGGERED | stop para a posição toda + um objetivo limite por parcial |
| 1.º objetivo atingido | stop passa para a entrada, na quantidade restante |
| CLOSED | cancela o que restar |
| EXPIRED / INVALIDATED | cancela a entrada |

Travões próprios (independentes do motor): só sinais em modo REAL; máximo
de 2 operações; máximo de 25 USDC por posição e 1 USDC de risco; estado
com mais de 10 minutos é recusado; sinal já em curso quando o executor
arranca é ignorado (não se persegue o preço); ordem abaixo da ordem
mínima (5 USDC) é assinalada.

## Por confirmar antes de ligar a dinheiro real

- Endereço da API para contas da Bybit UE e se a margem spot (empréstimo,
  shorts) está disponível por API nessas contas. A documentação pública
  (bybit-exchange.github.io/docs/v5) não o diz.
- Passo de preço, passo de quantidade e ordem mínima por par
  (`/v5/market/instruments-info`). Sem isso as quantidades não são
  arredondadas como a corretora exige.
- Tipo de ordem de stop em spot (ordem condicional ou TP/SL associado) e
  se stop e objetivos podem coexistir sobre o mesmo saldo.
- A Bybit tem conta de demonstração com API (`api-demo.bybit.com`); falta
  confirmar se existe para contas UE. Seria o passo seguinte à simulação.
