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
    """Linha factual sobre o registo da estrategia, para cada alerta."""
    st = status(strategy)
    if st.get("validated"):
        return (f"Estratégia validada em backtest: {st['expectancy_r']:+.2f}R "
                f"por operação, acerto {st['win_rate']:.0f}%, {st['n']} "
                "operações.")
    if st.get("n"):
        return (f"⚠️ Estratégia NÃO validada: em backtest deu "
                f"{st['expectancy_r']:+.2f}R por operação, acerto "
                f"{st['win_rate']:.0f}% em {st['n']} operações. Risco reduzido "
                "a metade.")
    return "⚠️ Estratégia sem backtest. Risco reduzido a metade."
