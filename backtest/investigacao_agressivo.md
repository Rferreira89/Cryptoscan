# Investigação agressivo — 2026-11-16

Branch isolada. Produção intacta.

## Prioridade operacional

Estratégia com R positivo medido: **SHORT_SOBRECOMPRA_X70V25** (R +0,044, p99).
Já registada em papel via `tools/sig_short_sobrecompra.py` + `engine/paper_ring.py`.

Objectivo: maximizar operações desta estratégia em papel (kill se R < 0 com ≥ 20 op.) antes de qualquer real.

## Alterações feitas (papel)

- `engine/paper_ring.py`: MAX_POS 6 → 12.
- `engine/paper_bounce.py`: MAX_POS 4 → 8.

## Limites de real (não alterados)

- MAX_PER_BAR = 4, MAX_PER_FAMILY = 4, RISCO_AGREGADO_MAX = 5.0.

## Longs 1H

Arquivados (R ≤ 0). Não desenvolvidos mais nesta linha.

## Próximo operacional

- Monitorizar SHORT_SOBRECOMPRA em papel até ≥ 25 op. e R > 0.
- Só depois pedir autorização para real com teto.
