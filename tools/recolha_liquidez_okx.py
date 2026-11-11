"""(11/11, P5) Recolha PUBLICA de liquidez dos X-Perps da OKX EEA para estudar o deslize dos stops.

So endpoints publicos de mercado (GET, sem chaves): /api/v5/public/instruments, /api/v5/market/tickers e
/api/v5/market/books (400 niveis). Uma linha por contrato e por volta em liquidez_okx.jsonl (ramo de dados de
investigacao), com spread, profundidade a 0,5/1/2%, desequilibrio e deslize previsto de compra e venda para 100 e
1 000 USD. Nao guarda nada da conta. Nao decide nada: alimenta engine.qualidade_execucao.
Uso: python3 tools/recolha_liquidez_okx.py <saida.jsonl> [ativo ...]   (sem ativos: todos os X-Perps)"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import qualidade_execucao as Q  # noqa: E402

BASE = "https://eea.okx.com"
PUBLICOS = ("/api/v5/public/instruments", "/api/v5/market/tickers", "/api/v5/market/books")


def publico(path, abrir=urllib.request.urlopen):
    if not path.startswith(PUBLICOS):
        raise ValueError(f"so endpoints publicos de mercado: {path}")
    with abrir(urllib.request.Request(BASE + path, headers={"User-Agent": "cryptoscan"}), timeout=15) as r:
        return json.loads(r.read().decode())


def xperps(ler=publico):
    d = ler("/api/v5/public/instruments?instType=FUTURES").get("data") or []
    return {x["instId"]: float(x.get("ctVal") or 1) for x in d if "XPERP" in x.get("instId", "") and x.get("state") == "live"}


def linha(inst, ct, ler=publico, now=None):
    b = (ler(f"/api/v5/market/books?instId={inst}&sz=400").get("data") or [{}])[0]
    bids = [(x[0], x[1]) for x in b.get("bids") or []]
    asks = [(x[0], x[1]) for x in b.get("asks") or []]
    out = {"t": int(now or time.time()), "ativo": inst.split("-")[0], "inst": inst}
    for v in (100.0, 1000.0):
        lv = Q.livro(bids, asks, valor=v, ct_val=ct)
        if not lv:
            return None
        if v == 100.0:
            out.update({k: lv[k] for k in ("spread_bps", "prof_0.5pct", "prof_1pct", "prof_2pct", "desequilibrio")})
        out[f"compra_{int(v)}_bps"] = lv["deslize_compra_bps"]
        out[f"venda_{int(v)}_bps"] = lv["deslize_venda_bps"]
    return out


def correr(saida, ativos=None, ler=publico, pausa=0.12):
    xs = xperps(ler)
    if ativos:
        xs = {i: c for i, c in xs.items() if i.split("-")[0] in set(ativos)}
    n = 0
    with open(saida, "a") as f:
        for inst, ct in sorted(xs.items()):
            try:
                ln = linha(inst, ct, ler)
            except Exception as e:                      # um contrato falhado nao para a recolha
                print("livro falhou:", inst, type(e).__name__)
                continue
            if ln:
                f.write(json.dumps(ln) + "\n")
                n += 1
            time.sleep(pausa)                           # ~8 pedidos/s, abaixo do limite publico (20 / 2 s)
    return n


if __name__ == "__main__":
    print("linhas:", correr(sys.argv[1], sys.argv[2:] or None))
