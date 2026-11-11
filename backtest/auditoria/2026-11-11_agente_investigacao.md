# Auditoria do agente de investigação — 2026-11-11

Ramo `investigacao/auditoria-agente`, criado a partir de `main` em 428c5a0. Nada foi fundido no main. Nada em `engine/`,
`.github/`, `config.json`, `backtest/results.json`, nas tarefas agendadas nem nas corretoras foi tocado (ver §9).

Dados usados: ramo `history` (70 moedas, 4H até 2026-11-08 12:00 UTC, funding desde 2024-09), `scan.json` e
`state.json` do ramo `data` e `forma.json` do ramo `arena` (11/11, cerca das 11:23 e das 17:11 UTC). A rede para a Binance
não está disponível neste ambiente, por isso o combate não foi corrido de novo; as operações foram reconstruídas com o
histórico e batem uma a uma com o registo do combate (§5).

**Regra seguida nesta auditoria.** Tudo o que mede robustez ou procura anomalias usa só dados **antes de 2026-05-08**
(início da reserva em vigor). A reserva não foi usada para escolher nada. Os 90 dias recentes da BOUNCE_AMPLITUDE só
foram descritos, porque já tinham sido vistos pelo combate.

---

## 1. Diagnóstico e reconciliação dos números

| Afirmação | Confirmada? | Fonte | Correção |
|---|---|---|---|
| 26 hipóteses contra a reserva | Sim: 12 no diário de investigação + 14 na afinação (H1–H15 sem a H14, que foi uma medição). `engine/hipoteses.contar()` também dá 26 | diários; `engine/hipoteses.py` | É só o contador **dos diários**. Contra dados que incluem a reserva atual (2026-05-08 → 11-08) foram feitos **155 testes registados**: mais 75 estudos offline, 50 lutadores da arena, 5 de dados novos, cada um com a sua grelha. O próprio `contar()` dá total 101 (26 + 75), e o diário ainda diz "87" (valor de 04/11, desatualizado) |
| ~74% de pelo menos um falso positivo | Sim: 1 − 0,95²⁶ = 73,6% | — | Com testes independentes. Medido nos 23 lutadores de compra com ≥ 30 operações (18 meses de desenho): correlação média 0,21; número efetivo 20,2 (Nyholt), 15 (Li-Ji) ou 6,1 (participação). A correlação reduz o número de testes, mas a subcontagem pesa muito mais: 155 testes × 0,27–0,88 dão 42 a 136 testes efetivos, ou seja, **88% a 99,9%** de probabilidade de pelo menos um falso positivo |
| 21 corridas seguidas sem hipótese | Sim (entradas de 21/10 a 11/11) | diário | Falta a entrada de **09/11**: essa corrida não deixou registo |
| 10 lutadores vivos | Sim: 50 na classificação, 40 mortos, mínimo 5 | `scan.json` | — |
| BOUNCE_AMPLITUDE: 16 op., +0,82R | Sim às 11:23 UTC | `forma.json`, `state.json` | Às 17:11 UTC o mesmo combate dava **13 op., +0,77R**. São operações **simuladas** num combate de 90 dias recalculado de hora a hora, com um universo que muda com o filtro de liquidez; não são operações ao vivo (0 na arena). **14 das 16 entraram na mesma vela** (2026-10-09 00:00 UTC). Na prática são **2 acontecimentos** |
| REVERSAO_INTERVALO: 27 op., −0,006R | Sim às 11:23 | `forma.json` | Às 17:11: 22 op., +0,026R. Oscila de hora a hora |
| BREAKOUT_R2, SHORT_SQUEEZE, MAIORES_TENDENCIA: 2–4 op. negativas | Sim (2 op. −1,02R; 4 op. −0,84R; 3 op. −0,79R) | `forma.json` | — |
| H15 RECUO_SUBIDA: −0,23R, percentil 0,1 | Sim, na fase de subida de 2021–24 (163 op.) | `afinacao_h15_recuo_subida.json` | Em 2024–26 a mesma fase dá +0,106R (percentil 71,7). A rejeição está certa (falha uma das metades), mas o resumo mostra só a metade que rejeita |

## 2. Problemas encontrados

