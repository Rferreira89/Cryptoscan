# Investigação agressivo — 2026-11-16

Branch isolada. Produção intacta.

## Capacidade LONG em papel

- `paper_ring.py`: longs não bloqueados por market_ok (BTC como contexto).
- `paper_trend.py`: MAX_POS 4→8; market_ok não veto absoluto. Estratégia LONG diária existente agora mais operacional em papel.
- `paper_bounce.py`: MAX_POS 4→8.
- `paper_ring.py`: MAX_POS 6→12.

## SHORT prioritário

SHORT_SOBRECOMPRA_X70V25 continua em papel.

## Repositórios externos (nota)

- CCXT: já amplamente usado para exchanges; licença MIT. Sem necessidade de nova integração pesada.
- Freqtrade / Nautilus / VectorBT / Jesse / Hummingbot: licenças permissivas na maioria, mas dependências pesadas. Não integrados para não aumentar complexidade sem ganho operacional imediato.

## Longs 1H research

Arquivados.
