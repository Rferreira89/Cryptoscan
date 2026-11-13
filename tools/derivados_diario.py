"""(13/11, ordem do Rui, B3) Arquivo DIARIO de dados de derivados gratuitos, so para a frente e sem apagar nada,
para avaliar no futuro estrategias com racio long/short, desalavancagem, open interest e financiamento (hoje so ha
30 dias destes dados nas APIs publicas e o arquivo horario de engine/derivhist guarda 20 moedas e 180 dias).

Fontes (ja lidas pelo programa, sem pedidos novos nem custos): o scan publicado (ramo data, scan.json: por moeda
funding, OI a 24h, racio long/short e percentil, base, posicionamento, liquidacoes) e o agente da OKX (ramo okx,
okx.json: funding dos perpetuos). Nao inventa historia: cada linha tem a hora real da leitura.
Uma linha por moeda e por dia UTC (a primeira leitura do dia), num ficheiro por mes: <pasta>/AAAA-MM.csv.
Colunas: dia, t, fonte, moeda, preco, funding_pct8h, funding_pctil, oi_chg_24h_pct, preco_chg_24h_pct, ls_ratio,
ls_pctil, basis_pct, posicionamento, liq_long_kusd, liq_short_kusd, liq_completo.
Uso: python3 -m tools.derivados_diario <scan.json> <okx.json> <pasta>"""
import csv
import json
import os
import sys

DAY = 86400
COLS = ["dia", "t", "fonte", "moeda", "preco", "funding_pct8h", "funding_pctil", "oi_chg_24h_pct", "preco_chg_24h_pct",
        "ls_ratio", "ls_pctil", "basis_pct", "posicionamento", "liq_long_kusd", "liq_short_kusd", "liq_completo"]


def _j(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def linhas_scan(scan):
    t = int(scan.get("generated_at") or 0)
    out = []
    for r in scan.get("universe") or []:
        d = r.get("derivatives") or {}
        if not d or not r.get("asset"):
            continue
        lq = d.get("liquidations") or {}
        fr = d.get("funding_rate")
        out.append({"dia": t // DAY, "t": t, "fonte": d.get("venue") or "?", "moeda": r["asset"], "preco": r.get("price"),
                    "funding_pct8h": None if fr is None else round(float(fr) * 100, 6),
                    "funding_pctil": d.get("funding_pctile"), "oi_chg_24h_pct": d.get("oi_chg_24h_pct"),
                    "preco_chg_24h_pct": d.get("price_chg_24h_pct"), "ls_ratio": d.get("ls_ratio"),
                    "ls_pctil": d.get("ls_pctile"), "basis_pct": d.get("basis_pct"),
                    "posicionamento": d.get("positioning"), "liq_long_kusd": lq.get("long_kusd"),
                    "liq_short_kusd": lq.get("short_kusd"), "liq_completo": lq.get("complete")})
    return out


def linhas_okx(okx):
    out = []
    for inst, serie in ((okx or {}).get("funding") or {}).items():
        if not serie:
            continue
        t, fr = serie[-1][0], serie[-1][1]
        out.append({"dia": int(t) // DAY, "t": int(t), "fonte": "okx", "moeda": inst.split("-")[0],
                    "funding_pct8h": None if fr is None else round(float(fr) * 100, 6)})
    return out


def acrescentar(pasta, linhas):
    """Acrescenta as linhas ainda nao gravadas (chave dia|fonte|moeda). Nunca apaga nem reescreve linhas antigas."""
    os.makedirs(pasta, exist_ok=True)
    novas = 0
    por_mes = {}
    for l in linhas:
        import time as _t
        mes = _t.strftime("%Y-%m", _t.gmtime(l["dia"] * DAY))
        por_mes.setdefault(mes, []).append(l)
    for mes, ls in por_mes.items():
        p = os.path.join(pasta, f"{mes}.csv")
        ja = set()
        if os.path.exists(p):
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    ja.add(f"{row['dia']}|{row['fonte']}|{row['moeda']}")
        novo = not os.path.exists(p)
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if novo:
                w.writeheader()
            for l in ls:
                k = f"{l['dia']}|{l['fonte']}|{l['moeda']}"
                if k in ja:
                    continue
                w.writerow({c: l.get(c) for c in COLS})
                ja.add(k)
                novas += 1
    return novas


def correr(scan_p, okx_p, pasta):
    ls = linhas_scan(_j(scan_p)) + linhas_okx(_j(okx_p))
    n = acrescentar(pasta, ls)
    return {"lidas": len(ls), "novas": n}


if __name__ == "__main__":
    print(json.dumps(correr(*sys.argv[1:4])))