| # | Gravidade | Problema | Prova | Onde se corrige |
|---|---|---|---|---|
| P1 | **Crítico** | O teste contra o acaso sorteia **cada operação à parte** (`engine/arena._dist`, `tools/arena_ringue.judge`). Quando várias operações nascem do mesmo acontecimento (a mesma vela em muitas moedas), a distribuição do acaso fica demasiado estreita e é fácil "passar o p95" com um só dia bom | BOUNCE_AMPLITUDE, 90 dias (21 op., 3 acontecimentos): acaso independente p95 −0,07 (p = 0,003); **acaso agrupado p95 +0,61** (p = 0,027). Janela de exploração 2021–26: independente p = 0,075; **agrupado p = 0,29** (igual ao acaso) | Implementado em `tools/estatistica_multipla.acaso_agrupado`. Mudar a arena é produção: **precisa de autorização** (A1) |
| P2 | **Crítico** | A reserva não está limpa: 155 dos 158 testes registados viram dados dela. Com a janela de 24 meses a deslizar todos os dias, a reserva de hoje esteve no desenho de corridas anteriores | `registo_hipoteses.contaminacao()` | Implementado: uma reserva já vista só deixa chegar a **PARA PAPEL**. A prova confirmatória passa a ser **prospetiva** (dados depois do registo) |
| P3 | **Crítico** | O contador vem de expressões regulares sobre o texto do diário (`engine/hipoteses.contar`: o maior número a seguir a "contra os" ou "contador passa a"). Qualquer frase o pode mudar, não conta grelhas nem lutadores, e os números divergem (26 / 87 / 101) | código; §1 | Implementado o registo central `backtest/registo/hipoteses.jsonl`. Ligar `engine/hipoteses` ao registo é produção (A2) |
| P4 | Alto | A unidade de prova é a operação, não o acontecimento. As regras da arena ("20 op."), da investigação ("40 fora da amostra") e do papel ("30 op.") contam operações que podem ser um só dia | BOUNCE_AMPLITUDE: 16 op. = 2 acontecimentos. Na exploração há 19 acontecimentos por ano com desvio-padrão de 0,67R; detetar +0,15R por acontecimento (unilateral, 5%, poder 80%) pede **125 acontecimentos, cerca de 6,5 anos** | `resumo_eventos`, `n_necessario`. Contar acontecimentos nas regras da arena é produção (A5) |
| P5 | Alto | Os efeitos que existem nos dados são pequenos de mais para os custos: ida e volta custa 0,7% (2 × 0,35%), e as famílias de 4H com detenção de 1–3 dias precisam de mais do que isso por operação | Triagem (exploração, 52 células): os maiores efeitos andam por 0,1–0,3% por dia; só horizontes de 7 dias chegam a margem líquida positiva, e mesmo esses sem significância | Novo ponto de partida da descoberta (§3) |
| P6 | Alto | As famílias estão desequilibradas: reversão à média (B) tem 47 dos 158 testes (30%), sazonalidade (F) 1, multitemporal (H) 5, microestrutura (G) 8. E nos dados não há reversão seccional: a reversão de 1 dia dá **t = −2,8** (as que caem continuam a cair) | registo; triagem | A triagem cobre as famílias A–I por igual |
| P7 | Médio | O combate não é reprodutível: o universo muda de hora a hora (filtro de liquidez), e o filtro de 25% da BOUNCE_AMPLITUDE está no fio da navalha (22,9% com 70 moedas, ≥ 25% com 44) | §5 | Fixar o universo do combate por semana é produção (A4) |
| P8 | Médio | Não havia ficha obrigatória: critérios e métrica primária ficavam em texto livre, sem verificação | diários | Implementado (`FICHA.md`, `validar_ficha`) |
| P9 | Médio | `tools/research.py` ainda tem 0,1% de comissão por omissão (a decisão de 07/10 é 0,25%). As ferramentas novas usam 0,25% + 0,1%, mas um teste novo feito com `research.py` subestimaria os custos | `tools/research.py:30` | A ficha recusa custos abaixo de 0,35% por lado. `research.py` não foi mudado para não alterar resultados antigos |
| P10 | Médio | Viés de sobrevivência: o `history` só tem moedas listadas hoje. As delistadas só entram nalguns estudos offline | `tools/fetch_history.py` | Assinalado na triagem; um efeito de compra só conta depois de confirmado com as delistadas |
| P11 | Baixo | O critério 6 da reserva é fraco ("Sharpe > 0") | `tools/research.py` | O DSR (`estatistica_multipla.dsr`) já está disponível para o protocolo |

## 3. Alterações implementadas

