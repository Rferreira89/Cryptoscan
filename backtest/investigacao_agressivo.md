# Investigação agressivo — 2026-11-16

## Auditoria dos commits

- `2a1ed74` (paper_ring): veto market_ok removido para longs. Anti-duplicação intacta (last[t_sig], closed, tg_key). Stops via trade.step. MAX_POS=12 respeitado.
- `6e603d2` (paper_trend): veto market_ok removido; MAX_POS=8. Continua a exigir breakout + acima SMA200 + não late. Limitado a MAJORS21. Stops e trail intactos.
- `cce61f5` (paper_bounce): MAX_POS=8. Lógica de sinal inalterada.

Sem regressões visíveis no código. Sem duplicação de posições por construção.

## Impacto operacional

Ainda não mensurável em dados vivos de papel (alterações recentes). Não há comparação quantitativa de sinais/operações/R antes vs depois.

## Protecções

- Kill se R < 0 com ≥ 20 op. (paper_ring).
- Stops e trail intactos.
- Não se forçam entradas em queda sistémica (regras de sinal de cada estratégia mantidas).
