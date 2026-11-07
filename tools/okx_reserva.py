"""(07/11, OK do Rui) Lancamento de reserva do agente OKX pelo servidor europeu.

O lancamento principal e o do ciclo do scanner (uma vez por hora entre hh:07 e hh:30, com nova tentativa). Antes, a
Europa tambem lancava o agente em todos os ciclos antes de hh:15 e o agente corria ~2,2 vezes por hora. Agora a Europa
so lanca como reserva: a partir de hh:30, e so se nenhuma volta do agente comecou nesta hora (scanner parado, ou o
lancamento dele falhou). Se o estado nao se ler, lanca (mais vale uma volta a mais, que o agente salta, do que nenhuma).

Uso: python3 tools/okx_reserva.py okx.json  ->  sai com 0 = lancar, 1 = nao lancar.
"""
import json, sys, time

INICIO_RESERVA = 30 * 60          # segundos depois da hora certa


def lancar(st, now):
    sh = now % 3600
    if sh < INICIO_RESERVA:
        return False, "antes de hh:30: o lancamento e do ciclo do scanner"
    try:
        t = float((st.get("resumo") or {}).get("t") or 0)
    except (AttributeError, TypeError, ValueError):
        t = 0
    if t >= now - sh:
        return False, f"o agente ja correu nesta hora (ha {int((now - t) // 60)} min)"
    return True, "nenhuma volta do agente nesta hora: lanca a reserva"


def main(caminho):
    try:
        with open(caminho) as f:
            st = json.load(f)
        if not isinstance(st, dict):
            st = {}
    except Exception:
        st = {}
    sim, porque = lancar(st, time.time())
    print("reserva do agente OKX:", porque)
    return 0 if sim else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "okx.json"))
