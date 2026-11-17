"""Global Opportunity Hunter (investigacao isolada, ramo investigacao/expansao-oportunidades).

So dados publicos, sem chaves, sem executores, sem ordens. Modulos:
  dados      universo (todos os X-Perps vivos, historico de instrumentos), velas 30m/1H/4H, funding, falhas de API
  familias   sinais LONG/SHORT de 7 grupos de familias (sem olhar para a frente)
  geometria  saidas: stop k*ATR(tf de referencia), objetivos em R, parcial+trailing, trailing ATR, tempo, inversao
  estat      divisao treino/validacao/teste intocado, controlos emparelhados, bootstrap por blocos (dias), Holm
             cumulativo entre rondas e registo de acessos ao teste
  diagnostico  onde se perde a vantagem: entrada, geometria, objetivo, duracao ou custos
  evolucao   pesquisa evolutiva com orcamento (genoma = familia + parametros + filtro + timeframe + saida)
  papel      paper trading continuo das estrategias selecionadas, com funil de oportunidades
"""
