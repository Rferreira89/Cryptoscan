# Investigação agressivo — 2026-11-16

Branch isolada. Produção intacta.

## Capacidade LONG estrutural (papel)

- `engine/paper_ring.py`: longs **não** são mais bloqueados por `market_ok=False`.
  BTC passa a ser contexto, não veto universal. Permite longs em altcoins com força individual.

## Limites de papel aumentados

- `paper_ring.py`: MAX_POS 6 → 12.
- `paper_bounce.py`: MAX_POS 4 → 8.

## Estratégia short prioritária

SHORT_SOBRECOMPRA_X70V25 continua em papel (R +0,044 research). Kill se R < 0 com ≥ 20 op.

## Longs 1H research

Arquivados (R ≤ 0). Não insistidos.

## Limites de real (intactos)

MAX_PER_BAR, MAX_PER_FAMILY, RISCO_AGREGADO_MAX — não alterados.
