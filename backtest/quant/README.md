# Módulo quant — DSR, PBO (CSCV) e vantagem residual face ao BTC

Só investigação. Nada daqui decide, liga, desliga ou altera estratégias, risco, capital, alavancagem, ordens ou
posições. Só biblioteca padrão do Python, para correr no CI e no servidor sem dependências novas.
A excepção é `tools/quant_backtests.py`, que volta a correr os estudos registados e por isso precisa do numpy,
tal como os próprios estudos.

| Ficheiro | O que faz |
|---|---|
| `estatistica.py` | Momentos (assimetria; curtose **não** excessiva, normal = 3), normal, t de Student (beta incompleta), inversão de matrizes |
| `dsr.py` | Sharpe, PSR, Sharpe máximo esperado entre N tentativas, Deflated Sharpe Ratio, contagem das tentativas |
| `pbo.py` | CSCV: blocos contíguos, combinações simétricas, escolha dentro da amostra, posição fora, PBO, degradação, embargo |
| `residual.py` | Alinhamento com o BTC, OLS, Newey-West, intervalos t, estabilidade (metades e janelas móveis) e regimes |
| `dados.py` | Operações por **ambiente**: OKX_REAL, BYBIT_REAL, PAPEL, SOMBRA, BACKTEST (nunca somados) |
| `tools/quant_avaliar.py` | Avaliação retrospetiva por estratégia e ambiente (JSON + Markdown, só em R) |
| `tools/quant_backtests.py` | Operações de BACKTEST com hora, a partir dos estudos H40 (h38), H45 e H46 sem os alterar |
| `tools/quant_btc_horario.py` | Preços horários do BTC (Binance pública) para o período das operações ao vivo |

## 1. Deflated Sharpe Ratio
Fonte: Bailey e López de Prado (2014), *The Deflated Sharpe Ratio*, Journal of Portfolio Management 40(5).

- SR = média / desvio dos retornos por observação (não anualizado).
- PSR(SR\*) = Φ((SR − SR\*)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²)), com γ₃ a assimetria e γ₄ a curtose.
- SR₀ = √V[SRₙ] · ((1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e))), com γ a constante de Euler-Mascheroni.
- DSR = PSR(SR₀). Considera-se vantagem provável com DSR ≥ 0,95.

**N (tentativas).** Vem dos registos, não de um número escolhido:
- mínimo: contador global do `engine/hipoteses.py` (afinação e investigação agendadas mais os estudos offline);
- conservador: o mínimo, mais as hipóteses novas registadas (`hipoteses_novas.json`), mais os lutadores da arena (`forma.json`).

O conservador pode contar duas vezes a mesma ideia (um lutador que também foi hipótese). Por isso mostram-se os dois.

**V[SRₙ].** Quando há várias configurações avaliadas sobre os mesmos dados, usa-se a variância dos Sharpe delas. Caso
contrário usa-se a aproximação sob a hipótese nula, 1/(T−1); a origem fica registada em `origem_var_sr`.

**Validação.** O exemplo numérico do artigo (SR anual 2,5; T = 1250; γ₃ = −3; γ₄ = 10; N = 100; V = ½) dá SR₀ = 0,1132 e
DSR = 0,9004; está fixado nos testes.

**Pressupostos e limites:**
- O erro do Sharpe assume observações independentes e identicamente distribuídas. Operações que se sobrepõem no tempo
  (vários sinais no mesmo pânico) estão correlacionadas, por isso o DSR por operação é otimista.
- Com menos de 30 observações o resultado é "insuficiente".

## 2. Probabilidade de sobreajuste (PBO) por CSCV
Fonte: Bailey, Borwein, López de Prado e Zhu (2017), *The Probability of Backtest Overfitting*, Journal of
Computational Finance 20(4).

**Entrada.** A matriz é T períodos × N configurações (R por dia UTC de fecho).
- `periodo="uniao"` serve para configurações que correram em simultâneo sobre os mesmos dados (variantes de um estudo,
  arena).
- `"comum"` serve para séries de períodos diferentes.

**Procedimento:**
1. Divide-se em S blocos **contíguos** (S par); nunca se baralha a ordem temporal.
2. Fazem-se as C(S, S/2) combinações: treino = metade dos blocos, teste = o resto.
3. n\* é a melhor no treino (Sharpe por defeito). Em caso de empate fica a primeira, para ser determinístico.
4. Calcula-se a posição de n\* no teste: w = posição / (N+1), com empates pela média, e λ = ln(w / (1−w)).
5. PBO = fração das combinações com λ ≤ 0 (n\* fica na metade de baixo fora da amostra).
6. Reporta-se também a degradação (inclinação de "fora" sobre "dentro" para n\*) e a probabilidade de perda fora.

**Fugas de informação.** Treino e teste são sempre conjuntos disjuntos de blocos. Com `embargo = k`, o teste perde k
linhas em cada fronteira com o treino. Testado em `tests/test_quant.py`.

**Limites.** Com 2 configurações o PBO tem pouca resolução (λ só toma dois ou três valores). É indicativo; ganha força
com mais configurações.

## 3. Vantagem residual face ao BTC
Modelo: y = α + β·x + ε.

**Alinhamento** (escolhido explicitamente; os dois modos nunca se misturam):
- `por_operacao` (por defeito): y = R da operação e x = retorno do BTC **entre a entrada e a saída dessa operação**.
- `diario`: y = soma do R por dia UTC de fecho (0 nos dias ativos sem fecho) e x = retorno diário do BTC.

**Timestamps e dados em falta:**
- Aceita segundos e milissegundos (valores ≥ 10¹² são tratados como ms).
- Uma saída anterior à entrada é recusada.
- Sem preço do BTC até 5 h antes da entrada ou da saída, a operação é excluída com o motivo. Nunca se preenche um
  preço em falta.

**Estimação:**
- OLS com Newey-West: núcleo de Bartlett, lags = ⌊4·(n/100)^(2/9)⌋, correção n/(n−k).
- Intervalos e p pela t de Student com n−k graus de liberdade.
- Validado contra o statsmodels 0.15 (`cov_type="HAC"`, `use_correction=True`): coeficientes e erros iguais até 1e-9.
  O statsmodels usa a normal para o p por defeito; aqui usa-se a t, que é mais conservadora.

**Saídas:**
- β, α, intervalos, retorno total.
- Parte explicada pelo BTC (β·Σx) e retorno residual (Σ(y − β·x)).
- Estabilidade: metades e janelas móveis.
- Regimes: BTC acima ou abaixo da média dos últimos 20 fechos diários, com uma regressão em cada.

**Limites:**
- β mede só a relação linear com o BTC na mesma janela; não capta dependência não linear (por exemplo, só nas quedas).
- Operações sobrepostas ordenadas pela entrada: o Newey-West corrige a autocorrelação em série, não a correlação entre
  operações simultâneas.

## Separação de ambientes
OKX_REAL e BYBIT_REAL vêm só de operações executadas; PAPEL inclui a arena **sem** as linhas executadas em real (essas
contam em BYBIT_REAL); SOMBRA é o TF-SHORT sombra; BACKTEST são re-simulações dos estudos registados. Nenhuma métrica
soma ambientes diferentes.

## Correr
```
python3 tools/quant_backtests.py <dir com o ramo history extraído> bt.json      # precisa de numpy
python3 tools/quant_avaliar.py <pasta com as cópias públicas> --backtests bt.json [--estado estado.json] [--btc btc.json]
```
No GitHub: `.github/workflows/quant-retrospetiva.yml`. Corre só com push neste ramo de investigação; abre o estado
completo dentro da corrida, nunca o imprime e apaga-o no fim.
