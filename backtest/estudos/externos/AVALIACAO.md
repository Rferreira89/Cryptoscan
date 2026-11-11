# Avaliação de vectorbt, Optuna, Qlib e FinRL (11/11/2026)

Investigação isolada. Nenhum destes projetos foi adicionado às dependências do CryptoScan. Os testes correram num
ambiente virtual próprio (`venv`, fora do repositório). Fontes: clones superficiais dos quatro repositórios
(commit e data abaixo), metadados dos pacotes no PyPI e medições próprias. Ambiente: Python 3.13.

| Projeto | Licença | Último commit (clone) | Versão PyPI | Python 3.13 | Dependências principais | Decisão |
|---|---|---|---|---|---|---|
| vectorbt | Apache 2.0 **com Commons Clause** | 07f5e85, 2026-11-08 | 1.2.0 | sim (numba 0.68) | numba, pandas 3, scipy, plotly, ipywidgets, sklearn… (ambiente com ~0,7 GB) | **Rejeitar a integração**; o benchmark fica guardado como prova |
| Optuna | MIT | 0886f6f, 2026-11-09 | 5.0.0 | sim | alembic, sqlalchemy, numpy, tqdm, PyYAML (leve) | **Testar isoladamente**; pode servir a investigação, nunca a produção |
| Qlib | MIT | 5435523, 2026-10-08 | `pyqlib` sem pacote para 3.13 | **não** (classificadores até 3.12) | plataforma completa (dados próprios, modelos torch/lightgbm) | **Rejeitar a plataforma**; aproveitar a ideia do IC/RankIC, reimplementada |
| FinRL | MIT | 7e98df4, 2026-10-25 | 0.3.7 | pacote existe, mas dependências pesadas | ray, stable-baselines3, torch, elegantrl (git), wrds, alpaca, yfinance | **Rejeitar a integração**; a ideia foi testada com um agente mínimo e não passa |

## vectorbt

**Arquitetura.** Backtests vetorizados sobre `pandas`, com o núcleo em `numba` e uma extensão opcional em Rust.
Portefólios a partir de sinais (`Portfolio.from_signals`) ou de funções de ordens.

**Medição** (`vectorbt_bench.py`): uma grelha de referência de 45 configurações (queda de 3 dias × horizonte) sobre
70 ativos de 4H.

| Medida | Ciclo em numpy | vectorbt |
|---|---|---|
| Tempo das 45 configurações | 0,44 s | 9,9 s (inclui a compilação do numba) |
| Mesmo número de operações | — | 0 de 45 |
| Maior diferença no retorno médio | — | 1,1 pontos percentuais |

A diferença vem da semântica. A versão aberta 1.2 não tem saída por número de velas em `from_signals` (`td_stop`
não existe nesta versão, medido). Reproduzir exatamente as regras do CryptoScan obriga a escrever funções de ordem em
numba, o que acrescenta complexidade sem ganho, porque o volume de dados é pequeno (dezenas de ativos de 4H).

**Licença.** A Commons Clause proíbe vender um produto ou serviço cujo valor venha substancialmente do vectorbt. Isto
conta para um projeto que pode vir a ser oferecido a terceiros.

**Sobreajustamento.** Facilitar milhares de configurações aumenta o número de tentativas e, portanto, o DSR exigido.

**Decisão: rejeitar.** O ciclo em numpy dos estudos é mais rápido nesta escala e já é o que está validado.

## Optuna

**Arquitetura.** Biblioteca de otimização: amostradores TPE e NSGA-II (multiobjetivo), poda e armazenamento opcional
em SQL. É leve e não impõe estrutura ao código.

**Teste** (`optuna_h40_wf.py`): afinação multiobjetivo (média diária de R e pior queda) dos filtros da H40 dentro de
um walk-forward (treino de 365 dias, teste de 90 dias). Foram 320 tentativas em 4 passos.

| Fora da amostra (dez/2025 a nov/2026) | Operações | Dias | R médio | p (diário) |
|---|---|---|---|---|
| Filtros afinados pelo Optuna | 61 | 12 | −0,052 | 0,57 |
| Regra registada (BTC ≤ −3%) | 110 | 28 | −0,008 | 0,52 |

A afinação não melhora o fora da amostra. As 320 tentativas teriam ainda de entrar na contagem do DSR. Há uma
limitação: os dados de funding só começam em dez/2024, por isso o walk-forward tem apenas 4 janelas de teste.

**Decisão: testar isoladamente.** Fica disponível para a investigação, sempre dentro de um walk-forward e com as
tentativas contadas. Não serve para afinar parâmetros reais.

## Qlib

**Arquitetura.** Plataforma de investigação quantitativa da Microsoft: armazenamento de dados próprio,
manipuladores de características (Alpha158/360), modelos (GBDT, LSTM, Transformer…), avaliação de sinais
(`contrib/eva/alpha.py`: IC e RankIC por data) e backtest de carteira para ações.

**Compatibilidade.** Não há pacote para Python 3.13, nem classificador acima de 3.12. A plataforma pressupõe dados
diários de ações num formato próprio.

**Aproveitado.** O conceito de IC e RankIC por data: a correlação, transversal entre ativos e por dia, entre uma
característica e o retorno seguinte. Foi reimplementado em biblioteca padrão no caçador de oportunidades
(`engine/oportunidades.py`), sem copiar código.

**Decisão: rejeitar a plataforma.** Fica só a ideia do IC.

## FinRL

**Arquitetura.** Ambientes de mercado em gymnasium, agentes de stable-baselines3, elegantrl e rllib, e ligação a
corretoras (Alpaca) e a dados (yfinance, WRDS).

**Não foi instalado.** As dependências (ray, torch, elegantrl via git, wrds, alpaca) são várias vezes maiores do que
o resto do CryptoScan.

**Teste da ideia** (`rl_baseline_h40.py`): um agente tabular mínimo (Q-learning de um passo) decide entrar ou não em
cada sinal da H40, num walk-forward, contra referências simples no mesmo período fora da amostra.

| Fora da amostra | Operações | R médio | Soma de R | p (diário) |
|---|---|---|---|---|
| Agente tabular (semente 7) | 92 | +0,081 | +7,4 | 0,34 |
| Agente, 20 sementes | 92–162 | média +0,035 (16 de 20 positivas, nenhuma significativa) | — | — |
| Todas as operações | 369 | −0,101 | −37,3 | 0,90 |
| Regra registada | 110 | −0,008 | −0,8 | 0,52 |
| Nenhuma operação | 0 | 0 | 0 | — |
| BTC comprado e mantido (contexto, em %) | — | — | −18,9% | — |

O agente evita parte das perdas, mas o resultado não é significativo, varia com a semente e assenta em 4 janelas.
Um agente profundo, com muitos mais parâmetros, estaria ainda mais exposto ao sobreajustamento.

**Decisão: rejeitar a integração.** Nenhum agente de aprendizagem controla ordens. A ideia pode ser revista quando
houver muito mais dados.
