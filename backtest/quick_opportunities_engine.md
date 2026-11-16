# Quick Opportunities Engine — plano técnico de investigação

Estado: investigação isolada; sem integração no scanner, sem execução de ordens e sem alterações de produção.

## Decisões do utilizador
- Direções: LONG e SHORT.
- Duração-alvo: 30 minutos a 4 horas.
- Frequência: procurar o máximo de oportunidades, mas só aceitar estratégias com vantagem estatística demonstrada.
- Regimes: subida, descida, lateralização e alta volatilidade.
- O motor deve descobrir oportunidades que não dependam dos sinais das estratégias atuais.

## Arquitetura proposta

### 1. Dados e timeframes
- Gatilho/execução simulada: velas de 30 minutos.
- Contexto: 1H e 4H.
- Horizonte máximo de posição: 8 velas de 30 minutos (4 horas); saídas antecipadas por stop, alvo ou invalidação.
- Usar apenas velas fechadas. Sinal calculado no fecho de uma vela; execução simulada nunca antes da vela seguinte.
- Validar timestamps, lacunas, duplicados, OHLCV, atraso e divergência entre fontes.
- Suporte 30m adicionado aos adaptadores públicos Binance, OKX, KuCoin e Bybit; a disponibilidade/qualidade deve ser verificada em runtime e por ativo.
- Os adaptadores atuais consultam candles SPOT. Um sinal SHORT é apenas hipótese analítica: não significa que exista contrato perpétuo, margem/borrow disponível ou permissão de short na venue. A executabilidade SHORT exige instrumento e custos próprios.

### 2. Famílias de hipóteses
Cada família deve ser testada isoladamente e em LONG/SHORT, sem presumir simetria:
1. Momentum e aceleração de volume.
2. Breakout/breakdown com reteste.
3. Pullback em tendência de 1H/4H.
4. Reversão à média nos extremos de range.
5. Liquidity sweep e recuperação/rejeição do nível.
6. Expansão de volatilidade após compressão.
7. Failed breakout / bull trap / bear trap.
8. Desequilíbrio de fluxo e derivados, apenas quando os dados históricos estiverem disponíveis e sincronizados.

### 3. Universo e regime
- Construir universo ponto-no-tempo, incluindo ativos entretanto removidos, para reduzir survivorship bias.
- Filtrar por liquidez, spread, profundidade e volume negociável na venue de execução.
- Classificar regime por ativo e contexto global; não usar apenas a direção do BTC como veto universal.
- Permitir LONG contra mercado bearish e SHORT contra mercado bullish apenas quando a hipótese específica justificar essa operação e passar validação própria.

### 4. Simulação e custos
- Backtest separado do motor atual, sem alterar engine/signals.py, engine/promo.py, scanner.py ou configuração de produção.
- Incluir comissões dos dois lados, spread, slippage conservador, funding e, para shorts em margem spot, custo/disponibilidade de empréstimo quando aplicável.
- Simular fills na vela seguinte; resolver stop/TP tocados na mesma vela de forma conservadora.
- Incluir expiração máxima de 4 horas e medir tempo real em posição.
- Rejeitar sinais que não possam ser executados no tamanho mínimo e na liquidez real da venue.

### 5. Validação estatística
- Separação cronológica treino/validação/teste; walk-forward e período final intocado.
- Sem look-ahead, leakage, seleção retrospetiva de ativos ou parâmetros escolhidos com base no teste final.
- Medir R líquido, expectativa, profit factor, drawdown, taxa de acerto, frequência, duração, custos e desempenho por regime/direção/ativo.
- Comparar com entradas aleatórias condicionadas ao mesmo universo, horário e regime; preservar o critério do projeto de superar o percentil 95 do acaso.
- Corrigir testes múltiplos quando forem exploradas muitas variantes; publicar intervalos de confiança e número efetivo de operações.
- Não aprovar uma hipótese apenas por score ou por lucro bruto.

## Implementação inicial já criada na branch isolada

- `engine/sources.py`: mapeamentos 30m nos adaptadores públicos.
- `engine/quick_opportunities.py`: classificação local de regime, hipóteses transparentes de breakout/breakdown, momentum e reversão, simulação na vela seguinte, stop conservador (inclui gaps), custos, backtest por família/direção e resumo bootstrap preliminar.
- `tests/test_quick_opportunities.py`: testes unitários iniciais para mapeamentos, vela ainda aberta, horizonte, custos e estatísticas.
- O módulo não é importado pelo scanner nem por executores; nenhuma ordem é possível através dele.
- O loop de backtest está implementado, mas ainda não foi executado sobre histórico real. Não existe prova de edge, benchmark aleatório, validação walk-forward ou dados de derivados históricos.

## Fases de implementação
1. Auditoria do estado da branch e dos dados históricos de 30m.
2. Adaptadores de 30m + testes unitários de normalização/validação, sem alterar os timeframes atuais.
3. Motor de investigação independente com sinais LONG/SHORT e horizonte de 1–8 velas.
4. Backtest dedicado com custos e fills conservadores.
5. Walk-forward, benchmark aleatório, análise por regime e teste fora da amostra.
6. Relatório de candidatos; só depois pedir autorização separada para qualquer integração em paper/live.

## Barreiras de segurança
- Nenhuma ordem real, chamada a endpoints privados, alteração de risco, capital ou alavancagem.
- Não modificar main, config.json, scanner.py, engine/run.py, engine/promo.py, executores ou estado das contas.
- Não ligar o motor ao ciclo de produção.
- A integração em paper e, mais tarde, qualquer ativação real exigem decisões separadas do utilizador.

## Bloqueadores técnicos já observados
- O scanner atual analisa 1D e 4H; o engine/backtest.py existente assume 4H (H4 = 14400) e não serve diretamente para o horizonte 30m–4h.
- engine/sources.py só declara 1d e 4h em TF_SECONDS; alguns adaptadores têm mapeamentos de 1m, mas nenhum está atualmente normalizado para 30m.
- engine/strategies.py é descrito como motor de setups em velas 4H e não cobre ainda as famílias rápidas propostas.
- A branch antiga investigacao-agressivo diverge da main (21 commits à frente e 14 atrás na comparação efetuada em 2026-11-16). Esta investigação começa numa branch nova criada a partir da main para evitar misturar alterações antigas.

Próximo passo: implementar suporte de dados 30m em módulos isolados e respetivos testes, depois construir o motor de papel e o backtest próprio.