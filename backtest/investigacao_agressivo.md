# Investigação agressivo — 2026-11-16

Branch isolada. Produção intacta.

## Alterações feitas

- `engine/paper_ring.py`: MAX_POS 6 → 12 (papel). Permite mais posições simultâneas sem alterar risco real.

## Estado das estratégias long 1H (research)

| Estratégia | R médio | Estado |
|-------------|----------|--------|
| ATAQUE_1H long | ≈ -0,26 | Rejeitada |
| LONG_TENDENCIA_1H v3 | ≈ -0,22 | Rejeitada |
| LONG_BOUNCE_1H | ≈ -0,03 a -0,15 | RECRUTAR / amostra pequena; R ainda ≤ 0 |

Nenhuma long 1H com R > 0. Não sobe a papel nem real.

## Próximo (na branch)

- Auditar outros limites (cooldowns, filtros BTC, max posições por estratégia).
- Nova lógica long (ex.: 4H puro ou bounce mais selectivo) se justificado.
- Só activar em papel após research com R > 0.
