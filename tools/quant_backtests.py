"""(10/11) Operacoes de BACKTEST por operacao (com hora de entrada e de saida) a partir dos estudos JA registados,
sem os alterar: executa a mesma parte do codigo que os estudos executam e recolhe a lista de operacoes.
  H40 (backtest/estudos/h38_custos_futuros.py, custos de futuros OKX): todos os sinais e so o panico do mercado todo
  H45 (backtest/estudos/h45_panico_bybit.py, custos Bybit UE): panico do mercado todo
  H46 (backtest/estudos/h46_recuo_tendencia.py): RSI < 30 e RSI < 35 (as duas variantes registadas)
Dados: velas de 4H e funding do ramo history (extraido para <dir_history>). Precos do BTC de 4H para a analise residual.
So investigacao; nao toca em estrategias nem em producao. Uso: python3 tools/quant_backtests.py <dir_history> <saida.json>"""
import json
import os
import sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HIST_ORIGINAL = "/tmp/claude-0/hist"
# (11/11) opcional (--com-ativo): o ativo de cada operacao, para a robustez entre ativos. Acrescenta o nome do ativo
# no FIM do tuplo de cada candidato (os estudos so leem os candidatos por indice 0-4: nada muda nos resultados).
TROCAS_ATIVO = (('R, r, ts)); livre = j; break', 'R, r, ts, a)); livre = j; break'),
                ('R, int(d["t"][i]))); livre = j; break', 'R, int(d["t"][i]), a)); livre = j; break'))
TROCAS = []


def _src(nome):
    with open(os.path.join(RAIZ, "backtest", "estudos", nome), encoding="utf-8") as f:
        return f.read()


def _abrir(hist):
    """open() dos estudos: os ficheiros .py que um estudo le e executa (exec em cadeia) tambem passam a apontar para
    'hist' — senao o estudo interior leria o caminho antigo e podia usar dados velhos ou nenhuns."""
    import io

    def abrir(p, *a, **k):
        caminho = os.path.join(RAIZ, p) if str(p).startswith("backtest/") else p
        if str(p).endswith(".py") and not (a and "w" in a[0]):
            with open(caminho, encoding="utf-8") as f:
                return io.StringIO(_trocar(f.read().replace(HIST_ORIGINAL, hist)))
        return open(caminho, *a, **k)
    return abrir


def _trocar(src):
    for a, b in TROCAS:
        src = src.replace(a, b)
    return src


def _correr(src, hist):
    g = {"__name__": "estudo", "open": _abrir(hist)}
    os.chdir(RAIZ)
    exec(compile(_trocar(src.replace(HIST_ORIGINAL, hist)), "estudo", "exec"), g)
    return g


def _ativo(c, base):
    return {**base, "ativo": c[-1]} if TROCAS and isinstance(c[-1], str) else base


def _mercado(g):
    b = g["dados"]["BTC"]; bidx = b["idx"]
    return lambda ts: (lambda k: k is not None and k >= 6 and b["c"][k] / b["c"][k - 6] - 1 <= -0.03)(bidx.get(ts))


def recolher(hist):
    import glob
    if not glob.glob(os.path.join(hist, "funding", "*.csv.gz")) or not os.path.exists(os.path.join(hist, "BTC.csv.gz")):
        raise SystemExit(f"sem dados do ramo history em {hist} (velas de 4H e funding): nada calculado")
    out, btc = [], []
    # H40: h38 ate a lista 'cand' = (t_entrada, t_saida, R, ret, t_sinal)
    g = _correr(_src("h38_custos_futuros.py").split('print("A) compra no panico com custos de futuros")')[0], hist)
    merc = _mercado(g)
    for c in g["cand"]:
        base = _ativo(c, {"ambiente": "BACKTEST", "t_entrada": int(c[0]), "t_saida": int(c[1]), "R": float(c[2]), "nota": "custos de futuros OKX (h38)"})
        out.append({**base, "estrategia": "H40 (todos os sinais)"})
        if merc(c[4]):
            out.append({**base, "estrategia": "H40 (panico do mercado)"})
    btc = [[int(t), float(v)] for t, v in zip(g["dados"]["BTC"]["t"], g["dados"]["BTC"]["c"])]
    # H45: o proprio estudo monta o codigo com os custos da Bybit; cortar antes do ciclo de relatorio
    s45 = _src("h45_panico_bybit.py").split('for per in ("B1", "B2"):')[0]
    g = _correr(s45, hist)
    merc = _mercado(g)
    out += [_ativo(c, {"ambiente": "BACKTEST", "estrategia": "H45 (panico do mercado, custos Bybit)", "t_entrada": int(c[0]), "t_saida": int(c[1]), "R": float(c[2]),
             "nota": "custos Bybit UE (h45)"}) for c in g["cand"] if merc(c[4])]
    # H46: as duas variantes registadas
    s46 = _src("h46_recuo_tendencia.py")
    cab, resto = s46.split("for L in (30, 35):")
    corpo = resto.split("    cand.sort()")[0]
    for L in (30, 35):
        g = _correr(cab + f"for L in ({L},):" + corpo + "    cand.sort()\n", hist)
        out += [_ativo(c, {"ambiente": "BACKTEST", "estrategia": f"H46 (RSI<{L})", "t_entrada": int(c[0]), "t_saida": int(c[1]), "R": float(c[2]), "nota": "h46"}) for c in g["cand"]]
    return {"operacoes": out, "btc_4h": btc}


if __name__ == "__main__":
    if "--com-ativo" in sys.argv:
        TROCAS.extend(TROCAS_ATIVO)
        sys.argv.remove("--com-ativo")
    r = recolher(os.path.abspath(sys.argv[1]))
    json.dump(r, open(sys.argv[2], "w"))
    from collections import Counter
    print(dict(Counter(o["estrategia"] for o in r["operacoes"])), f"BTC 4H: {len(r['btc_4h'])} velas")
