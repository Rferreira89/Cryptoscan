# Evolução contínua — qualidade operacional

Registo do agente de evolução contínua (deteção, execução, monitorização, dados, interface, eficiência). Sem valores de dinheiro.

## 2026-11-05 (04:30 UTC)
- **Verificado**: agente OKX correu de hora a hora nas últimas 24 h (32 corridas, todas com sucesso; a última falha foi a 04/11 09:35); sem erros nem Traceback nos logs das 3 últimas; 289 contratos, 289 analisados. Scanner da Bybit em ciclo (ramo `data` atualizado às 04:22; `erros.txt` só com falhas antigas de 24/10). Real: 1 operação aberta (HUMA, adotada, com stop e saída por tempo registados); nenhuma pendente; sem duplicados.
- **Medido**: papel do pânico 0 operações fechadas (mercado n=0, isolado n=0): ainda sem dados para comparar com +0,17 a +0,41R. 4 abertas em papel, todas pânico isolado. Recuo (H46) n=0. Macro: 5 fechadas, média −7,29%.
- **Problemas encontrados**: (1) o vigia não via ordens reais presas (pendentes depois de caducar, se a consulta ou o cancelamento falharem); (2) 8 das 33 operações do papel macro congeladas para sempre (CAP, INIT, LIGHT, TRUTH passaram a cripto; SOXS, SQQQ, TSLL, UVXY entraram em FORA); (3) AKE em papel com stop negativo (2 ATR maior do que o preço); (4) o radar diário diz "220 criptos" fixo (são 289).
- **Mudado**: `13fbaa7` vigia avisa de ordens limite reais pendentes mais de 2 h depois de caducarem; `11069cf` macro retira as operações de contratos que saíram do agente (sem resultado, não contam na média; API em baixo não apaga).
- **Verificação**: na próxima volta do agente (hh:07) o log deve mostrar `macro: ... abertas 25`; o aviso de ordem presa só aparece se acontecer.
- **Próxima candidata**: sinal com stop ≤ 0 (AKE): não executar em papel e, no real, dizer a causa certa (hoje diz "ordem mínima"); contagem real de contratos no radar diário.
