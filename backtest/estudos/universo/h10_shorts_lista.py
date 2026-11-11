"""H10 so com os SHORTS, com o codigo do estudo, guardando duracao e stop para descontar o juro."""
import json, sys
sys.path.insert(0, "/home/claude/cryptoscan")
src = open("/home/claude/cryptoscan/backtest/estudos/h10_fases.py").read().split('if __name__ == "__main__":')[0]
src = src.replace('out.append({"k": k, "a": a, "t": t["t"], "r": t["r"], "fase": RMAP.get(d - 1)})',
                  'out.append({"k": k, "a": a, "t": t["t"], "t_fim": t.get("t_fim"), "stop": t["geo"]["stop"], "r": t["r"], "fase": RMAP.get(d - 1)})')
assert '"t_fim"' in src
g = {"__name__": "h10"}
exec(compile(src, "h10", "exec"), g)
g["LONGS"][:] = []
moedas = sys.argv[2].split(",")


todos = [t for a in moedas for t in g["trabalho"](a)]
json.dump(todos, open(sys.argv[1], "w"))
print(len(todos))
