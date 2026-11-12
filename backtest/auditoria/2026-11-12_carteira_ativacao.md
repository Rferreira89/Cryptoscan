# Carteira LONG/SHORT e ativação (12/11/2026, 00h20)

- Ramo `investigacao/universo-bybit-ue`. O main está em 379927e: só um commit do agente de investigação (documentação e testes de hipóteses), sem código de negociação.
- Leituras reais (só GET) no servidor europeu: run 43121871170, autorizado pelo Rui a 11/11 23:40. Os saldos foram só para o Telegram; aqui ficam apenas regras e dados de mercado.

## O que a leitura confirmou

| | Bybit UE | OKX EEA |
|---|---|---|
| Comissões | maker 0,10–0,25%, taker 0,25% por lado | X-Perps: maker 0,02%, taker 0,05% por lado (Lv1) |
| Mínimo de ordem | 5 USDC (BTC: 1 USDC) | Contrato mínimo: mediana de 1,22 USD de nocional (p90 6,2; máx. 16,3) |
| Short | 37 moedas com margem, as 37 emprestáveis e com taxa confirmada | 263 X-Perps negociáveis pela conta (short nativo) |
| Juro / funding | 0,0015 a 0,047% por dia (BTC 0,004%, XRP 0,022%, TRUMP 0,033%): abaixo dos 0,03% assumidos na maior parte | Funding real nas operações (contabilidade) |
| Conta | alavancagem de margem 7x disponível, efetiva 1x | net_mode, margem isolada automática, chave com permissão de negociação |

## SHORT na Bybit UE: SHORT_TURTLE em mercado lateral, por teto de risco real

Mínimos e juros reais por moeda. Capital = o atual da Bybit UE. Fase lateral. Posição = ordem mínima. Dados antes da reserva.

| Teto de risco real | Moedas elegíveis | Período A, R/dia (IC90) | Período B, R/dia (IC90) | Com 1 aberta: R/op (IC90) | Op./ano | Pior DD |
|---|---|---|---|---|---|---|
| 0,5% e 1% | só BTC | −0,01 | −0,15 | −0,07 [−0,43; +0,30] | 6,5 | −9,9R |
| 2% | 19 | +0,06 [−0,25; +0,38] | +0,18 [−0,23; +0,59] | +0,07 [−0,26; +0,39] | 10 | −8,8R |
| 3% | 30 | +0,20 [−0,01; +0,41] | +0,07 [−0,16; +0,30] | +0,30 [+0,01; +0,57] | 13 | −8,8R |
| **4%** | 31 | **+0,31 [+0,11; +0,50]** | **+0,26 [+0,08; +0,45]** | **+0,39 [+0,14; +0,65]** | 14 | −7,1R |
| 5% | 31 | +0,26 [+0,09; +0,44] | +0,29 [+0,11; +0,49] | +0,36 [+0,12; +0,61] | 14 | −7,1R |

- **Porquê 4%, e não "porque deixa negociar".** Abaixo de 3 ou 4%, o teto deixa de fora as moedas mais voláteis, que são onde está a vantagem. Os subconjuntos de 2% e 3% não têm evidência nos dois períodos. A 4% fica a estratégia completa (exceto ENA, WLD, PEPE e TRUMP hoje), com os dois períodos positivos. 5% não acrescenta nada.
- **Risco real a 4%:** mediana de cerca de 2,6% por operação, máximo de 4%. Uma posição de cada vez (limite de família), por isso o risco agregado é igual ao de uma operação.

## SHORT na OKX: TF-SHORT U2

- **Sizing da própria regra:** peso de 0,25%/vol diária; o risco no stop fica em 1,2 a 1,7% da conta por posição. No máximo 5 posições e exposição bruta de 0,5x (agregado ≤ ~7,5%, se perderem todas juntas).
- **Capital mínimo** (contrato mínimo / peso, sinais abertos de hoje no universo validado): DOGE 7,5, XRP 11,5, SUI 13,1, BNB 63, WLD 75, PUMP 84, HYPE 98, AVAX 122, LINK 146, ZEC 204, ENA 378 (USD).
- **Evidência:**
  - histórico com moedas retiradas: +0,15R/op, +0,09R por dia, antes da reserva;
  - reserva: −0,26R por dia;
  - papel: 0 fechadas.
- **Executor:** `tools/okx_tfshort_exec.py`, completo e testado; NÃO está ligado.

## LONG: nenhuma estratégia existente passa

| Candidata | Resultado (com moedas retiradas, por dia independente) |
|---|---|
| H46 recuo (já real a 1% na OKX) | sem vantagem por dia; com teto de 3 abertas cerca de 0R |
| TURTLE long em subida (OKX, custos e funding) | A −0,07R por dia (IC [−0,19; +0,04]), B +0,05 (IC [−0,17; +0,29]): sem vantagem |
| TURTLE long em lateral | A +0,07, B −0,34R por dia (IC < 0): perde |
| Bounce/DIP em subida | 6 dias independentes: inconclusiva |
| H40 pânico do mercado | ~0R por dia com qualquer preenchimento |

- **Impedimento concreto:** nenhuma long existente tem expectativa positiva por acontecimento fora da amostra, depois de corrigido o viés de sobrevivência.
- **Solução mais próxima:**
  - MOMENTO_RISCO_ON em sombra prospetiva, a contar a partir de 12/11;
  - a H46 continua como experiência já autorizada (risco pequeno, 0 sinais em lateral).

## Código implementado e testado (inerte em produção)

- `tools/leitura_contas.py`: as leituras acima, só GET; saldos só para o Telegram.
- `tools/okx_tfshort_exec.py`:
  - short com stop anexado; fecho pela regra só com reduceOnly;
  - reconciliação; clOrdId determinístico com adoção (51016); adoção de posições sem registo;
  - alerta de posição sem stop; falhas transitórias; recusas sem repetição.
- `tools/okx_tfshort_plano.py`, `engine/viabilidade.py`, `engine/piloto.py` (guarda e sizing), `engine/risk.py` e `engine/promo.py` (`piloto_teto_pct` e `cfg_piloto`: sem a chave `"piloto"` nada muda).
- Testes: `test_leitura_contas`, `test_okx_tfshort_exec`, `test_viabilidade`, `test_piloto`. Suite completa em 3.12 sem yaml nem numpy: OK.

## O que falta e precisa da autorização do Rui

1. Integrar o ramo no main. É inerte até à configuração, mas muda os números da arena (shorts só onde há margem).
2. Corrigir no registo o AVAX e o ICP, que constam como reais mas nunca executaram, antes de qualquer piloto.
3. **Piloto Bybit:** acrescentar ao `config.json`:
   - `"real_autorizados": ["SHORT_TURTLE"]`;
   - `"piloto": {"estrategia": "SHORT_TURTLE", "teto_pct": 4, "perda_max_r": -8, "inicio": <data>}`.
4. **TF-SHORT na OKX:**
   - indicar o capital da OKX (enviado por Telegram);
   - aprovar o passo de execução: chamar `okx_tfshort_exec.volta` no workflow da TF-SHORT, com as chaves da OKX, e `"tfshort_real": true`. O passo do workflow ainda não está escrito: faço-o depois do OK.
