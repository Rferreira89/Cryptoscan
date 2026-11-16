# Investigação agressivo — 2026-11-16

Branch isolada. Produção intacta.

## Alterações feitas

- `engine/paper_ring.py`: MAX_POS 6 → 12 (papel).
- `engine/paper_bounce.py`: MAX_POS 4 → 8 (papel).

## Limites ainda presentes (não alterados — real)

- `promo.py`: MAX_PER_BAR = 4, MAX_PER_FAMILY = 4, RISCO_AGREGADO_MAX = 5.0, REAL_MIN_R = 0.15.
- Estes afectam dinheiro real. Não alterados sem autorização.

## Estado long 1H

Nenhuma com R > 0. Arquivadas.

## Próximo na branch

- Continuar auditoria de cooldowns e filtros.
- Nova lógica long (ex.: 4H puro ou liquidity sweep) se justificada.
- Só papel após research com R > 0.
