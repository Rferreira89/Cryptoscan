"""Estado de validacao de cada estrategia, lido de backtest/results.json.

Enquanto nao houver backtest, ou se a estrategia nao passar os criterios,
todos os sinais levam o aviso correspondente. Nunca se apresenta como
validada uma estrategia que nao o esteja.
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "backtest", "results.json")


def load():
    if os.path.exists(PATH):
        with open(PATH) as f:
            return json.load(f)
    return None


def status(strategy):
    res = load()
    if not res:
        return {"validated": False, "label": "SEM BACKTEST"}
    return res.get("strategies", {}).get(
        strategy, {"validated": False, "label": "SEM BACKTEST"})


def note(strategy):
    """Linha curta e factual sobre a estrategia, para cada alerta."""
    st = status(strategy)
    if st.get("validated"):
        return "Estratégia validada."
    if st.get("n"):
        return (f"⚠️ Não validada (histórico {st['expectancy_r']:+.2f}R/op., "
                f"acerto {st['win_rate']:.0f}%).")
    return "⚠️ Não validada."
