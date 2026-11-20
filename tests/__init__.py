"""Os testes nunca leem o engine/events_extra.json real: o agente de
noticias escreve la eventos todos os dias e isso nao pode fazer falhar a
suite (o scanner ao vivo para quando um teste falha)."""
from engine import events

REAL_EXTRA_PATH = events.EXTRA_PATH
events.EXTRA_PATH = "/nao/existe/events_extra.json"

# (20/11) Os testes NUNCA enviam mensagens para o Telegram do Rui. O ciclo de producao corre a suite (validacao do
# codigo novo) com as credenciais do Telegram no ambiente; um teste que corre o scan inteiro (acumulacao em sombra,
# papel com estrategias falsas) mandava mensagens de teste ("Acumulacao Bybit (SOMBRA)... sem precos", "PAPEL KILL
# NOVO") a cada commit. Retiradas aqui, antes de qualquer teste, valem para unittest e pytest em qualquer workflow.
import os as _os

for _k in [k for k in _os.environ if k.startswith("TELEGRAM_")]:
    _os.environ.pop(_k, None)
