# Ficha obrigatória de uma hipótese

Desde 2026-11-11 nenhuma hipótese é testada sem esta ficha registada **antes** de qualquer resultado:

```
python -m tools.registo_hipoteses pre-registar ficha.json
```

O registo (`backtest/registo/hipoteses.jsonl`) é **só de acrescentar**. Cada linha leva o hash da anterior. Apagar ou
mudar uma linha parte a cadeia, e `python -m tools.registo_hipoteses verificar --contra origin/main` deteta-o antes do
commit. Uma hipótese rejeitada fica para sempre no registo.

## Campos (todos obrigatórios; o código recusa a ficha se faltar algum)

| Campo | O que é | Exemplo |
|---|---|---|
| `id` | identificador único, curto, em maiúsculas | `ENTRADA_04H` |
| `familia` | A momento · B reversão · C shorts · D quebras/volatilidade · E regime · F sazonalidade · G microestrutura/fluxo · H multitemporal · I fontes novas · X gestão/saídas | `F` |
| `justificacao` | a anomalia observada **e** o mecanismo económico ou comportamental que a explica | "a vela das 04h UTC sobe mais do que as outras (triagem de 2026-11-11, t=3,3, Holm 0,02): abertura europeia sobre a liquidez asiática" |
| `fonte_dados` | de onde vêm os dados e até quando há histórico | `ramo history, 4H Binance, 2021-01 → 2026-11` |
| `universo` | que moedas, com que filtro de liquidez, se inclui as delistadas | `moedas da Bybit UE com volume ≥ 20 M` |
| `direcao` | `LONG`, `SHORT` ou `AMBOS` | `LONG` |
| `temporalidade` | vela de decisão e horizonte | `4H; detenção 1–7 dias` |
| `entrada`, `saida` | regras completas, só com velas fechadas | |
| `custos` | `{"por_lado_pct": ≥ 0,35}`: 0,25% de comissão da Bybit UE + 0,1% de deslize (mais juros/financiamento se houver) | `{"por_lado_pct": 0.35}` |
| `h0` | a hipótese nula, escrita para ser rejeitada | "o R médio líquido por acontecimento é ≤ 0" |
| `metrica_primaria` | UMA métrica, com nome; o resultado tem de a trazer | `{"nome": "r_liquido_por_acontecimento"}` |
| `criterios_rejeicao` | lista fechada, escrita antes de ver | `["r ≤ 0", "p agrupado ≥ 0,05", "< 30 acontecimentos"]` |
| `protocolo` | método de validação (sete critérios, acaso agrupado, critério da conta) | |
| `exploracao` | `{"inicio","fim"}`: os dados que foram vistos para ter a ideia | `{"inicio":"2021-01-01","fim":"2026-05-08"}` |
| `validacao` | `{"tipo":"prospetiva","inicio":…}` (só dados **depois** do registo) ou `{"tipo":"reserva","inicio","fim"}` | |
| `grelha` | 1 a 6 configurações, todas declaradas | `[{"h":1},{"h":3}]` |

Opcionais úteis: `deriva_de` (id da hipótese de onde vem), `fonte_anomalia` (ficheiro da triagem que a sugeriu).

## Regras que o código faz cumprir

1. A validação não se pode sobrepor à exploração da própria ficha.
2. Uma validação **prospetiva** só usa dados com data posterior ao pre-registo.
3. Cada hipótese usa uma reserva **uma única vez**.
4. Se a janela de reserva já foi vista por outra hipótese, o veredicto máximo passa a **PARA PAPEL**. A 11/11/2026, 155 das
   158 hipóteses registadas tinham visto dados da reserva em vigor (maio a novembro de 2026), por isso uma hipótese nova
   validada nessa reserva já não pode passar de PARA PAPEL.
5. Um resultado só entra depois do pre-registo, com a métrica primária declarada. Um veredicto acima do teto é recusado.
6. Só uma validação prospetiva limpa permite **CANDIDATA**. Dinheiro real continua a exigir 30 operações em papel acima do
   acaso e o sim do Rui numa sessão (nada disto muda a lista REAL_OK).

## Exemplo mínimo

```json
{"id": "EXEMPLO", "familia": "F", "justificacao": "…", "fonte_dados": "history 4H",
 "universo": "todas as moedas do history", "direcao": "LONG", "temporalidade": "4H",
 "entrada": "…", "saida": "…", "custos": {"por_lado_pct": 0.35},
 "h0": "R médio líquido por acontecimento ≤ 0", "metrica_primaria": {"nome": "r_liquido_por_acontecimento"},
 "criterios_rejeicao": ["r_liquido_por_acontecimento <= 0", "p_acaso_agrupado >= 0.05", "acontecimentos < 30"],
 "protocolo": "prospetivo: papel/ringue até 30 acontecimentos; acaso agrupado; critério da conta",
 "exploracao": {"inicio": "2021-01-01", "fim": "2026-05-08"},
 "validacao": {"tipo": "prospetiva", "inicio": "2026-11-12"},
 "grelha": [{"h": 1}]}
```