| Ficheiro | O que faz |
|---|---|
| `tools/estatistica_multipla.py` | Holm, Benjamini-Hochberg, Šidák, p-valor empírico, matriz de correlação, valores próprios (Jacobi), número efetivo de testes (Nyholt, Li-Ji, participação), PSR, DSR, PBO por CSCV, agrupamento por acontecimentos com intervalo por acontecimento, amostra necessária, **teste contra o acaso agrupado**. Python puro, sem dependências |
| `tools/registo_hipoteses.py` + `backtest/registo/hipoteses.jsonl` | Registo só de acrescentar, com cadeia SHA-256. Ficha obrigatória (17 campos, família A–I/X, grelha ≤ 6, custos ≥ 0,35% por lado). A validação não se pode sobrepor à exploração; a validação prospetiva só usa dados posteriores ao registo; a reserva usa-se uma vez; reserva já vista → teto PARA PAPEL; o resultado exige a métrica primária declarada; um veredicto acima do teto é recusado; `verificar --contra origin/main` deteta linhas apagadas. Semente retroativa com os **158 testes** já feitos, com família (classificador + 12 correções à mão) e janela de dados aproximada |
| `backtest/registo/FICHA.md` | Modelo da ficha e as regras |
| `tools/triagem_anomalias.py` | Triagem **exploratória** por família (A, B, D, F, G, H, I e E informativa) só antes do corte, com retorno bruto, excesso sobre o universo, margem líquida depois de 0,7% e Holm sobre todas as células |
| `tools/auditoria_bounce_amplitude.py` | Auditoria só de leitura (§5) |
| `tools/n_efetivo_lutadores.py` | Correlação diária entre os lutadores de compra na janela de desenho → número efetivo de testes |
| `backtest/auditoria/*.json` | Resultados: `triagem_2026-11-11.json`, `bounce_amplitude_2026-11-11.json`, `n_efetivo_2026-11-11.json` |
| `backtest/registo/PROMPT_PROPOSTO.md` | Proposta de funcionamento diário e semanal (não aplicada) |
| 5 ficheiros de teste em `tests/` | 50 testes novos; a bateria completa passa de 1134 para 1184, todos a passar |

Ficaram **por fazer, à espera de autorização**, porque tocam em produção:

- **A1** — trocar `engine/arena._dist` pelo acaso agrupado. Muda quem morre e quem se qualifica na arena.
- **A2** — `engine/hipoteses.contar` passar a ler o registo central. Muda o limiar do filtro novo do ringue.
- **A3** — mudar o texto e a cadência da tarefa agendada (proposta em `PROMPT_PROPOSTO.md`).
- **A4** — universo do combate fixo por semana.
- **A5** — regras da arena e do papel a contar acontecimentos e não operações.

## 4. Primeira triagem (exploração, 2021-01 → 2026-05-08, 70 moedas, 52 células)

**Não é validação. Tem viés de sobrevivência.**

| Família | Melhor célula | Bruto | Excesso sobre o universo | Líquido (−0,7%) | t | Holm |
|---|---|---|---|---|---|---|
| F | vela de 4H que abre às 04h UTC (mercado) | +0,15% | — | −0,55% | 3,35 | **0,021 (passa)** |
| A | momento de 7 dias, quintil de cima, 1 dia | +0,20%/dia | +0,15% | −0,50% | 2,92 | 0,09 |
| G | fração compradora de 3 dias, 1 dia | +0,15% | +0,10% | −0,55% | 2,73 | 0,16 |
| F | quarta-feira | +1,06% | — | +0,36% | 2,51 | 0,28 |
| G | surto de volume, 7 dias | +1,07% | +0,70% | +0,37% | 1,60 | 1,0 |
| I | financiamento negativo de 3 dias, 3 dias | +0,26% | +0,29% | −0,44% | 1,78 | 1,0 |
| B | reversão de 1 dia, 1 dia | −0,07% | −0,11% | −0,77% | **−2,84** | — |
| D | compressão 5/60, 7 dias | −0,33% | −0,70% | −1,03% | **−3,03** | — |
| E | BTC a cruzar para cima a SMA200 (24 vezes) | +4,0% em 30 dias | — | — | — | informativo |

Leitura:

1. Nenhuma célula passa Holm **com margem líquida positiva**. Não há nestes dados uma anomalia que pague os custos de spot da Bybit UE em detenções curtas.
2. A única célula que passa Holm (a vela das 04h UTC) foi testada contra zero, não contra as outras horas. A média das
   seis velas é cerca de +0,06%, por isso a vantagem própria da hora ronda +0,09%. Vale +0,15% por vela, cinco vezes menos do que o custo de ida e volta. Sozinha não se negocia. Pode servir para escolher **a hora de entrada** de uma estratégia que já vai comprar (custo extra nulo), e isso só se avalia de forma prospetiva.
