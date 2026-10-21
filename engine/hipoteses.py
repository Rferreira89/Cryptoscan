"""Contador global de hipoteses testadas contra os mesmos dados (auditoria
pos-alteracoes, OK do Rui 21/10). Junta a afinacao e a investigacao agendadas
(backtest/afinacao.md e investigacao.md partilham um contador "contra os
mesmos dados") e os estudos feitos fora do programa (hipoteses_offline.json).
Quanto mais testes, mais exigente fica o filtro novo: o limiar do acaso passa
de 95% para 1 - 0,05/K (Bonferroni), para a sorte acumulada nao parecer
descoberta."""
import json
import os
import re

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest")
Q_MAX = 0.999                     # com 1000 repeticoes do acaso nao da para medir mais fino


def _ler(nome):
    try:
        with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def contar():
    """{agendadas, offline, total, quantil}."""
    txt = _ler("afinacao.md") + "\n" + _ler("investigacao.md")
    nums = [int(x) for x in re.findall(r"(\d+) contra os", txt)]
    nums += [int(x) for x in re.findall(r"contador (?:fica em|passa a) (\d+)", txt)]
    agendadas = max(nums) if nums else 0
    try:
        offline = len(json.loads(_ler("hipoteses_offline.json") or "{}").get("estudos") or [])
    except ValueError:
        offline = 0
    total = agendadas + offline
    return {"agendadas": agendadas, "offline": offline, "total": total, "quantil": quantil(total)}


def quantil(k):
    """Percentil do acaso que um resultado tem de bater com k testes feitos."""
    return round(min(Q_MAX, 1 - 0.05 / max(1, k)), 4)
