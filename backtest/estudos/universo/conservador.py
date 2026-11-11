import sys, json, importlib
sys.path.insert(0, "."); sys.argv = sys.argv
from tools import _qb_tmp as Q
X = float(sys.argv[3])
Q.TROCAS.extend(Q.TROCAS_ATIVO)
Q.TROCAS.append(('d["l"][k] <= lim: return min(lim, d["o"][k])', f'd["l"][k] <= lim * (1 - {X}): return min(lim, d["o"][k])'))
Q.TROCAS.append(('if d["l"][k] <= lim:', f'if d["l"][k] <= lim * (1 - {X}):'))
r = Q.recolher(sys.argv[1]); json.dump(r, open(sys.argv[2], "w"))
from collections import Counter; print(X, dict(Counter(o["estrategia"] for o in r["operacoes"])))
