"""Os testes nunca leem o engine/events_extra.json real: o agente de
noticias escreve la eventos todos os dias e isso nao pode fazer falhar a
suite (o scanner ao vivo para quando um teste falha)."""
from engine import events

REAL_EXTRA_PATH = events.EXTRA_PATH
events.EXTRA_PATH = "/nao/existe/events_extra.json"