3. As únicas margens líquidas positivas aparecem a 7 dias (momento, fração compradora, surto de volume), todas sem significância. Se houver vantagem acessível com estes custos, está em **horizontes mais longos**, não em novas entradas de 4H.
4. A família mais testada (B) é a que os dados mais contrariam. As quedas de 1 a 3 dias continuam, não revertem.

## 5. Auditoria da BOUNCE_AMPLITUDE (só leitura)

Regra: RSI de 4H abaixo de 30 a virar, só com ≥ 25% das moedas em sobrevenda; saída G0; BTC acima da SMA200.

- **As 16 operações.** 2 a 16/09 (ICP +2,32R e DOT +0,07R, fase de subida) e 14 a **2026-10-09 00:00 UTC** (fase lateral): ARB +1,71, PEPE +1,44, XLM +1,25, TRUMP +0,96, SKY +0,93, VIRTUAL +0,90, LINK +0,85, DOGE +0,58, BNB +0,53, ETH +0,51, LTC +0,39, XRP +0,28, DOT +0,24, SOL +0,20. Os 14 valores R do combate batem um a um com a reconstrução local.
- **Distribuição.** 16 em 16 positivas; média por operação +0,82R. Por acontecimento, são 2 acontecimentos (3 velas). O acerto de 100% é o ressalto de um só dia de capitulação geral (08/10), não uma taxa de acerto.
- **Concentração.** 14/16 numa vela; 14/16 na fase lateral; a melhor moeda (ARB) vale 0,07R da média.
- **Limiar no fio da navalha.** Nessa vela, 22,9% das 70 moedas do `history` estavam em sobrevenda. No universo de 44 moedas do combate a fração passou os 25%, porque saíram AIXBT, ANIME, LA, MASK e NXPC. Com o limiar a 25% a reconstrução local tem 2 operações; a 22% tem 21.
- **Robustez do limiar (exploração 2021-08 → 2026-05).** Nenhum limiar se aguenta: 15% −0,22R/op. (129 acontecimentos), 20% −0,22R, 25% −0,22R (92 acontecimentos, intervalo de 90% por acontecimento [−0,51; −0,28]), 30% −0,20R, 35% −0,28R. Sem filtro (BOUNCE_X30), −0,11R. O filtro não melhora nada.
- **Custos.** Com 0,1% + 0,05% −0,18R; com 0,25% + 0,1% −0,22R; com 0,25% + 0,2% −0,24R; com 0,4% + 0,2% −0,27R. Negativa com qualquer custo: o problema não está nos custos.
- **Contra o acaso.** Exploração: média −0,222R; acaso independente mediana −0,275, p95 −0,212, p = 0,075; **acaso agrupado** mediana −0,272, p95 −0,099, **p = 0,29**. Ser "menos má do que o acaso" desaparece quando o acaso respeita o agrupamento. Nos 90 dias recentes (dados já vistos): independente p = 0,003, agrupado p = 0,027, com 3 acontecimentos.
- **Referência passiva.** Nos mesmos 90 dias o BTC comprado deu **+18,1%** (81 dos 90 dias acima da SMA200). Uma conta com uma posição teria feito 2 operações em 90 dias.
- **Porque passou o acaso e falhou o critério da conta.** Passou o acaso porque o p95 do combate trata as 14 operações de 09/10 como 14 sorteios independentes. Falhou o critério da conta (estudo de 02/11) porque em cinco anos cada operação perde dinheiro (−0,15R em 2021–24, −0,20R em 2024–26). Ser "menos má do que o acaso" não faz crescer uma conta, e com o valor todo numa posição a conta encolhe nas duas metades.
- **Amostra que falta.** 19 acontecimentos por ano; desvio-padrão de 0,67R por acontecimento. Para detetar +0,25R são precisos 45 acontecimentos (~2,3 anos); para +0,15R, 125 (~6,5 anos); para +0,10R, 281 (~15 anos). As "20 operações" da arena podem ser 1 ou 2 acontecimentos.
- **Veredicto da auditoria.** Sem vantagem demonstrada; com o método agrupado, indistinguível do acaso na exploração e negativa em termos absolutos. Não foi promovida nem alterada. O combate vai continuar a mostrá-la acima do acaso enquanto a arena usar o método independente (A1).

## 6. Melhorias esperadas e limitações

O que melhora, e porquê:

