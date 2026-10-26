"""Papel x22 (26/10, pedido do Rui: "monta varias operacoes em papel e depois diz-me").
Objetivo testado: transformar 900 em 20 000 (x22,2 sobre a margem) com alavancagem.
SO PAPEL: nenhuma ordem, nenhum dinheiro.

Parte A: 9 operacoes abertas a 26/10 ~11:55 Lisboa aos precos reais da Bybit UE
         (compra ao preco de venda do livro, short ao de compra).
Parte B: regra automatica, a mesma que no historico deu mais sucessos (backtest 2021-26):
         moeda com +10% em 24h -> compra 25x e 50x; -10% em 24h -> short 50x.
         Uma por moeda e lado a cada 24h.
Liquidacao: movimento contra de 1/L - 0,5%. Alvo: (21,2 + comissoes 0,11% x L) / L.
Precos: um ponto a cada scan (~5 min) do ramo data. Sem pavios entre scans: a favor da aposta.

Uso: python3 backtest/estudos/papel_x22.py   (corre a partir do repositorio com origin/data)
"""
import json, subprocess, time

MARGEM, ALVO_X, FEE = 900.0, 20000 / 900 - 1, 0.0011
T0 = 1793015700                          # 26/10/2026 11:55 UTC
A = [  # (moeda, lado, alavancagem, entrada)
    ("ENA", "compra", 25, 0.20573), ("ENA", "compra", 50, 0.20573), ("UNI", "compra", 25, 7.019),
    ("NEAR", "compra", 25, 4.575), ("TRX", "compra", 25, 0.3305), ("WIF", "short", 25, 0.1784),
    ("AAVE", "short", 25, 135.35), ("BTC", "compra", 50, 80292.7), ("BTC", "short", 50, 80292.0)]


def niveis(lado, L, e):
    up, dn = (ALVO_X + FEE * L) / L, 1 / L - 0.005
    return (e * (1 + up), e * (1 - dn)) if lado == "compra" else (e * (1 - up), e * (1 + dn))


def pnl(lado, L, e, px):
    m = (px / e - 1) * (1 if lado == "compra" else -1)
    return MARGEM * (m * L - FEE * L)


def snaps():
    out = subprocess.run(["git", "log", "--reverse", f"--since=@{T0 - 600}", "--format=%H %ct",
                          "origin/data", "--", "scan.json"], capture_output=True, text=True).stdout.split("\n")
    for ln in out:
        if not ln.strip():
            continue
        h, t = ln.split()
        try:
            d = json.loads(subprocess.run(["git", "show", f"{h}:scan.json"], capture_output=True, text=True).stdout)
        except Exception:
            continue
        px = {}
        for r in d.get("universe") or []:
            v = r.get("venue") or {}
            p = v.get("last") if v.get("fonte") == "bybit" else r.get("price")
            if p:
                px[r["asset"]] = (p, r.get("chg_24h"))
        yield int(t), px


def main():
    pos = [dict(a=a, lado=l, L=L, e=e, t=T0, src="A", fim=None) for a, l, L, e in A]
    ult = {}
    for t, px in snaps():
        if t < T0:
            continue
        for a, (p, ch) in px.items():        # parte B
            for cond, lado, Ls in ((ch is not None and ch >= 10, "compra", (25, 50)),
                                   (ch is not None and ch <= -10, "short", (50,))):
                if cond and t - ult.get((a, lado), 0) >= 86400:
                    ult[(a, lado)] = t
                    for L in Ls:
                        pos.append(dict(a=a, lado=lado, L=L, e=p, t=t, src="B", fim=None))
        for o in pos:
            if o["fim"] or o["a"] not in px or t < o["t"]:
                continue
            p = px[o["a"]][0]
            alvo, liq = niveis(o["lado"], o["L"], o["e"])
            ok = p >= alvo if o["lado"] == "compra" else p <= alvo
            bad = p <= liq if o["lado"] == "compra" else p >= liq
            o["px"], o["t_px"] = p, t
            o["min"] = min(o.get("min", 1e18), pnl(o["lado"], o["L"], o["e"], p))
            o["max"] = max(o.get("max", -1e18), pnl(o["lado"], o["L"], o["e"], p))
            if bad:
                o["fim"] = ("LIQUIDADA", t)
            elif ok:
                o["fim"] = ("ALVO 20 000", t)
    f = lambda t: time.strftime("%d/%m %H:%M", time.gmtime(t))
    tot = 0.0
    for o in pos:
        res = -MARGEM if o["fim"] and o["fim"][0] == "LIQUIDADA" else \
            20000 - MARGEM if o["fim"] else pnl(o["lado"], o["L"], o["e"], o.get("px", o["e"]))
        tot += res
        print(f"{o['src']} {o['a']:<6}{o['lado']:<7}{o['L']:>3}x entrada {o['e']:<10g} "
              f"{(o['fim'][0] + ' ' + f(o['fim'][1])) if o['fim'] else 'aberta, agora ' + format(o.get('px', 0), 'g'):<32}"
              f" resultado {res:+9.0f}  (melhor {o.get('max', 0):+.0f}, pior {o.get('min', 0):+.0f})")
    n = len(pos)
    print(f"\n{n} operações, {n * MARGEM:,.0f} de margem em papel; resultado total {tot:+,.0f} "
          f"({sum(1 for o in pos if o['fim'] and o['fim'][0] == 'ALVO 20 000')} chegaram aos 20 000, "
          f"{sum(1 for o in pos if o['fim'] and o['fim'][0] == 'LIQUIDADA')} liquidadas)")


if __name__ == "__main__":
    main()