- **Disciplina.** Antes, uma hipótese podia ser desenhada e validada nos mesmos dados sem que nada o impedisse. Agora o código recusa a ficha, o uso duplo da reserva e o veredicto acima do teto (os testes provam cada recusa). O histórico de rejeitadas não se apaga sem partir a cadeia.
- **Leitura estatística.** O acaso agrupado mudou a conclusão do único lutador "acima do acaso" (p 0,075 → 0,29 na exploração). O número de testes passou de "26 numa frase" para 158 registados, com família e origem.
- **Descoberta.** Em vez de 21 corridas sem nada, a triagem dá um mapa com 52 células corrigidas por Holm. Mostra porque é que as entradas de 4H falham (custos contra o tamanho do efeito, reversão inexistente) e onde vale a pena olhar (horizontes de 7 dias ou mais; F e G como filtros de execução).

Limitações:

- A semente retroativa tem famílias e janelas **aproximadas** (classificador automático mais correções à mão) e conta uma configuração por estudo. É um limite inferior das grelhas.
- A triagem usa só as moedas listadas hoje (viés de sobrevivência) e testes simples (quintil de cima contra o universo). Não substitui uma ficha.
- O número efetivo só cobre os 23 lutadores de compra com ≥ 30 operações; os estimadores discordam muito entre si (6 a 20).
- O acaso agrupado agrupa por vela de 4H. Um acontecimento que se espalha por velas seguidas conta como vários (fica ainda otimista).
- Nada disto está ligado à arena nem ao scanner (A1–A5). Os testes do registo real só correm com `CRYPTOSCAN_REGISTO=1`, de propósito: um registo estragado nunca pode parar o scanner ao vivo.

## 7. Novo funcionamento proposto (a aplicar só com autorização, A3)

- **Diário (curto, sem hipóteses).** Verificar o histórico; ler a arena; se morrer alguém, fazer a autópsia **por acontecimentos** com o acaso agrupado; atualizar o acompanhamento prospetivo das hipóteses registadas; `verificar` o registo. Uma corrida sem hipótese nova é o resultado normal, não uma falha. Notificação só se houver morte, autópsia com causa clara ou uma hipótese prospetiva a cruzar um critério.
- **Semanal (exploração).** Correr a triagem na janela de exploração (que pode crescer porque a validação deixa de ser a reserva). Se houver uma célula que passe Holm **e** tenha margem líquida plausível, escrever no máximo **uma** ficha com uma razão económica, pre-registá-la e pô-la em validação prospetiva. Senão: "sem anomalia nova", com a tabela.
- **Validação.** Por omissão, prospetiva (papel/ringue/dados novos posteriores ao registo, até 30 **acontecimentos**). A reserva histórica passa a filtro de sanidade (necessária, não suficiente) com teto PARA PAPEL. Critério da conta como já está.
- **Porque semanal.** A matéria-prima da descoberta (o `history`) só se atualiza de poucos em poucos dias. As mortes foram 19 e 18 nas semanas 42–43 (corte dos clones) e depois 2, 1 e 0 por semana. Um acontecimento de capitulação dá-se cerca de 19 vezes por ano. Uma pergunta nova por dia contra os mesmos dados só aumenta o número de testes (P2/P3) sem acrescentar informação. Os 21 dias sem hipótese confirmam-no: a pressão diária não produziu nada, e a única produção recente (H45 "PASSA" a 04/11) caiu no papel (19 op., −0,39R).

## 8. Como descobrir sem contaminar a validação

1. **Explorar** só com dados até ao corte de exploração (hoje 2026-05-08; `triagem_anomalias.CORTE`, com teste a garantir que nada depois entra).
2. **Pre-registar** a ficha antes de qualquer número da validação. Cadeia de hashes, `quando` imutável, métrica e critérios fixos.
3. **Validar para a frente.** Só dados com data posterior ao registo contam (`usar_dados(..., "prospetiva")` recusa o resto). É o mesmo princípio que o caçador noturno já usa com `dados_para_avaliar`, agora geral e verificado.
4. **Contar acontecimentos**, não operações, e comparar com o acaso agrupado.
5. **Corrigir pela multiplicidade.** Holm sobre as células da triagem; DSR com o número de tentativas do registo; PBO quando houver grelha.
6. **Nunca apagar.** Rejeitadas e notas ficam para sempre; correções entram como `nota`.

## 9. Produção e trading real intactos

`git diff --stat origin/main...investigacao/auditoria-agente` só mostra ficheiros novos em `tools/`, `tests/`,
`backtest/registo/` e `backtest/auditoria/`. Nenhuma alteração em `engine/`, `.github/`, `config.json`,
`okx_config.json`, `admin.json`, `backtest/results.json`, `backtest/investigacao.md` ou `backtest/afinacao.md`. Nenhuma
tarefa agendada foi criada, mudada ou apagada. Nenhuma chamada à Bybit ou à OKX. Nenhuma ordem, posição, stop ou objetivo
foi tocado. Nada foi fundido no main.
